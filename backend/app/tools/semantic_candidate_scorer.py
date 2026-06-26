"""ADR#65 — offline/gated semantic candidate scorer (병합 0·LLM 0·embedding 0·predicted_status 숨김).

ADR#64 가 실 key 로 입증한 다음 병목: cross-source pair 는 생겼으나(Guardian+NYT cross_source_pair 100) **deterministic
title-Jaccard 가 0 검출**(no_title_overlap). 즉 source scarcity → **detection scarcity** 로 문제가 재분해됐다. 이 모듈은
그 0 을 **버리지도 병합하지도 않고** semantic candidate scorer 로 점수화해 reviewer queue **prioritization** 으로만 넘긴다.

핵심(정직 — 과대주장 금지):
  - 이번 턴 진전은 **candidate prioritization substrate** 이지 **validated adjudicator** 가 아니다.
  - deterministic 0 은 semantic scoring 필요성을 보여주지만, **semantic score 는 gold 전까지 provisional** 이다.
  - score 는 truth 가 아니라 **reviewer 주목 우선순위 신호**다. threshold 로 같은 사건을 단정하지 않는다(top-k rank 만).
  - 어떤 mode 도 gold/MERGE_GATE 없이 병합·같은 사건 확정을 하지 않는다(merge_allowed=False 불변).

scorer_mode(§4):
  - deterministic_scaffold: title-Jaccard×date_factor(`cross_source_dedup._jaccard`/`_title_tokens` 재사용·date_factor 는
    `semantic_identity_adjudicator` 와 동일 형태로 정합). ADR#64 에서 0 을 낸
    **바로 그 신호** — 정직하게 100쌍이 sub-floor→candidate 0 임을 드러낸다(recall 개선 주장 0).
  - fake_semantic: **결정론 paraphrase-tolerant proxy**(char-bigram Dice + token containment). 실 embedding 아님·검증된
    recall 아님 — top-k/queue 배관(plumbing)을 테스트하는 **scaffold** 일 뿐(network 0).
  - embedding_opt_in / llm_opt_in: **interface only**(injection-only). 실 client 미배선(No-Go) — explicit opt-in +
    secret-safe credential probe + `scorer_fn` 주입이 모두 있어야 호출. 기본 경로는 호출 0.

경계(불변·상속):
  - **no merge / no public IU / no DB write / no LLM·embedding 실호출**(기본). DB·EventLink·adjudication 미접근.
  - **secret 값 0**: opt-in readiness 는 `probe_env_var`(present/missing boolean·값 미열람)만. key 값 미출력.
  - **labeler-facing 숨김**: score/rationale/model metadata 는 internal-only. reviewer queue 는 score 없는 pair record 만
    투입 — `validate_labeling_packet` 가 score/predicted_status 누출을 **fail-loud** 로 구조적 차단.
  - **source role guard**: publishable×publishable(official/article)만 후보. community/market/catalog anchor 금지.
  - **본문 미저장**: title 헤드라인(≤512)·canonical·observed_at·source_type 만.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Optional

from backend.app.services.identity_eval_dataset import MERGE_GATE
from backend.app.tools.near_match_reviewer_queue import (
    build_gold_seed_report,
    build_near_match_reviewer_queue,
)
from backend.app.tools.source_overlap_discovery import discover_overlap
from ingestion.orchestration.cross_source_dedup import _date_bucket, _jaccard, _title_tokens

_SCORER_NAME = "semantic_candidate_scorer"

# scorer mode(§4).
MODE_DETERMINISTIC = "deterministic_scaffold"
MODE_FAKE = "fake_semantic"
MODE_EMBEDDING = "embedding_opt_in"
MODE_LLM = "llm_opt_in"
SCORER_MODES = frozenset({MODE_DETERMINISTIC, MODE_FAKE, MODE_EMBEDDING, MODE_LLM})
_OFFLINE_MODES = frozenset({MODE_DETERMINISTIC, MODE_FAKE})   # network 0·실호출 0.
_OPT_IN_MODES = frozenset({MODE_EMBEDDING, MODE_LLM})          # explicit opt-in + credential + scorer_fn 필요.

# opt-in mode → (env var 이름, 용도). .env.example 단일 출처(OPENAI_API_KEY 가 LLM·embedding 공용). 값 미열람.
_OPT_IN_ENV_VAR = {MODE_EMBEDDING: "OPENAI_API_KEY", MODE_LLM: "OPENAI_API_KEY"}

DEFAULT_TOP_K = 10
_MAX_PAIRS = 2000   # bounded(폭주 차단; candidate_pairs 는 bounded records 의 pairwise 라 이미 유한).

_PUBLISHABLE_SOURCE_TYPES = frozenset({"official", "article"})

# §7/§9 — embedding/LLM scorer 정책(No-Go for merge·문서/계약 고정). MERGE_GATE 는 identity_eval_dataset 단일 출처.
EMBEDDING_LLM_SCORER_POLICY = {
    "default": "no-network/fake scorer (실 embedding/LLM 호출 0)",
    "opt_in_requires": [
        "explicit opt-in flag",
        "env var readiness present via secret-safe probe (값 미열람)",
        "`.env` value not read/output",
        "bounded pair count",
        "no raw body in prompt",
        "no DB write",
        "no merge",
        "no public Intelligence Unit",
        "output internal-only (labeler-facing hidden)",
        "scorer_fn 주입(실 client 는 이번 턴 미배선·No-Go)",
    ],
    "score_is": "prioritization signal (NOT truth·NOT same-event 확정·NOT threshold merge)",
    "status": "No-Go for merge (gold/MERGE_GATE 미충족·이번 턴 실호출 0)",
    "forbidden": [
        "같은 사건 단정", "merge 실행", "public Intelligence Unit 생성",
        "gold 없이 threshold/precision 개선 주장", "community/market/catalog 를 event anchor 로 사용",
        "secret 값 출력", "labeler 에게 score/rationale 노출",
    ],
}

# §9 — Agent orchestration: scorer 로 무엇을 계획할 수 있고 무엇을 못 하는가(merge 불가 명문화).
SCORER_AGENT_CONTRACT = {
    "can_plan": [
        "cross-source pair scoring", "semantic candidate prioritization", "reviewer packet priority",
        "hard negative sampling", "expected gold value", "next reviewer action", "next provider action",
    ],
    "cannot": [
        "semantic score 를 truth 로 사용", "같은 사건 확정", "merge 실행", "public Intelligence Unit 생성",
        "community reaction 을 event anchor 로 사용", "market/catalog 를 event anchor 로 사용",
        "secret 을 읽거나 출력",
    ],
    "semantic_prioritization": True,
    "no_truth_assertion": True,
    "no_merge_without_gate": True,
    "no_public_intelligence_unit": True,
    "secret_boundary": "env var 이름만·값 미열람·prompt 에 secret/raw body 금지",
}

_NEXT_ACTION = {
    "scorer_disabled": ("opt-in scorer 미활성 — offline mode(deterministic_scaffold/fake_semantic) 사용 또는 "
                        "opt_in=True + scorer_fn 주입(실 embedding/LLM client 는 No-Go·미배선)"),
    "missing_credentials": "set the opt-in provider env var in .env (secret 커밋 금지·값 미출력)",
    "env_not_loaded": "create .env at repo root from .env.example and set the opt-in provider env var (값 미출력)",
    "provider_error": "opt-in credential 은 present 이나 실 client 미배선(No-Go) — scorer_fn 주입 필요(이번 턴 실호출 0)",
    "rate_limited": "respect provider cooldown (no tight retry)",
    "no_pairs": "no publishable cross-URL same-date pair — broaden topic/window 또는 2nd provider 보강(ADR#64)",
    "no_candidates": "scored pairs 는 있으나 top-k reviewer candidate 0 — top_k>0 확인·role guard 통과 pair 부재",
}


def _cred_state(probe: dict) -> str:
    """probe → credential 상태(secret 0). present / missing_credentials(.env 있음·키 없음) / env_not_loaded(.env 부재)."""
    if probe.get("credential_present"):
        return "present"
    return "missing_credentials" if probe.get("env_file_present") else "env_not_loaded"


def _default_env_probe(var_name: str) -> dict:
    """secret-safe env probe(없으면 fail-closed: present 추측 금지)."""
    try:
        from ingestion.core.env_loader import probe_env_var
        return probe_env_var(var_name)
    except Exception:
        return {"var_name": var_name, "credential_present": False,
                "env_file_present": False, "declared_in_example": False}


# ── §5: cross-source pair → SemanticPairInput 정규화(본문 미저장·secret 0) ─────────────────────────
def normalize_candidate_pair(
    pair: dict, *, topic: Optional[str], time_window: Optional[str],
    provider_a: Optional[str], provider_b: Optional[str],
    dataset_source: Optional[str], provenance: Optional[str],
) -> dict:
    """discover_overlap candidate/near/hard pair(`_near_pair_record`) → §5 SemanticPairInput(scorer 입력).

    pair 가 이미 보존한 source_id/source_type(role)/title/canonical/observed_at 를 그대로 옮기고, smoke 맥락
    (topic/time_window/provider/provenance)만 주입한다(재구현 0·본문 미포함)."""
    return {
        "pair_id": pair.get("pair_id"),
        "source_a": pair.get("source_id_left"),
        "source_b": pair.get("source_id_right"),
        "provider_a": provider_a,
        "provider_b": provider_b,
        "source_role_a": pair.get("source_type_left"),
        "source_role_b": pair.get("source_type_right"),
        "title_a": pair.get("title_left"),
        "title_b": pair.get("title_right"),
        "canonical_url_a": pair.get("canonical_url_left"),
        "canonical_url_b": pair.get("canonical_url_right"),
        "published_at_a": pair.get("observed_at_left"),
        "published_at_b": pair.get("observed_at_right"),
        "topic": topic,
        "time_window": time_window,
        "dataset_source": dataset_source,
        "provenance": provenance,
    }


def _role_compatible(inp: dict) -> bool:
    """publishable×publishable(official/article)만 후보(source role guard·community/market/catalog anchor 금지)."""
    return inp.get("source_role_a") in _PUBLISHABLE_SOURCE_TYPES and \
        inp.get("source_role_b") in _PUBLISHABLE_SOURCE_TYPES


def _is_cross_source(pair: dict) -> bool:
    """candidate pair 가 cross-source 인가(source_id 상이). cross_source_live_overlap_smoke 본경로 가드와 동일 —
    same-source(guardian↔guardian·nyt↔nyt) within-publisher near-dup 을 scorer 입력에서 제외해 single-source 둔갑 차단."""
    return bool(pair.get("source_id_left")) and pair.get("source_id_left") != pair.get("source_id_right")


def _date_factor(inp: dict) -> float:
    """same date bucket → 1.0·아니면 0.5(adjudicator date_factor 와 정합). candidate_pairs 는 same-date 라 통상 1.0."""
    da = _date_bucket({"published_at_or_observed_at": inp.get("published_at_a")})
    db = _date_bucket({"published_at_or_observed_at": inp.get("published_at_b")})
    return 1.0 if (da and da == db) else 0.5


# ── scorer mode별 점수(전부 결정론·offline; opt-in 은 주입 scorer_fn) ───────────────────────────────
def _score_deterministic(inp: dict) -> tuple[float, str, dict]:
    """title-Jaccard×date_factor — ADR#64 에서 0 을 낸 **바로 그 deterministic 신호**(정직: recall 개선 주장 0).

    primitive 는 `cross_source_dedup._jaccard`/`_title_tokens` 재사용(adjudicator·discover_overlap 과 동일 토큰화);
    date_factor 는 `semantic_identity_adjudicator` 와 **동일 형태**(1.0/0.5)로 정합(분류기 자체는 status 산출이라
    미import — 여기선 0..1 ranking score 만 필요)."""
    ja = _jaccard(_title_tokens(inp.get("title_a")), _title_tokens(inp.get("title_b")))
    score = round(ja * _date_factor(inp), 6)
    return score, "deterministic_title_jaccard", {
        "title_token_jaccard": round(ja, 6),
        "note": "same signal as deterministic fingerprint band — no recall gain over ADR#64 (정직·provisional)",
    }


def _char_bigrams(s: Optional[str]) -> set:
    s = (s or "").lower()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _dice(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


def _containment(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _score_fake_semantic(inp: dict) -> tuple[float, str, dict]:
    """**결정론 paraphrase-tolerant proxy**(char-bigram Dice + token containment). 실 embedding 아님·검증 recall 아님.

    paraphrase(어순 변경·부분집합)에 deterministic Jaccard 보다 관대 → top-k/queue 배관을 테스트하는 **scaffold** 일 뿐
    (network 0). score 를 truth/recall 로 해석 금지(scorer_mode=fake_semantic 로 영구 표기)."""
    dice = _dice(_char_bigrams(inp.get("title_a")), _char_bigrams(inp.get("title_b")))
    cont = _containment(_title_tokens(inp.get("title_a")), _title_tokens(inp.get("title_b")))
    score = round((0.5 * dice + 0.5 * cont) * _date_factor(inp), 6)
    return score, "fake_semantic_scaffold", {
        "char_bigram_dice": round(dice, 6),
        "token_containment": round(cont, 6),
        "note": "DETERMINISTIC SCAFFOLD — not a real embedding·not validated recall·plumbing test only",
    }


def _score_opt_in(inp: dict, scorer_mode: str, scorer_fn: Callable[[dict], float]) -> tuple[float, str, dict]:
    """injection-only opt-in scorer(embedding/LLM). scorer_fn 은 input dict→float[0,1]. raw body 미전달(title 헤드라인만)."""
    raw = scorer_fn(inp)
    score = max(0.0, min(1.0, float(raw)))
    return round(score, 6), scorer_mode, {
        "note": "opt-in provisional score (uncalibrated·No-Go for merge)",
        "model_metadata": "injected scorer_fn (실 client·prompt·secret 은 caller 책임·본문 미전달)",
    }


def build_pair_score(
    inp: dict, *, scorer_mode: str, scorer_fn: Optional[Callable[[dict], float]] = None,
) -> dict:
    """§5 SemanticPairScore — provisional·internal-only·labeler_visible False·merge_allowed False·requires_gold True."""
    if scorer_mode == MODE_DETERMINISTIC:
        score, stype, reasons = _score_deterministic(inp)
    elif scorer_mode == MODE_FAKE:
        score, stype, reasons = _score_fake_semantic(inp)
    elif scorer_mode in _OPT_IN_MODES:
        if scorer_fn is None:
            raise ValueError("opt-in scorer_mode requires scorer_fn injection (실 client 미배선·No-Go)")
        score, stype, reasons = _score_opt_in(inp, scorer_mode, scorer_fn)
    else:
        raise ValueError(f"unknown scorer_mode: {scorer_mode!r} (allowed: {sorted(SCORER_MODES)})")
    return {
        "pair_id": inp.get("pair_id"),
        "score": score,
        "score_type": stype,
        "scorer_mode": scorer_mode,
        "confidence": "uncalibrated",       # gold 부재 → calibration 불가(정직·Q11). 확률로 해석 금지.
        "reasons_internal": reasons,         # internal-only(labeler 미노출).
        "model_metadata_internal": {"scorer_mode": scorer_mode, "score_type": stype},
        "labeler_visible": False,
        "merge_allowed": False,
        "requires_gold": True,
        "requires_merge_gate": True,
    }


def score_candidate_pairs(
    inputs: list[dict], *, scorer_mode: str,
    scorer_fn: Optional[Callable[[dict], float]] = None, max_pairs: int = _MAX_PAIRS,
) -> list[dict]:
    """SemanticPairInput 목록 → SemanticPairScore 목록(bounded·internal-only). role guard 통과분만 점수화."""
    out: list[dict] = []
    for inp in inputs[:max_pairs]:
        if not _role_compatible(inp):
            continue
        out.append(build_pair_score(inp, scorer_mode=scorer_mode, scorer_fn=scorer_fn))
    return out


def _score_distribution(scores: list[dict]) -> dict:
    """score 분포(band 카운트 + min/max/mean). truth 아님·prioritization 분포만."""
    vals = [s["score"] for s in scores]
    bands = {"0.0-0.2": 0, "0.2-0.5": 0, "0.5-0.8": 0, "0.8-1.0": 0}
    for v in vals:
        if v < 0.2:
            bands["0.0-0.2"] += 1
        elif v < 0.5:
            bands["0.2-0.5"] += 1
        elif v < 0.8:
            bands["0.5-0.8"] += 1
        else:
            bands["0.8-1.0"] += 1
    return {
        "bands": bands,
        "min": round(min(vals), 6) if vals else None,
        "max": round(max(vals), 6) if vals else None,
        "mean": round(sum(vals) / len(vals), 6) if vals else None,
    }


def select_top_k(scores: list[dict], *, top_k: int, min_score: float = 0.0) -> list[str]:
    """top-k pair_id by score desc(동률 시 pair_id asc·결정론). **threshold 아닌 rank**(같은 사건 단정 0·prioritization).

    min_score(기본 0.0): score > min_score 인 pair 만 — score==0(어휘 overlap 전무)인 zero-signal pair 를 reviewer
    노이즈로 보내지 않기 위한 **신호 유무** 컷일 뿐, calibrated same-event threshold 가 아니다(merge 단정 0·gold 없음)."""
    eligible = [s for s in scores if s["score"] > min_score]
    ranked = sorted(eligible, key=lambda s: (-s["score"], str(s.get("pair_id"))))
    return [str(s["pair_id"]) for s in ranked[:max(0, top_k)]]


# ── §4/§6: scorer → top-k → reviewer queue(score hidden) 통합 ────────────────────────────────────
def run_semantic_candidate_scoring(
    *, records: Optional[list[dict]] = None, discovery: Optional[dict] = None,
    scorer_mode: str = MODE_DETERMINISTIC, top_k: int = DEFAULT_TOP_K,
    topic: Optional[str] = None, time_window: Optional[str] = None,
    provider_a: Optional[str] = None, provider_b: Optional[str] = None,
    dataset_source: Optional[str] = None, provenance: Optional[str] = None,
    opt_in: bool = False, scorer_fn: Optional[Callable[[dict], float]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None,
    reviewers: Optional[list[str]] = None, packet_id: str = "semantic_candidate_pkt",
    max_pairs: int = _MAX_PAIRS, cross_source_only: bool = True,
) -> dict:
    """§4 offline/gated semantic candidate scoring scaffold. records 또는 discovery 중 하나 필요.

    gate(fail-closed): opt-in mode 인데 opt_in=False→scorer_disabled; opt_in 이나 credential 부재→missing_credentials/
    env_not_loaded; credential present 이나 scorer_fn 미주입→provider_error(실 client 미배선·No-Go). offline mode
    (deterministic_scaffold/fake_semantic)는 gate 통과(network 0). candidate_pairs 0→no_pairs. 점수화 후 top-k rank
    (threshold 아님)→ top-k near + hard-negative band → build_near_match_reviewer_queue(score 없는 pair 만 투입·
    labeler-facing 숨김·validate fail-loud). 병합·LLM·embedding 실호출·DB write·public IU 0."""
    if scorer_mode not in SCORER_MODES:
        raise ValueError(f"unknown scorer_mode: {scorer_mode!r} (allowed: {sorted(SCORER_MODES)})")
    probe = env_probe_fn or _default_env_probe
    network_used = False
    block_reasons: list[str] = []
    credential_status: Optional[str] = None
    opt_in_env_var = _OPT_IN_ENV_VAR.get(scorer_mode)   # 이름만(.env.example 단일 출처)·값 미열람.

    # discovery 준비(records 주면 emit_candidate_pairs 로 전 cross-source pair 노출).
    if discovery is None:
        if records is None:
            raise ValueError("run_semantic_candidate_scoring requires records or discovery")
        discovery = discover_overlap(
            records, discovery_mode="semantic_candidate_scoring",
            real_fetch=bool(provenance == "live_derived"), emit_candidate_pairs=True)
    candidate_pairs = discovery.get("candidate_pairs") or []
    # candidate_pairs 부재 시(emit_candidate_pairs 미사용 discovery 직접 주입) near+hard fallback. 원본
    # `_near_pair_record` 는 band 키가 없으므로 **명시 부여**(없으면 hard_selected/fingerprint band 필터가 None 으로
    # 새어 hard negative lane 소실·code-review HIGH-1). fingerprint 정확일치 pair 는 record 로 emit 되지 않아 fallback 에 없음.
    if not candidate_pairs:
        candidate_pairs = (
            [{**p, "band": "near_match"} for p in (discovery.get("near_match_pairs") or [])] +
            [{**p, "band": "hard_negative"} for p in (discovery.get("hard_negative_pairs") or [])])
    # cross-source 진정성(adversarial M-1): scorer 입력을 **source_id 상이 pair 만**으로 제한(기본). discover_overlap 의
    # candidate_pairs 는 publishable·same-date·cross-URL 만 거르고 source_id 동일 여부는 안 봐서 same-source(guardian↔
    # guardian·nyt↔nyt) within-publisher near-dup 이 섞인다 — smoke 본경로 cross-source 가드가 scorer 경로에서 풀리지
    # 않도록 여기서 동일 필터(input_pair_count=전 candidate·cross_source_pair_count=필터 후·excluded 분해 보고).
    input_pair_total = len(candidate_pairs)
    scored_universe = [p for p in candidate_pairs if _is_cross_source(p)] if cross_source_only else list(candidate_pairs)
    same_source_excluded = input_pair_total - len(scored_universe)

    # ── opt-in gate(secret-safe·실호출 0) ──
    scoring_enabled = True
    if scorer_mode in _OPT_IN_MODES:
        env_var = _OPT_IN_ENV_VAR[scorer_mode]
        if not opt_in:
            block_reasons.append("scorer_disabled")
            scoring_enabled = False
        else:
            credential_status = _cred_state(probe(env_var))
            if credential_status != "present":
                block_reasons.append(credential_status)   # missing_credentials / env_not_loaded
                scoring_enabled = False
            elif scorer_fn is None:
                block_reasons.append("provider_error")     # credential present·실 client 미배선(No-Go).
                scoring_enabled = False

    scores: list[dict] = []
    distribution = _score_distribution([])
    top_ids: list[str] = []
    queue_pop = hard_count = near_count = 0
    above_near_floor = 0
    band_distribution: dict[str, int] = {}
    labeler_prediction_hidden = True
    reviewer_packet_exportable = False

    if scoring_enabled:
        # role guard: candidate pair 의 source_role_compatible(publishable×publishable·_near_pair_record 산출) 만.
        role_pairs = [p for p in scored_universe if p.get("source_role_compatible")]
        if not role_pairs:
            block_reasons.append("no_pairs")
        else:
            inputs = [
                normalize_candidate_pair(
                    p, topic=topic, time_window=time_window, provider_a=provider_a,
                    provider_b=provider_b, dataset_source=dataset_source, provenance=provenance)
                for p in role_pairs]
            scores = score_candidate_pairs(inputs, scorer_mode=scorer_mode,
                                           scorer_fn=scorer_fn, max_pairs=max_pairs)
            distribution = _score_distribution(scores)
            # top-k 는 **same-event candidate space**(hard_negative band=different-event lean 제외)에서만 rank —
            # hard negative 를 high score 로 near positive(gold seed)로 승격 금지·negative floor 보존(code-review MED-1).
            hard_pairs = [p for p in role_pairs if p.get("band") == "hard_negative"]
            hard_ids = {str(p.get("pair_id")) for p in hard_pairs}
            scores_for_rank = [s for s in scores if str(s.get("pair_id")) not in hard_ids]
            top_ids = select_top_k(scores_for_rank, top_k=top_k)
            if not top_ids:
                block_reasons.append("no_candidates")
            else:
                by_id = {str(p.get("pair_id")): p for p in role_pairs}
                near_selected = [by_id[t] for t in top_ids if t in by_id]
                hard_selected = hard_pairs   # 전 hard-band pair 보존(top-k 와 band 로 disjoint·double-count 0).
                # detection-floor 분해(adversarial M-2): top-k 후보 중 deterministic 검출 band(fingerprint/near_match=
                # near floor 이상)와 sub-floor(below_floor) 를 구분 — candidate_count>0 이 "검출 진전"으로 오독되지 않게.
                for p in near_selected:
                    band_distribution[p.get("band")] = band_distribution.get(p.get("band"), 0) + 1
                above_near_floor = sum(
                    1 for p in near_selected if p.get("band") in ("fingerprint", "near_match"))
                filtered = dict(discovery)
                filtered["near_match_pairs"] = near_selected   # score 없는 pair record(누출 0).
                filtered["hard_negative_pairs"] = hard_selected
                filtered["fingerprint_overlap_pairs"] = sum(
                    1 for p in near_selected if p.get("band") == "fingerprint")
                queue = build_near_match_reviewer_queue(
                    filtered, packet_id=packet_id, reviewers=reviewers)
                gold_seed = build_gold_seed_report(filtered, queue)
                near_count = queue["near_positive_count"]
                hard_count = queue["hard_negative_discovery_count"]
                queue_pop = len(queue.get("queue_pair_ids") or [])
                labeler_prediction_hidden = bool(gold_seed["labeler_prediction_hidden"])
                reviewer_packet_exportable = bool(gold_seed["reviewer_packet_exportable"])

    def _action_for(br: str) -> str:
        base = _NEXT_ACTION.get(br, f"investigate: {br}")
        # credential 사유는 env var **이름**(값 아님)을 노출해 구체 안내(§10-27: name visible·value hidden).
        if br in ("missing_credentials", "env_not_loaded") and opt_in_env_var:
            return f"{base} — env var: {opt_in_env_var}"
        return base

    next_actions = [_action_for(br) for br in block_reasons]
    return {
        "scorer_name": _SCORER_NAME,
        "scorer_mode": scorer_mode,
        "network_used": network_used,
        "opt_in_env_var": opt_in_env_var,   # opt-in mode 의 readiness env var 이름(값 미열람·None=offline mode).
        # llm_invoked/embedding_invoked = **이 모듈이 실 provider network 호출을 했는가** — 항상 False(이번 턴 실호출 0·
        # injection-only). 주입 scorer_fn 실행 여부는 secret 경계 밖이라 아래 scorer_fn_invoked 로 분리 보고(정직).
        "llm_invoked": False,
        "embedding_invoked": False,
        "scorer_fn_invoked": bool(scorer_mode in _OPT_IN_MODES and scores),
        "opt_in": bool(opt_in),
        "credential_status": credential_status,
        "credential_value_exposed": False,
        "input_pair_count": input_pair_total,                  # 전 candidate pair(cross-source 필터 전·band 무관).
        "cross_source_pair_count": len(scored_universe),       # cross-source(source_id 상이) pair = scorer 입력(M-1).
        "same_source_pair_excluded": same_source_excluded,     # same-source within-publisher near-dup 제외 수(정직).
        "cross_source_only": bool(cross_source_only),
        "scored_pair_count": len(scores),
        "top_k": top_k,
        "score_distribution": distribution,
        "candidate_count": len(top_ids),
        # detection-floor 분해(M-2): top-k 후보 중 deterministic 검출 band(near floor 이상=fingerprint/near_match) 수 +
        # band 분포. above_near_floor_count=0 이면 candidate_count>0 이라도 **deterministic 검출은 여전히 0**(prioritization
        # ≠ 검출). deterministic_scaffold 가 실 ADR#64 데이터(전 sub-floor·Jaccard>0)에서 candidate>0 을 내도 이 필드가 0.
        "above_near_floor_count": above_near_floor,
        "candidate_band_distribution": band_distribution,
        "reviewer_queue_population_count": queue_pop,
        "near_match_count": near_count,
        "hard_negative_count": hard_count,
        "labeler_prediction_hidden": labeler_prediction_hidden,
        "score_hidden_from_labeler": True,
        "rationale_hidden_from_labeler": True,
        "reviewer_packet_exportable": reviewer_packet_exportable,
        "eval_gold_linkage": build_eval_gold_linkage(reviewer_packet_exportable),
        "agent_contract": SCORER_AGENT_CONTRACT,
        "embedding_llm_scorer_policy": EMBEDDING_LLM_SCORER_POLICY,
        "production_gold_count": 0,
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "db_write": False,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }


# ── §8: eval/gold linkage(scorer 가 의미 있으려면 gold 필요·정직) ─────────────────────────────────
def build_eval_gold_linkage(reviewer_packet_exportable: bool, *, current_gold_count: int = 0) -> dict:
    """§8 — scorer 는 gold 전까지 provisional. MERGE_GATE 단일 출처(identity_eval_dataset.MERGE_GATE) 재참조."""
    return {
        "gold_required": True,
        "merge_gate_required": True,
        "current_gold_count": current_gold_count,
        "production_gold_count": 0,
        "reviewer_packet_exportable": bool(reviewer_packet_exportable),
        "reviewer_labels_required": True,
        "calibration_required": True,
        "precision_target": MERGE_GATE["likely_same_precision_min"],
        "fpr_target": MERGE_GATE["likely_same_false_positive_rate_max"],
        "korean_precision_target": MERGE_GATE["korean_subset_precision_min"],
        "deterministic_precision_note": "기존 deterministic precision 0.57 < gate 0.98 (R-IdentityEvalDataset)",
        "semantic_not_better_without_gold": True,   # semantic scorer 도 gold 전엔 더 낫다고 주장 금지.
        "current_status": "No-Go for merge",
    }


# ── CLI(기본 captured fixture·network 0·deterministic; --mode/--top-k; opt-in 은 실호출 0) ──────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#65 semantic candidate scorer (병합 0·LLM 0·embedding 0; 기본 captured fixture·network 0; "
                     "score→top-k rank→reviewer queue·score labeler-facing 숨김)."))
    parser.add_argument("--mode", default=MODE_DETERMINISTIC, choices=sorted(SCORER_MODES),
                        help="scorer mode(기본 deterministic_scaffold). embedding/llm opt-in 은 실호출 0·scorer_fn 미주입 시 block.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="reviewer prioritization top-k(threshold 아님).")
    parser.add_argument("--opt-in", action="store_true", help="opt-in mode 활성(실 client 미배선·No-Go).")
    parser.add_argument("--json", action="store_true", help="§4 scorer report 를 JSON 으로 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.source_overlap_discovery import build_captured_overlap_fixture
    records = build_captured_overlap_fixture()
    out = run_semantic_candidate_scoring(
        records=records, scorer_mode=ns.mode, top_k=ns.top_k, opt_in=ns.opt_in,
        topic="captured_fixture", time_window="1d",
        provider_a="captured", provider_b="captured", dataset_source="captured_fixture",
        provenance="captured_fixture")

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- scorer={out['scorer_name']} mode={out['scorer_mode']} network_used={out['network_used']} "
          f"llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    print(f"- input_pairs={out['input_pair_count']} cross_source={out['cross_source_pair_count']} "
          f"same_source_excluded={out['same_source_pair_excluded']} scored={out['scored_pair_count']} "
          f"top_k={out['top_k']} candidates={out['candidate_count']} above_near_floor={out['above_near_floor_count']} "
          f"queue_pop={out['reviewer_queue_population_count']}")
    print(f"- score_distribution={out['score_distribution']} candidate_bands={out['candidate_band_distribution']}")
    print(f"- near={out['near_match_count']} hard_neg={out['hard_negative_count']} "
          f"labeler_hidden={out['labeler_prediction_hidden']} score_hidden={out['score_hidden_from_labeler']}")
    print(f"- eval_gold_linkage status={out['eval_gold_linkage']['current_status']} "
          f"gold={out['eval_gold_linkage']['current_gold_count']} precision_target={out['eval_gold_linkage']['precision_target']}")
    print(f"- merge_allowed={out['merge_allowed']} no_merge_without_gold={out['no_merge_without_gold']} "
          f"production_gold={out['production_gold_count']} db_write={out['db_write']}")
    print(f"- block_reasons={out['block_reasons']}")
    print(f"- next_actions={out['next_actions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
