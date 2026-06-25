"""ADR#54 — production activation preflight (read-only·운영 가동 전 통합 점검).

scheduler/backfill persist 를 켜기 전, 흩어진 게이트를 **하나의 report** 로 묶어 운영자에게
can_dry_run / can_persist · block_reasons · next_required_actions 를 제시한다:
  - operational_db_readiness (migration/identity 테이블·destructive_risk·ADR#48)
  - backfill_preflight       (flag·persist_allowed·ADR#51)
  - classify_write_target    (named 환경 분류·APP_ENV↔URL 불일치·ADR#54)
  - assert_safe_write_target (dev/test allowlist binary 가드·ADR#27)

**read-only**: DDL/upgrade/persist 0(어떤 write 도 안 함 — 이 도구는 가동 *전 점검*). DATABASE_URL 원문
**미로그**(target_db_label fingerprint 만 — host:port/dbname·자격증명 제외). 자동 병합과 무관(auto_merge_enabled=False).

**safe-target 정직 경계(MEDIUM-1):** dev `event_intel` + APP_ENV=dev 에서 assert_safe_write_target 는 사실상
no-op 이다. 이 preflight 는 그 한계를 classify_write_target 의 named classification + APP_ENV↔URL 불일치 경고로
**표면화**한다 — 실제 운영 보호막은 별도 운영 DB + APP_ENV=production + target 정책이지, dev 경로의 safe-target 이 아니다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.config import settings
from backend.app.tools.backfill_semantic_adjudications import (
    backfill_preflight,
    count_pending_semantic_links,
)
from backend.app.tools.db_target import (
    UnsafeWriteTargetError,
    assert_safe_write_target,
    classify_write_target,
    target_db_label,
)
from backend.app.tools.identity_backlog_readiness import operational_db_readiness


async def production_activation_preflight(
    session: AsyncSession,
    *,
    persist_requested: bool,
    allow_non_dev: bool = False,
    allow_flag_off: bool = False,
    scheduler_profile_enabled: Optional[bool] = None,
    app_env: Optional[str] = None,
    database_url: Optional[str] = None,
) -> dict:
    """운영 activation 전 통합 preflight report(read-only). 게이트 입력을 DB 에서 모아 _build_preflight_report 로 조립.

    can_dry_run = ready_for_stage3(테이블만 준비되면 읽기전용 가능).
    can_persist = persist_requested ∧ ready ∧ (flag 또는 allow_flag_off) ∧ safe_target ∧ ¬destructive_pending
                  ∧ (APP_ENV↔URL 일치 또는 allow_non_dev 명시 override).
    """
    app_env = settings.APP_ENV if app_env is None else app_env
    database_url = settings.DATABASE_URL if database_url is None else database_url

    readiness = await operational_db_readiness(session)
    pre = await backfill_preflight(session, allow_flag_off=allow_flag_off)
    flag_enabled = bool(pre["flag_enabled"])

    # safe-target 판정(차단 여부 — raise 잡아 bool 화·이 함수는 read-only 라 raise 전파 안 함).
    try:
        assert_safe_write_target(
            app_env=app_env, database_url=database_url, allow_non_dev=allow_non_dev)
        safe_target = True
    except UnsafeWriteTargetError:
        safe_target = False

    # backlog 가시성 — ready 일 때만(미준비 DB 에서 NOT IN adjudication 쿼리 크래시 방지).
    pending_links = (
        await count_pending_semantic_links(session)
        if bool(readiness.get("ready_for_stage3")) else None)

    return _build_preflight_report(
        app_env=app_env, database_url=database_url, persist_requested=persist_requested,
        allow_non_dev=allow_non_dev, allow_flag_off=allow_flag_off,
        scheduler_profile_enabled=scheduler_profile_enabled, readiness=readiness,
        flag_enabled=flag_enabled, safe_target=safe_target, pending_links=pending_links)


def _build_preflight_report(
    *,
    app_env: str,
    database_url: str,
    persist_requested: bool,
    allow_non_dev: bool,
    allow_flag_off: bool,
    scheduler_profile_enabled: Optional[bool],
    readiness: dict,
    flag_enabled: bool,
    safe_target: bool,
    pending_links: Optional[int],
) -> dict:
    """게이트 입력(readiness/flag/safe_target/...) → preflight report(**순수·DB 무관**·결정론).

    block_reasons 는 capability 게이트 미충족 사유(persist_requested 자체는 제외 — can_persist 가 별도 반영).
    scheduler_profile_enabled 는 런타임 introspect 불가(compose profile 활성 여부) — 호출자 명시값 또는 None."""
    cls = classify_write_target(app_env=app_env, database_url=database_url)
    ready = bool(readiness.get("ready_for_stage3"))
    destructive = bool(readiness.get("destructive_risk"))

    can_dry_run = ready
    block_reasons: list[str] = []
    if not ready:
        block_reasons.append("readiness:stage3_tables_absent")
    if not (flag_enabled or allow_flag_off):
        block_reasons.append("flag:semantic_adjudication_disabled")
    if not safe_target:
        block_reasons.append("safe_target:non_dev_db_without_allow")
    if destructive:
        block_reasons.append("migration:destructive_pending")
    if not cls["consistent"] and not allow_non_dev:
        block_reasons.append("boundary:app_env_url_mismatch")
    can_persist = persist_requested and not block_reasons

    warnings: list[str] = []
    if cls["classification"] in ("dev", "test") and safe_target:
        warnings.append(
            "safe_target_noop_in_dev: assert_safe_write_target 는 dev/test 경로에서 사실상 no-op "
            "— 실 운영 보호막은 별도 운영 DB + APP_ENV=production")
    if not cls["consistent"]:
        warnings.append(
            f"app_env_url_mismatch: APP_ENV={app_env}(env_class={cls['env_class']}) vs "
            f"URL class={cls['url_class']} — 운영 DB 경계 확정 필요")
    if persist_requested:
        # index/lock 은 DEFER(미적용) — persist 가동 시 운영 caveat 으로 표면화(은폐 금지).
        warnings.append(
            "created_at_index_deferred: (created_at,id) 인덱스 미적용(0010 예정·DEFER) "
            "— 대형 백로그 keyset 페이지 시 latency 주의")
        warnings.append(
            "single_runner_discipline: advisory lock 미구현(DEFER) — 동시 backfill 은 중복 work 가능. "
            "단일 runner 또는 disjoint --after-link-id 범위로 운영(데이터 안전은 PK upsert 멱등)")
    if pending_links == 0:
        warnings.append(
            "backlog_zero: pending semantic link 0 — 실 fetch/stage③ 누적 전까지 처리할 백로그 없음")

    next_required_actions: list[str] = []
    if not ready:
        next_required_actions.append(
            "운영 DB 0003→head 배포(백업 후·승인 필요): build_operational_deploy_checklist 절차")
    if not flag_enabled and not allow_flag_off:
        next_required_actions.append(
            "EVENT_SEMANTIC_ADJUDICATION_ENABLED=1 설정(.env) 또는 --allow-flag-off 명시")
    if not safe_target:
        next_required_actions.append(
            "비-dev DB write 는 --allow-non-dev-db 명시 또는 APP_ENV/DATABASE_URL 교정")
    if destructive:
        next_required_actions.append(
            "미적용 migration 에 destructive op — 배포 전 검토(데이터 손실 위험)")
    if not cls["consistent"]:
        next_required_actions.append(
            f"APP_ENV({app_env})↔DATABASE_URL(class={cls['url_class']}) 불일치 — 운영 DB 경계 확정")
    if can_persist:
        next_required_actions.append(
            "모든 게이트 통과 — --persist 가동 가능(dry-run 선행·단일 runner 권장)")
    elif can_dry_run and not persist_requested:
        next_required_actions.append(
            "dry-run 가능 — persist 전 규모 확인(--dry-run)")

    return {
        "app_env": app_env,
        "database_url_fingerprint": target_db_label(database_url),
        "target_classification": cls["classification"],
        "env_class": cls["env_class"],
        "url_class": cls["url_class"],
        "app_env_url_consistent": cls["consistent"],
        "is_dev_target": cls["is_dev_target"],
        "is_production_target": cls["is_production_target"],
        "allow_non_dev_db": allow_non_dev,
        "event_resolution_enabled": bool(settings.EVENT_RESOLUTION_ENABLED),
        "semantic_adjudication_enabled": flag_enabled,
        "scheduler_profile_enabled": scheduler_profile_enabled,
        "persist_requested": persist_requested,
        "ready_for_stage3": ready,
        "db_revision": readiness.get("current_revision"),
        "expected_head": readiness.get("expected_head"),
        "pending_migrations": readiness.get("missing_revisions"),
        "behind_count": readiness.get("behind_count"),
        "identity_tables_present": readiness.get("tables_present"),
        "destructive_risk": destructive,
        "safe_write_target": safe_target,
        "pending_semantic_links": pending_links,
        "can_dry_run": can_dry_run,
        "can_persist": can_persist,
        "block_reasons": block_reasons,
        "warnings": warnings,
        "next_required_actions": next_required_actions,
        "auto_merge_enabled": False,
    }


def preflight_exit_code(report: dict) -> int:
    """preflight report → deterministic exit code(운영/CI 관측용).

    0 = green(persist 요청 시 can_persist·아니면 can_dry_run) · 1 = blocked(게이트 미충족).
    2(runtime error: DB down 등)는 main() 가 직접 반환(이 함수는 게이트 판정만)."""
    if report["persist_requested"]:
        return 0 if report["can_persist"] else 1
    return 0 if report["can_dry_run"] else 1


# ── read-only CLI(운영자가 가동 전 점검·DDL/upgrade/persist 0) ──
async def _run_preflight(
    *, persist_requested: bool, allow_non_dev: bool, allow_flag_off: bool,
    scheduler_profile_enabled: Optional[bool],
) -> dict:
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as session:
            return await production_activation_preflight(
                session, persist_requested=persist_requested, allow_non_dev=allow_non_dev,
                allow_flag_off=allow_flag_off, scheduler_profile_enabled=scheduler_profile_enabled)
    finally:
        await engine.dispose()


def main(argv: Optional[list[str]] = None) -> int:
    try:  # Windows cp949 콘솔이 한국어/em-dash 에 죽지 않도록 utf-8(closeout_sig 선례).
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="production activation preflight (read-only·운영 가동 전 통합 점검·DDL/upgrade/persist 0).",
    )
    parser.add_argument("--persist", action="store_true",
                        help="persist(영속 가동)를 요청한 경우의 게이트 평가(can_persist). 미지정=dry-run 평가만.")
    parser.add_argument("--allow-non-dev-db", action="store_true",
                        help="APP_ENV=staging/production DB 에도 허용(기본 거부 — fail-closed). 불일치 경계 override.")
    parser.add_argument("--allow-flag-off", action="store_true",
                        help="EVENT_SEMANTIC_ADJUDICATION_ENABLED off 여도 persist 게이트 통과(명시 우회).")
    parser.add_argument("--scheduler-profile-enabled", choices=("true", "false"), default=None,
                        help="docker compose --profile backfill 활성 여부(런타임 introspect 불가·명시값).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # read-only 이지만 어떤 DB 를 probe 하는지 운영자 확인(자격증명 제외 라벨).
    print(f"- preflight target DB: {target_db_label(settings.DATABASE_URL)} (APP_ENV={settings.APP_ENV})")
    spe = None if ns.scheduler_profile_enabled is None else (ns.scheduler_profile_enabled == "true")
    try:
        report = asyncio.run(_run_preflight(
            persist_requested=ns.persist, allow_non_dev=ns.allow_non_dev_db,
            allow_flag_off=ns.allow_flag_off, scheduler_profile_enabled=spe))
    except Exception as e:   # runtime error(DB down 등) → exit 2(자격증명 미노출: 타입·메시지만).
        print(f"- ERROR preflight runtime failure: {type(e).__name__}: {e}")
        return 2

    print(
        f"- classification: {report['target_classification']} "
        f"(env={report['env_class']} url={report['url_class']} consistent={report['app_env_url_consistent']})")
    print(
        f"- readiness: ready_for_stage3={report['ready_for_stage3']} revision={report['db_revision']} "
        f"head={report['expected_head']} behind={report['behind_count']} "
        f"destructive_risk={report['destructive_risk']} pending_links={report['pending_semantic_links']}")
    print(
        f"- gates: flag={report['semantic_adjudication_enabled']} safe_target={report['safe_write_target']} "
        f"can_dry_run={report['can_dry_run']} can_persist={report['can_persist']} "
        f"auto_merge={report['auto_merge_enabled']}")
    if report["block_reasons"]:
        print(f"- block_reasons: {report['block_reasons']}")
    for w in report["warnings"]:
        print(f"- WARNING {w}")
    for a in report["next_required_actions"]:
        print(f"- next: {a}")
    return preflight_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
