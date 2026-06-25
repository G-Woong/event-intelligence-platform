"""ADR#60 — targeted same-event acquisition → near-match reviewer/gold operating readiness.

ADR#58/#59 가 정직하게 남긴 gap: ① near-match reviewer/gold queue(ADR#59)는 captured fixture 수준에서 멈춰
있고 ② untargeted RSS fetch 는 same-event cross-source overlap 0(ADR#58 실증). 이 모듈은 그 queue 를
**targeted same-event acquisition**(source-pair·topic·time-window)과 연결해, 실 near-match 후보를 채울 수 있는
**detection-layer 운영 경로**를 닫는 orchestrator 다. 자동 병합 턴도, LLM 본경로 턴도, 운영 DB 배포 턴도 아니다.

재구현 0 — 무거운 일은 전부 기존 단일 출처가 한다:
  - 실 governed fetch: `source_overlap_discovery.fetch_rss/gdelt_overlap_records`(transport 주입 시 결정론·본문 미저장)
  - overlap 분해: `source_overlap_discovery.discover_overlap`(fingerprint vs near vs hard-negative band)
  - reviewer/gold queue: `near_match_reviewer_queue.build_near_match_reviewer_queue`/`resolve_queue_gold`/linkage
  - packet/gold/agreement: `identity_human_labeling`(build_labeling_packet/resolve_gold_from_reviewers/…)

절대 불변(상속·재확인 — 상용 안전 계약):
  - **no merge / no auto-merge**: 같은 사건 단정·병합 0(no_merge_without_gold/no_merge_without_gate).
  - **정직한 acquisition**: 실 fetch 가 0 후보면 no_candidate/block_reason 으로 드러낸다. **captured/deterministic
    fixture 를 실 near-match 후보로 위장 금지**(dataset_source=synthetic_fixture 명시·real_fetch=False).
  - **predicted_status 숨김·LLM/embedding 호출 0·본문 미저장·source role guard**(publishable×publishable 만).
  - **production DB 미접촉(옵션 E 금지)·운영 DB upgrade 0·scheduler persist 0**.
  - embedding/LLM adjudicator 는 여전히 **No-Go**(gold/MERGE_GATE 미충족) — interface/eval plan 문서화만.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from itertools import combinations
from typing import Any, Callable, Optional

from backend.app.services.identity_eval_dataset import GOLD_LABELS
from backend.app.services.identity_human_labeling import (
    _PACKET_FORBIDDEN_VERDICT_KEYS,
    _PACKET_INSTRUCTIONS,
    DEFAULT_REVIEWERS_PER_PAIR,
    PACKET_ALLOWED_KEYS,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    ReviewerLabel,
)
from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    augment_agent_schema_with_reviewer_queue,
    build_gold_seed_report,
    build_near_match_reviewer_queue,
    build_reviewer_queue_acquisition_linkage,
    resolve_queue_gold,
)
from backend.app.tools.source_overlap_discovery import (
    _rec,
    build_agent_orchestration_schema,
    discover_overlap,
    fetch_gdelt_overlap_records,
    fetch_rss_overlap_records,
    gdelt_provider_status,
)

# targeted acquisition 기본 source 함대(key-free RSS·같은 영문 world-news 보도권 — 같은 사건 재보도 가능성↑).
_DEFAULT_TARGET_SOURCES: tuple[str, ...] = ("bbc", "aljazeera", "the_verge", "techcrunch")

# 시점창 plan(다출처 같은 사건 재유입 관측창) — GDELT timespan/RSS recency 와 호환.
_TIME_WINDOWS: tuple[str, ...] = ("1d", "7d")

# deterministic fixture record marker — synthetic 이 실 fetch(live_derived)로 위장되는 것을 **코드로** 차단한다
# (call discipline 아님·adversarial MEDIUM-1). build_targeted_same_event_fixture 가 부여하고
# run_targeted_acquisition 이 real_fetch=True 도장을 거부한다(synthetic↔live 봉인의 마지막 한 줄).
_SYNTHETIC_FIXTURE_MARKER = "_synthetic_fixture_origin"

# fixture topic_key → 사람이 읽는 topic 라벨. fixture provider 의 report.topic 이 실 fixture 내용과 어긋나지 않게 강제
# (code-review: --topic 임의값이 fixture 내용과 다른 라벨로 표기되는 것 차단).
_FIXTURE_TOPIC_LABELS = {"central_bank_rate": "central bank rate decision"}


# ── §8: provider capability matrix(오늘의 정직한 query/rate-limit 현실) ────────────────────────────────
def build_provider_capability_matrix(*, gdelt_status: Optional[dict] = None) -> dict:
    """provider 별 query_capability·status·rate_limit_risk·fallback_plan — "어떤 targeting 이 실제 가능한가"를 정직 표면화.

    오늘의 현실(분석 §2-Q4~Q6): GDELT 만 key-free topic+time query 가능하나 429 cooldown(rate_limit_risk high);
    RSS 함대는 key-free 이나 **topic query 불가**(time-window+source-pair targeting 만·latest-N); 나머지는 key 필요
    (미설정). → 실 targeted near-match yield 는 현재 낮다(deterministic fixture 가 운영 경로를 입증)."""
    gdelt_st = (gdelt_status or {}).get("provider_status")
    return {
        "providers": {
            "gdelt": {
                "query_capability": "topic+time_window", "topic_query": True, "auth": "none",
                "status": gdelt_st or "rate_limit_risk_429",
                "rate_limit_risk": "high",   # ADR#57/#58: 5s 간격에도 429·900s cooldown.
                "fallback_plan": "respect cooldown(no tight retry) → RSS time/source-pair targeting → deterministic fixture",
            },
            "rss": {
                "query_capability": "time_window+source_pair", "topic_query": False, "auth": "none",
                "status": "available",
                "rate_limit_risk": "low",    # shared host_rate_gate 참여(no-bypass).
                "fallback_plan": "same news-sphere 다출처 동시 수집(같은 date bucket) → deterministic fixture",
            },
            "key_required": {
                "query_capability": "topic+time_window", "topic_query": True, "auth": "api_key",
                "status": "deferred(key 미설정)", "rate_limit_risk": "unknown",
                "fallback_plan": "키 확보 후 활성(nyt/guardian/newsapi/serper/tavily/exa) — 이번 턴 범위 밖",
            },
            "fixture": {
                "query_capability": "deterministic_demonstration", "topic_query": True, "auth": "none",
                "status": "synthetic_fixture", "rate_limit_risk": "none",
                "fallback_plan": "n/a(실 source 아님 — 운영 경로 입증용·실 near-match 후보 아님)",
            },
        },
        "today_reality": (
            "GDELT 만 key-free topic query 가능하나 429 cooldown(high risk); RSS 는 topic query 불가"
            "(time-window+source-pair targeting 만); 나머지 query provider 는 key 필요(미설정) → 실 targeted "
            "near-match yield 낮음 — deterministic fixture 가 reviewer/gold 운영 경로를 입증(실 후보 아님)"),
        "no_merge_without_gate": True,
    }


# ── §4: targeted acquisition plan(source-pair·topic·time-window + provider capability) ─────────────────
def build_targeted_acquisition_plan(
    *, topic: str = "central bank rate decision", topic_key: str = "central_bank_rate",
    time_window: str = "1d", provider: str = "fixture",
    source_ids: Optional[list[str]] = None, day: str = "2026-06-22",
    gdelt_status: Optional[dict] = None,
) -> dict:
    """targeted same-event acquisition 계획 — source-pair·topic·time-window + provider query capability.

    topic targeting 은 GDELT(blocked)/key-required 만 가능 → provider='rss' 면 topic 은 **수집 의도**로만 기록
    (RSS 는 topic 못 좁힘). source_pair_plan 은 같은 보도권 다출처 조합(같은 사건 재보도 관측 대상)."""
    if provider == "fixture":
        topic = _FIXTURE_TOPIC_LABELS.get(topic_key, topic)   # fixture 라벨↔내용 일치(report.topic 오표기 차단).
    matrix = build_provider_capability_matrix(gdelt_status=gdelt_status)
    cap = matrix["providers"].get(provider, {})
    sids = list(source_ids) if source_ids else list(_DEFAULT_TARGET_SOURCES)
    source_pair_plan = [
        {"source_a": a, "source_b": b, "required_fetch_window": time_window, "no_merge_without_gate": True}
        for a, b in combinations(sids, 2)
    ]
    return {
        "provider": provider,
        "topic": topic,
        "topic_key": topic_key,
        "time_window": time_window,
        "day": day,
        "source_ids": sids,
        "source_pair_plan": source_pair_plan,
        "query_capability": cap.get("query_capability"),
        "provider_status": cap.get("status"),
        "rate_limit_risk": cap.get("rate_limit_risk"),
        "fallback_plan": cap.get("fallback_plan"),
        "topic_targetable": bool(cap.get("topic_query")),
        "no_merge_without_gate": True,
    }


# ── §4: deterministic target fixture(targeted topic+time-window fetch 가 무엇을 산출할지 입증·실 source 아님) ──
def build_targeted_same_event_fixture(
    *, topic_key: str = "central_bank_rate", day: str = "2026-06-22",
) -> list[dict]:
    """targeted topic+time-window fetch 가 **무엇을 산출할지** 입증하는 deterministic fixture(network 0).

    같은 사건(중앙은행 금리결정)을 다출처가 보도: wire verbatim 2(→fingerprint·deterministic 검출) + paraphrase 1
    (→near·adjudicator-zone) + 같은 주제·**다른 사건** 1(→hard-negative band·different-event lean) + community 반응 1
    (anchor 금지·source role guard 로 필터). band 는 실 `_title_tokens`/`_jaccard`/`semantic_identity_fingerprint`
    로 수치 검증(near 2·hard 3·fingerprint 1). title≤512·canonical·published_at·source_id 만(**본문 미저장**).

    **honesty(불변): synthetic_fixture — 실 source behavior 아님·실 near-match 후보 아님. targeted acquisition 의
    detection-layer 운영 경로(discover→queue→reviewer/gold)를 결정론으로 입증할 뿐, 같은 사건 단정·gold 가 아니다.**"""
    if topic_key == "central_bank_rate":
        wire = "Federal Reserve raises benchmark interest rate by quarter point"
        para = "Federal Reserve raises benchmark interest rate by 25 basis points"
        diff = "Federal Reserve official comments on interest rate policy outlook"
    else:
        raise ValueError(f"unknown topic_key {topic_key!r} (현재 지원: central_bank_rate)")
    recs = [
        _rec(source_id="rss:bbc", canonical_url="https://outlet-bbc.test/fed-rate",
             title_or_label=wire, published_at_or_observed_at=day),
        _rec(source_id="rss:aljazeera", canonical_url="https://outlet-aljazeera.test/fed-rate",
             title_or_label=wire, published_at_or_observed_at=day),
        # paraphrase: wire 와 token 대부분 공유하나 정확 집합 불일치(Jaccard 0.545) → near(adjudicator-zone).
        _rec(source_id="rss:techcrunch", canonical_url="https://outlet-techcrunch.test/fed-25bps",
             title_or_label=para, published_at_or_observed_at=day),
        # 같은 주제·**다른 사건**(코멘트/전망 — 금리결정 아님): Jaccard 0.31~0.33 → hard-negative band(different-event lean).
        _rec(source_id="rss:the_verge", canonical_url="https://outlet-theverge.test/fed-outlook",
             title_or_label=diff, published_at_or_observed_at=day),
        # community 반응(wire 와 같은 제목이나 anchor 금지 — reaction layer 로 필터·publishable 아님).
        _rec(record_type="community_signal", source_id="rss:forum",
             canonical_url="https://forum.test/fed-thread",
             title_or_label=wire, published_at_or_observed_at=day),
    ]
    for r in recs:
        r[_SYNTHETIC_FIXTURE_MARKER] = True   # 실 fetch(live_derived) 도장 불가(run_targeted_acquisition 코드 강제).
    return recs


# ── §4: targeted acquisition 실행(실 governed fetch OR 주입 records OR deterministic fixture → discover) ──
def run_targeted_acquisition(
    plan: dict, *, records: Optional[list[dict]] = None, real_fetch: bool = False,
    rss_transport: Optional[Callable[[str, str], Optional[str]]] = None,
    gdelt_transport: Optional[Callable[[str], Optional[str]]] = None,
    host_gate: Any = None, live_network: bool = False,
) -> dict:
    """plan → records → `discover_overlap`. 우선순위: 주입 records > governed fetch(transport/live) > deterministic
    fixture. 실 fetch 가 0 후보면 **block_reason 으로 정직 노출**(fixture 위장 금지·real_fetch True 유지)."""
    provider = plan.get("provider", "fixture")
    provider_status: Optional[dict] = None
    rss_status: Optional[dict] = None
    block_reason: Optional[str] = None
    fixture_used = False
    used_real = real_fetch

    if records is not None:
        acquired = list(records)
        # honesty 강제(adversarial MEDIUM-1): synthetic fixture record 는 real_fetch=True 여도 live_derived 로
        # 도장 못 찍는다 — synthetic↔live 봉인을 call discipline 이 아니라 **코드로** 보장.
        if real_fetch and any(r.get(_SYNTHETIC_FIXTURE_MARKER) for r in acquired):
            used_real = False
    elif provider == "gdelt" and (gdelt_transport is not None or live_network):
        # host_gate 전달 — shared cross-process host floor 를 GDELT 도 honor(ADR#57 우회 재발 방지·code-review).
        provider_status = gdelt_provider_status(
            query=plan.get("topic", "world news"), host_gate=host_gate)
        acquired, fail = fetch_gdelt_overlap_records(
            query=plan.get("topic", "world news"), timespan=plan.get("time_window", "1d"),
            transport=gdelt_transport, provider_status=provider_status)
        used_real = True
        if fail:
            block_reason = fail   # 실 시도였으나 0(429 cooldown 등) — fixture 위장 금지.
    elif provider == "rss" and (rss_transport is not None or live_network):
        acquired, rss_status = fetch_rss_overlap_records(
            source_ids=plan.get("source_ids"), transport=rss_transport, host_gate=host_gate)
        used_real = True
        if not acquired:
            block_reason = "rss_no_records"
    else:
        # deterministic target fixture(synthetic — 실 near-match 후보 아님·운영 경로 입증용).
        acquired = build_targeted_same_event_fixture(
            topic_key=plan.get("topic_key", "central_bank_rate"), day=plan.get("day", "2026-06-22"))
        used_real = False
        fixture_used = True
        if provider != "fixture":
            # rss/gdelt 요청이나 transport/live_network 없음 → fixture 대체. 실 fetch 미시도를 정직 노출(masking 금지).
            block_reason = "real_fetch_not_attempted_fixture_substituted"

    disc = discover_overlap(
        acquired, discovery_mode=f"targeted_{provider}", real_fetch=used_real)
    candidate_count = (
        disc["near_match_below_fingerprint_pairs"] + disc["hard_negative_band_pairs"])
    if candidate_count == 0 and block_reason is None:
        # 후보 0 의 정확한 원인(source scarcity 를 모델 실패로 뭉뚱그리지 않음).
        block_reason = disc["block_reasons"][0] if disc["block_reasons"] else "no_candidate"
    return {
        "discovery": disc,
        "provider": provider,
        "real_fetch": used_real,
        "fixture_used": fixture_used,
        "provider_status": provider_status,
        "rss_status": rss_status,
        "block_reason": block_reason,
        # discovery near+hard(role-filter/synthetic 전). report.candidate_count(reviewer 후보·queue 기준)와 **구분**.
        "discovery_candidate_count": candidate_count,
        "acquired_record_count": len(acquired),
    }


def _acquisition_run_id(plan: dict, acquisition: dict) -> str:
    """결정론 run id(timestamp 아님·재현 가능·테스트 안정). provider/topic/window/real_fetch/candidate_count 로
    유도 — candidate_count 포함으로 같은 plan·다른 record 집합이 같은 id 를 받는 충돌 방지(adversarial LOW-1)."""
    basis = (f"{plan.get('provider')}:{plan.get('topic_key')}:{plan.get('time_window')}:"
             f"{acquisition.get('real_fetch')}:{acquisition.get('block_reason')}:"
             f"{acquisition.get('discovery_candidate_count')}")
    return "tsea:" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _honesty_boundary(*, real_fetch: bool, block_reason: Optional[str], near: int, hard: int) -> str:
    parts = [
        ("real fetch(live_derived)" if real_fetch
         else "deterministic target fixture(synthetic_fixture·실 source 아님·실 near-match 후보 아님)")]
    if block_reason:
        parts.append(f"block_reason={block_reason}(후보 부족 정직 노출)")
    parts.append(f"reviewer 후보 near={near}·hard_negative={hard}")
    parts.append("실 reviewer/gold 0(queue=substrate·packet≠gold·synthetic label 은 경로 입증용)")
    parts.append("near-match 는 reviewer/gold/MERGE_GATE 전까지 병합·같은 사건 단정 0")
    parts.append("production backlog 0·운영 DB 미배포·scheduler persist 0·LLM/embedding 호출 0")
    return " · ".join(parts)


# ── §4: targeted acquisition 통합 report(필수 output 단일 dict) ────────────────────────────────────────
def build_targeted_acquisition_report(
    plan: dict, acquisition: dict, queue: dict, gold_seed: dict, linkage: dict,
    *, acquisition_run_id: str,
) -> dict:
    """§4 필수 output — acquisition_run_id·source_pair_plan·topic/time_window·candidate/near/hard/fingerprint
    count·reviewer_packet_exportable·labeler_prediction_hidden·gold_ready·agreement/conflict_queue_ready·
    merge_allowed False·no_merge_without_gold·no_public_intelligence_unit·dataset_source·honesty_boundary."""
    disc = acquisition["discovery"]
    real = acquisition["real_fetch"]
    near = queue.get("near_positive_count", 0)
    hard = (queue.get("hard_negative_discovery_count", 0)
            + queue.get("hard_negative_synthetic_count", 0))
    exportable = gold_seed.get("reviewer_packet_exportable", False)
    return {
        "acquisition_run_id": acquisition_run_id,
        "provider": plan.get("provider"),
        "source_pair_plan": plan.get("source_pair_plan", []),
        "topic_window": plan.get("topic"),
        "time_window": plan.get("time_window"),
        "candidate_count": near + hard,                  # reviewer 후보 = near positive + hard negative.
        "near_positive_count": near,
        "hard_negative_count": hard,
        "fingerprint_overlap_count": disc.get("fingerprint_overlap_pairs", 0),
        "reviewer_packet_exportable": exportable,
        "labeler_prediction_hidden": gold_seed.get("labeler_prediction_hidden", True),
        "raw_body_included": gold_seed.get("raw_body_included", False),
        # readiness = **경로**가 준비됐는가(실 데이터 보유 아님). gold_ready 만 실 gold 있을 때 True.
        "gold_ready": gold_seed.get("gold_ready", False),
        "agreement_ready": exportable,                   # packet 있으면 ≥2 reviewer 라벨 시 agreement 측정 가능.
        "conflict_queue_ready": exportable,              # conflict→human adjudication 경로 배선(검증됨).
        "block_reason": acquisition.get("block_reason"),
        "real_fetch": real,
        "dataset_source": SOURCE_LIVE if real else SOURCE_SYNTHETIC,
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "llm_invoked": False,
        "next_fetch_plan": linkage.get("next_fetch_plan"),
        "honesty_boundary": _honesty_boundary(
            real_fetch=real, block_reason=acquisition.get("block_reason"), near=near, hard=hard),
    }


# ── §5: reviewer operating checklist(실 reviewer 투입 전 운영 점검표·구조적 verify) ──────────────────────
_REVIEWER_INSTRUCTION = (
    "같은 사건인지 판단하라 — **모델 예측은 보이지 않는다**(predicted_status withheld). "
    "title/canonical_url/published/source role 만 보고 판단하라(raw body 없음). "
    "확신이 없으면 ambiguous/insufficient 로 남겨라(추측 금지). "
    "community 반응은 사건 anchor 가 아니다(reaction layer). market/catalog 도 anchor 가 아니다. "
    "gold 확정 전 병합은 없다(no merge without MERGE_GATE)."
)


def build_reviewer_operating_checklist(
    queue: dict, *, dataset_source: str,
    packet_source: str = "targeted_same_event_acquisition", packet_id: Optional[str] = None,
) -> dict:
    """§5 reviewer operating checklist — 실 reviewer 투입 직전 점검표. hidden_prediction/raw_body absent 를
    **구조적으로 검증**(하드코딩 True 아님): labeler_view·packet_rows 에 verdict/bucket/raw 키 부재 확인."""
    packet_rows = queue.get("packet_rows") or []
    labeler_view = queue.get("labeler_view") or []
    # hidden prediction: labeler view 에 verdict/bucket 누출 0 + packet row 에 verdict 누출 0.
    hidden_ok = all(
        not (set(v) & _PACKET_FORBIDDEN_VERDICT_KEYS) and "sampling_bucket" not in v
        for v in labeler_view
    ) and all(not (set(r) & _PACKET_FORBIDDEN_VERDICT_KEYS) for r in packet_rows)
    # raw body absent: 모든 packet row 키가 allowlist 안 + 원문/PII 키 부재.
    _raw_keys = {"body", "content", "raw_payload", "text", "author", "email"}
    raw_absent_ok = all(
        set(r) <= PACKET_ALLOWED_KEYS and not (set(r) & _raw_keys) for r in packet_rows)
    return {
        "packet_id": packet_id or queue.get("packet_id"),
        "packet_source": packet_source,
        "dataset_source": dataset_source,
        "candidate_count": len(queue.get("queue_pair_ids") or []),
        "assignment_count": len(packet_rows),
        "hidden_prediction_verified": hidden_ok,
        "raw_body_absent_verified": raw_absent_ok,
        "evidence_fields": ["title_left", "title_right", "source_type_left", "source_type_right",
                            "observed_at_left", "observed_at_right", "canonical_url_left",
                            "canonical_url_right", "instructions"],
        "reviewer_instruction": _REVIEWER_INSTRUCTION,
        "packet_machine_instruction": _PACKET_INSTRUCTIONS,
        "allowed_labels": sorted(GOLD_LABELS),
        "conflict_policy": "2+ reviewer 불일치·미adjudication → conflict(needs_review·자동 gold 금지)",
        "agreement_policy": "2+ reviewer 전원 동일 → agreed(gold). agreement_rate = 최빈 label / reviewer 수",
        "adjudication_policy": "conflict 는 **사람 lead** 판정만 gold(adjudicator_kind=human·LLM-as-judge 금지)",
        "gold_promotion_policy": "agreed/adjudicated 만 gold 승격. single reviewer=insufficient(gold 아님)",
        "merge_policy": "prohibited until MERGE_GATE(precision≥0.98·FPR≤0.01·hard_neg_fp=0·KO≥0.98)",
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
    }


# ── §6: gold calibration simulation(unanimous/conflict/single/adjudicated 경로 검증·production gold 0) ──
def _sim_label(pair_id: str, reviewer_id: str, label: str) -> ReviewerLabel:
    """gold 경로 검증용 **synthetic** human reviewer label(실 reviewer 아님·dataset_source=synthetic_fixture)."""
    return ReviewerLabel(
        pair_id=pair_id, reviewer_id=reviewer_id, review_round=1, label=label,
        label_confidence="high", reviewed_at="2026-06-23T00:00:00Z", language="en",
        source_type_left="article", source_type_right="article",
        title_left="sim title left", title_right="sim title right",
        observed_at_left="2026-06-22", observed_at_right="2026-06-22",
        dataset_source=SOURCE_SYNTHETIC)


def simulate_gold_calibration() -> dict:
    """§6 gold path 검증 — **synthetic** reviewer label 로 5 경로(unanimous same/different·single·conflict·
    adjudicated)를 `resolve_queue_gold` 로 입증. **production gold 아님**(전부 synthetic_fixture). 같은 사건 단정·
    병합 0. report: simulated_gold_count·conflict_count·insufficient_count·production_gold_count=0·merge_allowed=False."""
    labels = [
        _sim_label("sim:same", "rev_a", "same_event"),       # unanimous same → gold
        _sim_label("sim:same", "rev_b", "same_event"),
        _sim_label("sim:diff", "rev_a", "different_event"),  # unanimous different → gold
        _sim_label("sim:diff", "rev_b", "different_event"),
        _sim_label("sim:single", "rev_a", "same_event"),     # single → insufficient(gold 아님)
        _sim_label("sim:conflict", "rev_a", "same_event"),   # conflict·미adjudication → needs_review
        _sim_label("sim:conflict", "rev_b", "different_event"),
        _sim_label("sim:adj", "rev_a", "same_event"),        # conflict + human adjudication → adjudicated gold
        _sim_label("sim:adj", "rev_b", "different_event"),
    ]
    adjudications = {
        "sim:adj": {"label": "same_event", "adjudicator_kind": "human", "adjudicated_by": "lead_sim"}}
    resolved = resolve_queue_gold(labels, adjudications=adjudications)
    gold_pairs = resolved["gold_pairs"]
    # production gold = live_derived gold 만(synthetic 은 0 — readiness 부풀리기 금지).
    production_gold = sum(1 for gp in gold_pairs if gp.dataset_source == SOURCE_LIVE)
    insufficient = sum(
        1 for r in resolved["resolved"] if r.agreement_status == "insufficient_reviews")
    return {
        "scenarios": ["unanimous_same", "unanimous_different", "single_reviewer", "conflict",
                      "human_adjudicated"],
        "simulated_gold_count": resolved["gold_count"],          # 3(same·different·adjudicated)
        "conflict_count": resolved["conflict_count"],            # 1
        "insufficient_count": insufficient,                      # 1
        "agreement_rate": resolved["reviewer_agreement"]["agreement_rate"],
        "production_gold_count": production_gold,                # 0(전부 synthetic_fixture)
        "dataset_source": SOURCE_SYNTHETIC,
        "path_verified": (resolved["gold_count"] >= 1 and resolved["conflict_count"] >= 1
                          and insufficient >= 1 and production_gold == 0),
        "merge_allowed": False,
        "no_merge_without_gate": True,
    }


# ── §8: targeted acquisition linkage(reviewer/gold value + provider capability 연결) ──────────────────
def build_targeted_acquisition_linkage(
    discovery: dict, queue: dict, plan: dict, *, provider_matrix: Optional[dict] = None,
) -> dict:
    """§8 — 기존 `build_reviewer_queue_acquisition_linkage`(source-pair reviewer/gold value)에 expected yield/
    reviewer load + provider capability(query/status/rate_limit_risk/fallback)를 더해 **목적 기반 수집**으로 steer."""
    base = build_reviewer_queue_acquisition_linkage(discovery, queue)
    matrix = provider_matrix or build_provider_capability_matrix()
    cap = matrix["providers"].get(plan.get("provider"), {})
    near = discovery.get("near_match_below_fingerprint_pairs", 0)
    hard = discovery.get("hard_negative_band_pairs", 0)
    fp = discovery.get("fingerprint_overlap_pairs", 0)
    rpp = queue.get("reviewers_per_pair", DEFAULT_REVIEWERS_PER_PAIR)
    return {
        **base,
        "expected_near_match_yield": near,
        "expected_hard_negative_yield": hard,
        "expected_fingerprint_yield": fp,
        "expected_gold_value": "high" if near > 0 else "none",
        "expected_reviewer_load": (near + hard) * rpp,   # packet assignment 부하(reviewer 명·round).
        "query_capability": cap.get("query_capability"),
        "provider_status": cap.get("status"),
        "rate_limit_risk": cap.get("rate_limit_risk"),
        "fallback_plan": cap.get("fallback_plan"),
        "topic_targetable": bool(cap.get("topic_query")),
        "no_merge_without_gate": True,
    }


# ── §9: Agent orchestration schema(targeted planning·merge 불가·LLM No-Go) ────────────────────────────
def build_targeted_agent_schema(
    discovery: dict, queue: dict, gold_seed: dict, linkage: dict, gold_sim: dict, plan: dict,
) -> dict:
    """§9 — Agent 가 source-pair/topic-window/reviewer packet priority/hard-negative sampling/gold value 를
    **계획**할 수 있게 보강. Agent 불가: 같은 사건 확정·merge·public IU·community/market anchor. LLM 0·embedding No-Go."""
    base = augment_agent_schema_with_reviewer_queue(
        build_agent_orchestration_schema(discovery), queue, gold_seed, linkage)
    return {
        **base,
        "recommended_topic_windows": list(_TIME_WINDOWS),
        "targeted_topic": plan.get("topic"),
        "query_capability": linkage.get("query_capability"),
        "rate_limit_risk": linkage.get("rate_limit_risk"),
        "expected_reviewer_load": linkage.get("expected_reviewer_load"),
        "gold_calibration_path_verified": gold_sim.get("path_verified"),
        "production_gold_count": gold_sim.get("production_gold_count"),   # 0(정직).
        "uncertainty": {
            "adjudicator_zone_unverified": discovery.get("adjudicator_zone_pairs", 0),
            "real_near_match_candidates": "low(untargeted RSS overlap 0·GDELT 429·fixture 입증)",
            "gold_calibration": "synthetic path 검증만(실 gold 0)",
        },
        "agent_can_plan": ["recommended_source_pairs", "recommended_topic_windows",
                           "reviewer_packet_priority", "hard_negative_sampling_plan",
                           "expected_gold_value", "expected_merge_gate_value", "next_fetch_plan"],
        "agent_cannot": ["같은 사건 확정", "merge 실행", "public Intelligence Unit 생성",
                         "community/market/catalog 를 event anchor 로 사용"],
        "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go(이번 턴 호출 0).
    }


# ── 최상위 orchestrator(plan→acquisition→queue→report+checklist+gold sim+linkage+agent schema) ────────
def run_targeted_same_event_operating_readiness(
    *, topic: str = "central bank rate decision", topic_key: str = "central_bank_rate",
    time_window: str = "1d", provider: str = "fixture",
    source_ids: Optional[list[str]] = None, records: Optional[list[dict]] = None,
    real_fetch: bool = False, rss_transport: Optional[Callable[[str, str], Optional[str]]] = None,
    gdelt_transport: Optional[Callable[[str], Optional[str]]] = None, host_gate: Any = None,
    live_network: bool = False, include_synthetic_hard_negatives: bool = False,
    reviewers: Optional[list[str]] = None, packet_id: str = "targeted_near_match_pkt",
) -> dict:
    """ADR#60 단일 진입 — targeted acquisition → near-match reviewer/gold queue → 운영 readiness 통합 산출.

    기본(provider='fixture')은 network 0·deterministic(synthetic_fixture). provider='rss'/'gdelt' + live_network/
    transport 면 실 governed fetch(live_derived·실 후보 0 면 block_reason 정직). 병합·LLM·DB write 0."""
    plan = build_targeted_acquisition_plan(
        topic=topic, topic_key=topic_key, time_window=time_window, provider=provider,
        source_ids=source_ids)
    acq = run_targeted_acquisition(
        plan, records=records, real_fetch=real_fetch, rss_transport=rss_transport,
        gdelt_transport=gdelt_transport, host_gate=host_gate, live_network=live_network)
    disc = acq["discovery"]
    queue = build_near_match_reviewer_queue(
        disc, packet_id=packet_id, reviewers=reviewers,
        include_synthetic_hard_negatives=include_synthetic_hard_negatives)
    gold_seed = build_gold_seed_report(disc, queue)
    linkage = build_targeted_acquisition_linkage(disc, queue, plan)
    gold_sim = simulate_gold_calibration()
    run_id = _acquisition_run_id(plan, acq)
    report = build_targeted_acquisition_report(
        plan, acq, queue, gold_seed, linkage, acquisition_run_id=run_id)
    checklist = build_reviewer_operating_checklist(
        queue, dataset_source=report["dataset_source"], packet_id=packet_id)
    agent_schema = build_targeted_agent_schema(disc, queue, gold_seed, linkage, gold_sim, plan)
    return {
        "plan": plan,
        "acquisition": {k: v for k, v in acq.items() if k != "discovery"},
        "queue": queue,
        "gold_seed_report": gold_seed,
        "report": report,
        "reviewer_operating_checklist": checklist,
        "gold_calibration_simulation": gold_sim,
        "acquisition_linkage": linkage,
        "agent_schema": agent_schema,
    }


# ── CLI(기본 fixture·network 0·deterministic; --live + --provider 로 실 governed fetch opt-in) ──────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("targeted same-event acquisition → near-match reviewer/gold operating readiness "
                     "(ADR#60·병합 0·LLM 0·DB write 0; 기본 deterministic fixture·network 0)."))
    parser.add_argument("--provider", choices=["fixture", "rss", "gdelt"], default="fixture",
                        help="acquisition provider. 기본 fixture(synthetic·network 0).")
    parser.add_argument("--topic", default="central bank rate decision", help="targeted topic(수집 의도).")
    parser.add_argument("--time-window", default="1d", help="time window(1d/7d).")
    parser.add_argument("--live", action="store_true",
                        help="실 governed fetch(opt-in·network·CI 아님). --provider rss/gdelt 와 함께.")
    parser.add_argument("--synthetic-hard-negatives", action="store_true",
                        help="trap-zone synthetic hard negative 포함(calibration·synthetic_fixture 명시).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    host_gate = None
    if ns.live and ns.provider == "rss":
        try:
            from pathlib import Path as _P

            from ingestion.orchestration.host_rate_gate import HostRateGate
            host_gate = HostRateGate(state_path=_P("ingestion/outputs/state/host_rate_gate.json"))
        except Exception:
            host_gate = None

    out = run_targeted_same_event_operating_readiness(
        topic=ns.topic, time_window=ns.time_window, provider=ns.provider,
        live_network=ns.live, host_gate=host_gate,
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)
    rep = out["report"]
    chk = out["reviewer_operating_checklist"]
    sim = out["gold_calibration_simulation"]
    link = out["acquisition_linkage"]
    print(f"- run_id={rep['acquisition_run_id']} provider={rep['provider']} "
          f"real_fetch={rep['real_fetch']} dataset_source={rep['dataset_source']}")
    print(f"- candidates: total={rep['candidate_count']} near={rep['near_positive_count']} "
          f"hard_neg={rep['hard_negative_count']} fingerprint={rep['fingerprint_overlap_count']} "
          f"block_reason={rep['block_reason']}")
    print(f"- readiness: packet_exportable={rep['reviewer_packet_exportable']} "
          f"labeler_prediction_hidden={rep['labeler_prediction_hidden']} gold_ready={rep['gold_ready']} "
          f"agreement_ready={rep['agreement_ready']} conflict_queue_ready={rep['conflict_queue_ready']}")
    print(f"- checklist: hidden_prediction_verified={chk['hidden_prediction_verified']} "
          f"raw_body_absent_verified={chk['raw_body_absent_verified']} "
          f"allowed_labels={chk['allowed_labels']} merge_policy={chk['merge_policy']!r}")
    print(f"- gold_sim: simulated_gold={sim['simulated_gold_count']} conflict={sim['conflict_count']} "
          f"insufficient={sim['insufficient_count']} production_gold={sim['production_gold_count']} "
          f"path_verified={sim['path_verified']}")
    print(f"- linkage: expected_near={link['expected_near_match_yield']} "
          f"expected_hard={link['expected_hard_negative_yield']} reviewer_load={link['expected_reviewer_load']} "
          f"query_capability={link['query_capability']} rate_limit_risk={link['rate_limit_risk']}")
    print(f"- next_fetch_plan: {rep['next_fetch_plan']}")
    print(f"- honesty_boundary: {rep['honesty_boundary']}")
    print(f"- merge_allowed={rep['merge_allowed']} no_public_IU={rep['no_public_intelligence_unit']} "
          f"llm_invoked={rep['llm_invoked']} embedding_adjudicator={out['agent_schema']['embedding_llm_adjudicator']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
