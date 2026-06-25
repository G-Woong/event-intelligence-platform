"""DB write target 안전 가드 (R-EventSinkDbTarget).

운영 결선 sink / seed 가 `settings.DATABASE_URL` 로 Event 를 영속할 때, 의도치 않은 DB
(특히 staging/production)에 쓰는 것을 **구조적으로 차단**한다. dev/test 는 허용,
staging/production 은 명시 opt-in(`allow_non_dev`/`--allow-non-dev-db`) 없이는 거부한다
(fail-closed). 자격증명은 라벨에서 제외(host:port/dbname 만 — 비밀 미노출).

run_event_orchestration(운영 결선)과 seed_event_timeline(데모 seed) 이 **동일 정책을 공유**한다.
"""
from __future__ import annotations

from sqlalchemy.engine import make_url

# Event write 를 명시 허용 없이 받는 환경 — **allowlist**(dev/test 만). staging/production·
# 오타·미지 환경은 모두 거부(fail-closed; denylist 의 fail-open 회귀 차단).
_DEV_ENVS = frozenset({"dev", "test"})
# dbname 에 이 마커가 보이면 APP_ENV 와 무관하게 거부 — APP_ENV 단일 신뢰 회피
# (APP_ENV=dev 오설정 + DATABASE_URL→prod 우회 차단, 2차 방어).
_PROD_DB_MARKERS = ("prod", "production")
# staging 마커 — classify_write_target(ADR#54) 의 named 분류용(차단 정책 아님·진단/경고용).
_STAGING_DB_MARKERS = ("staging", "stg")


class UnsafeWriteTargetError(RuntimeError):
    """dev/test 가 아닌(또는 prod 처럼 보이는) DB 에 명시 허용 없이 Event write 를 시도했다."""


def target_db_label(database_url: str) -> str:
    """DATABASE_URL → `host:port/dbname` 라벨(자격증명 제외). 파싱 실패 시 '?'.

    운영/테스트 DB 혼동을 운영자가 눈으로 확인하도록 stdout 에 출력하는 용도.
    password/username 은 절대 포함하지 않는다(비밀 미노출).
    """
    try:
        u = make_url(database_url)
        return f"{u.host or '?'}:{u.port or '?'}/{u.database or '?'}"
    except Exception:
        return "?"


def _dbname(database_url: str) -> str:
    try:
        return (make_url(database_url).database or "").lower()
    except Exception:
        return ""


def assert_safe_write_target(
    *, app_env: str, database_url: str, allow_non_dev: bool = False
) -> str:
    """Event write 대상 DB 안전성 강제 — 라벨(자격증명 제외) 반환(호출자 출력용).

    **2중 fail-closed 가드**(R-EventSinkDbTarget closure = "APP_ENV 기반 DB 선택 + 명시 확인"):
      ① **APP_ENV allowlist** — dev/test 만 무명시 허용. staging/production·오타·미지 환경은
         모두 거부(denylist 가 아니라 allowlist → 새 비-dev 환경 추가 시 누락돼도 fail-closed).
      ② **DATABASE_URL 교차검증** — dbname 에 prod 마커가 있으면 APP_ENV 와 무관하게 거부
         (APP_ENV=dev 오설정 + DATABASE_URL→prod 우회 차단 — APP_ENV 단일 신뢰 회피).
    `allow_non_dev=True`(--allow-non-dev-db) 는 둘 다 우회하는 명시 opt-in.
    "출력(보임)"이 아니라 "차단(거부)"이 핵심.
    """
    label = target_db_label(database_url)
    if allow_non_dev:
        return label
    # ① APP_ENV allowlist.
    if app_env not in _DEV_ENVS:
        raise UnsafeWriteTargetError(
            f"refusing Event write: APP_ENV={app_env!r} is not dev/test "
            f"(target={label}); pass allow_non_dev / --allow-non-dev-db to override"
        )
    # ② dbname prod 마커 교차검증.
    dbname = _dbname(database_url)
    if any(m in dbname for m in _PROD_DB_MARKERS):
        raise UnsafeWriteTargetError(
            f"refusing Event write: target DB name looks production-like "
            f"(target={label}, APP_ENV={app_env}); "
            f"pass allow_non_dev / --allow-non-dev-db to override"
        )
    return label


# named 환경 분류 severity(높을수록 위험) — classification 은 APP_ENV/URL 둘 중 더 위험한 쪽을 채택.
_TARGET_SEVERITY = {"unknown": 0, "dev": 1, "test": 1, "unmarked": 1, "staging": 2, "production": 3}


def classify_write_target(*, app_env: str, database_url: str) -> dict:
    """APP_ENV + DATABASE_URL dbname → **named 환경 분류**(dev/test/staging/production/unknown) + 일치성(ADR#54).

    `assert_safe_write_target` 는 dev/test 허용·그외 차단의 **binary** 가드다(차단이 핵심). 이 함수는 그 위에서
    운영 activation preflight 용 **이름붙은 분류**와 APP_ENV↔URL **불일치 경고**를 제공한다(자격증명 미노출·차단 아님).
    분류는 보수적 — URL dbname 의 prod/staging 마커가 APP_ENV 보다 위험하면 그쪽을 채택(APP_ENV=dev 오설정 +
    prod-like URL 같은 위험 조합을 가장 위험한 쪽으로 표면화). 일치성:
      - env=dev/test 인데 URL=staging/production → **위험한 불일치**(env 가 '안전'이라 거짓 안심 가능).
      - env=staging/production 인데 URL=unmarked(prod/staging 마커 없음) → 경고(운영인데 dev-like URL — 오설정 가능).
    """
    env_class = app_env if app_env in ("dev", "test", "staging", "production") else "unknown"
    dbname = _dbname(database_url)
    if any(m in dbname for m in _PROD_DB_MARKERS):
        url_class = "production"
    elif any(m in dbname for m in _STAGING_DB_MARKERS):
        url_class = "staging"
    else:
        url_class = "unmarked"   # prod/staging 마커 없음(전형적 dev 이름)
    # 최종 분류 = 더 위험한 쪽. URL 마커가 prod/staging 이면 APP_ENV 보다 우선(오설정 방어).
    classification = url_class if _TARGET_SEVERITY[url_class] > _TARGET_SEVERITY[env_class] else env_class
    if classification == "unmarked":   # unmarked 가 살아남는 경우(env=unknown) → unknown 으로 환원.
        classification = env_class if env_class != "unknown" else "unknown"
    # 일치성 = URL tier 가 APP_ENV tier 와 맞는가(모든 cross-tier 불일치를 빠짐없이 — dev/test→unmarked,
    # staging→staging, production→production 만 일치). env=unknown 은 검증 불가라 항상 불일치(fail toward flag).
    if env_class in ("dev", "test"):
        consistent = url_class == "unmarked"
    elif env_class == "staging":
        consistent = url_class == "staging"
    elif env_class == "production":
        consistent = url_class == "production"
    else:   # unknown env(오타·미지) — 어떤 URL 과도 일치 단정 불가.
        consistent = False
    return {
        "classification": classification,
        "env_class": env_class,
        "url_class": url_class,
        "consistent": consistent,
        "is_dev_target": classification in ("dev", "test"),
        "is_production_target": classification == "production",
    }
