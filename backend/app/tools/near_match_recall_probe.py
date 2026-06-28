"""ADR#79 — near-match recall probe (reviewer-routing recall ONLY · merge 0 · LLM 0 · embedding 0 · same_event 단정 0).

문제(ADR#77/#78 실측): cross-source near-match 0. 그 0 의 원인은 (i) **같은 사건인데** deterministic detector 가
표면 변형(약어·복수형·기관명 변형)으로 못 잡음(recall 한계) vs (ii) **broad topic 아래 서로 다른 사건**이라 정당하게
안 겹침 — 단일 broad/7d run 으로는 구분 불가(ADR#64/#77 명시).

이 모듈은 그 (i)/(ii) 를 가르는 **경험적 레버**다. deterministic 정규화(case fold·punctuation strip·organization
phrase alias·acronym alias·light stemming·number normalize)를 적용해 **reviewer-routing 후보 recall** 을 높이고,
**어느 정규화가 공유 토큰을 만들었는지(feature attribution)** 를 보고한다:
  - 정규화 후 **entity-canonical 토큰**(federalreserve·supremecourt …)을 공유 → (i) recall-miss 지지(같은 기관/사건).
  - 정규화 후에도 **무공유 또는 generic 토큰만** → (ii) different-events 지지.
둘 다 **reviewer 라벨 없이는 indeterminate** — probe 는 truth 가 아니라 reviewer 우선순위 신호다.

절대 불변(false-merge = cardinal sin):
  - **reviewer-routing recall ONLY**: 이 모듈은 `cluster_records`/`semantic_identity_fingerprint`(merge 경로)를
    **호출하지 않는다**. merge 는 여전히 exact token-set + date bucket + gold + MERGE_GATE 게이트 — recall 완화는
    reviewer 라우팅에만 적용된다(false-merge 표면 불변). `recall_probe_applies_to_merge=False` 불변.
  - **merge_allowed=False 불변** · `same_event_asserted=False` 불변 · score 는 internal-only(labeler 미노출) ·
    raw body 0(title 헤드라인만·≤512) · secret 0.
  - 정규화 표는 **결정론·stdlib only**(ML/embedding/외부 사전 0) · 보수적(과확장 금지) · 큐레이트(확장 가능).
  - **source role guard**: publishable×publishable 만 reviewer 후보(community/market/catalog anchor 금지 — 소비처가 강제).

baseline(merge-path) 신호는 `cross_source_dedup._title_tokens`/`_jaccard`(read-only 재사용)로 계산해 정직하게
대조한다(probe 가 baseline 대비 무엇을 lift 했는지 분해). 이 모듈은 merge 함수를 import 하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional

from ingestion.orchestration.cross_source_dedup import _jaccard, _title_tokens

_PROBE_NAME = "near_match_recall_probe"

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")

# reviewer-routing 기본 floor — source_overlap_discovery._HARD_NEG_FLOOR(0.2)와 정합(hard-negative band 진입선).
# probe 가 이 선을 넘기면 reviewer 후보가 된다(merge 아님·같은 사건 단정 아님).
DEFAULT_ROUTING_FLOOR = 0.2

# 정규화 stopword: cross_source_dedup._STOPWORDS(21·merge 정합) + routing 전용 generic filler 소폭 확장.
# 확장분은 **routing 한정**(merge 토큰화는 불변) — entity 신호 대비 generic 잡음을 낮춰 (i)/(ii) 판별을 선명하게.
# ADR#77 fed_rate 에서 below-floor 쌍을 오염시킨 generic 토큰(it/over/day) 류를 포함.
_BASE_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "with",
    "is", "are", "was", "were", "says", "say", "after", "as", "at", "by",
})
_ROUTING_EXTRA_STOPWORDS = frozenset({
    "it", "its", "over", "day", "new", "two", "amid", "into", "from", "out",
    "up", "off", "than", "this", "that", "his", "her", "their", "but", "not",
})
_PROBE_STOPWORDS = _BASE_STOPWORDS | _ROUTING_EXTRA_STOPWORDS

# ── organization phrase alias(다토큰 기관명 → canonical 단일 토큰; 결정론·큐레이트·확장 가능) ─────────────────
# 어순 보존 인접 매칭(longest-first). stopword(of) 포함 구(bank of japan)는 stopword 제거 **전** 단계라 매칭 가능.
_ORG_PHRASE_ALIAS: dict[tuple[str, ...], str] = {
    ("federal", "reserve"): "federalreserve",
    ("supreme", "court"): "supremecourt",
    ("european", "central", "bank"): "europeancentralbank",
    ("european", "union"): "europeanunion",
    ("bank", "of", "japan"): "bankofjapan",
    ("bank", "of", "england"): "bankofengland",
    ("united", "nations"): "unitednations",
    ("united", "kingdom"): "unitedkingdom",
    ("united", "states"): "unitedstates",
    ("white", "house"): "whitehouse",
    ("world", "health", "organization"): "worldhealthorganization",
    ("international", "monetary", "fund"): "imf",
    ("north", "atlantic", "treaty", "organization"): "nato",
    ("securities", "and", "exchange", "commission"): "sec",
}

# ── acronym alias(단일 토큰 → canonical; 큐레이트·모호 단어 제외) ────────────────────────────────────────────
# 소문자화 후 일반 영어 단어와 충돌하는 약어(who/un/us/eu/it)는 **제외**(false lift 방지). 식별성 높은 약어만.
_ACRONYM_ALIAS: dict[str, str] = {
    "fed": "federalreserve",
    "fomc": "federalreserve",
    "scotus": "supremecourt",
    "ecb": "europeancentralbank",
    "boj": "bankofjapan",
    "boe": "bankofengland",
    "nato": "nato",
    "imf": "imf",
    "opec": "opec",
    "doj": "departmentofjustice",
    "fda": "fooddrugadministration",
}

# entity-canonical 토큰(alias 산출값) — (i)/(ii) 판별의 핵심: 정규화 후 이 집합 토큰을 **alias provenance 로** 공유하면
# 같은 기관/사건 신호. **string membership 만으로 판정하지 않는다**(adversarial: 짧은 canonical 값[sec/imf/nato/opec]이
# raw 토큰[seconds/Section]으로 등장 시 거짓 entity 승격 차단) — entity 판정은 `_ALIAS_ORIGINS` provenance 와 AND.
_ENTITY_CANONICAL_TOKENS = frozenset(_ORG_PHRASE_ALIAS.values()) | frozenset(_ACRONYM_ALIAS.values())
# alias 가 산출한 토큰의 origin 태그(raw identity/stem/number 와 구분) — entity-canonical provenance 게이트.
_ALIAS_ORIGINS = frozenset({"phrase_alias", "acronym_alias"})

# normalization_features_tested(§4 보고용·정직: 실제 적용되는 정규화만 열거).
NORMALIZATION_FEATURES: tuple[str, ...] = (
    "case_fold",
    "punctuation_strip",
    "routing_stopword_removal",
    "organization_phrase_alias",
    "acronym_alias",
    "light_stemming",
    "number_normalize",
)

# 계약 상수(소비처/문서/테스트가 같은 표면을 본다).
RECALL_PROBE_CONTRACT = {
    "applies_to": "reviewer_routing_candidate_recall",
    "applies_to_merge": False,
    "merge_path_untouched": "cross_source_dedup.cluster_records / semantic_identity_fingerprint (exact token-set + "
                            "date bucket); recall probe never calls these",
    "score_is": "reviewer prioritization signal — NOT truth, NOT same-event assertion, NOT a merge threshold",
    "score_visibility": "internal-only (labeler/public 미노출)",
    "same_event_asserted": False,
    "raw_body_used": False,
    "secret_used": False,
    "forbidden": [
        "use probe score as merge decision",
        "assert same_event from probe lift",
        "expose probe score/rationale to reviewer or public",
        "weaken cross_source_dedup merge tokenization",
        "use community/market/catalog as anchor",
    ],
}


def _light_stem(tok: str) -> str:
    """보수적 결정론 suffix stripping(routing recall 한정·merge 토큰화 불변). 흔한 복수/시제만·과형태소화 회피.

    rates→rate · increases→increase · operations→operation · halting→halt · shipping→ship · companies→company.
    완벽한 stemmer 아님(silent-e/불규칙 일부 미처리) — routing 후보 recall 용 'light' 정규화."""
    if len(tok) <= 3:
        return tok
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-3] + "y"                                   # companies→company
    if tok.endswith("s") and not tok.endswith(("ss", "us", "is", "as", "os")) and len(tok) > 3:
        return tok[:-1]                                         # rates→rate · increases→increase · shares→share
    if tok.endswith("ing") and len(tok) > 5:
        stem = tok[:-3]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
            stem = stem[:-1]                                    # shipping→ship
        return stem                                            # halting→halt
    if tok.endswith("ed") and not tok.endswith("eed") and len(tok) > 4:
        stem = tok[:-2]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
            stem = stem[:-1]                                    # banned→ban
        return stem                                            # halted→halt
    return tok


def _number_normalize(tok: str) -> str:
    """digit 토큰 leading-zero 제거(005→5). 비숫자 토큰 불변·word-number 매핑은 하지 않음(과변환 회피·정직)."""
    if tok.isdigit():
        return str(int(tok))
    return tok


def _collapse_phrases(tokens: list[str]) -> tuple[list[str], list[str], list[bool]]:
    """ordered 토큰열에서 알려진 기관 다토큰 구를 canonical 토큰으로 축약(longest-first·인접 매칭).

    반환: (축약된 토큰열, fired phrase 목록['federal reserve→federalreserve'], collapsed_flags[위치별 phrase-collapse
    산출 여부]). collapsed_flags 로 **phrase-collapse 가 만든 canonical** 과 **우연히 같은 문자열인 raw 토큰**을 구분
    (raw 'sec'[seconds] 거짓 entity 승격 차단). stopword 제거 **전** 호출(bank of japan 등 stopword 포함 구 매칭)."""
    phrases = sorted(_ORG_PHRASE_ALIAS.items(), key=lambda kv: -len(kv[0]))
    out: list[str] = []
    fired: list[str] = []
    collapsed_flags: list[bool] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        for seq, canon in phrases:
            ln = len(seq)
            if i + ln <= n and tuple(tokens[i:i + ln]) == seq:
                out.append(canon)
                fired.append(" ".join(seq) + "→" + canon)
                collapsed_flags.append(True)
                i += ln
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            collapsed_flags.append(False)
            i += 1
    return out, fired, collapsed_flags


def normalize_for_recall(title: Optional[str]) -> dict:
    """title → 정규화 토큰 집합 + feature 출처(case fold·phrase/acronym alias·light stem·number·stopword).

    반환 dict:
      - tokens: frozenset[str] — 최종 정규화 토큰(reviewer-routing 유사도 계산용).
      - origin: dict[token, set[feature]] — 각 최종 토큰을 만든 정규화 feature(phrase_alias/acronym_alias/stem/
        number/identity) — pair 단계에서 '무엇이 공유 토큰을 만들었나' 분해에 사용.
      - features: dict — fired 정규화 요약(phrase_alias 목록·acronym 목록·stem 쌍·stopword 제거 수).
    raw body 미사용(title 헤드라인만)·secret 0·결정론."""
    raw = [t.lower() for t in _TOKEN.findall(title or "")]
    collapsed, phrase_fired, collapsed_flags = _collapse_phrases(raw)

    tokens: set[str] = set()
    origin: dict[str, set[str]] = {}
    acronym_fired: list[str] = []
    stem_fired: list[str] = []
    stopword_removed = 0

    for tok, is_collapsed in zip(collapsed, collapsed_flags, strict=True):
        if is_collapsed:
            # phrase-collapse 가 산출한 canonical 토큰(예: federal reserve→federalreserve) — provenance 확실한 entity.
            # **raw 토큰이 우연히 canonical 문자열과 같은 경우(raw 'sec'=seconds)는 여기 오지 않는다**(collapsed_flags=False).
            tokens.add(tok)
            origin.setdefault(tok, set()).add("phrase_alias")
            continue
        if len(tok) <= 1 or tok in _PROBE_STOPWORDS:
            stopword_removed += 1
            continue
        if tok in _ACRONYM_ALIAS:
            canon = _ACRONYM_ALIAS[tok]
            tokens.add(canon)
            origin.setdefault(canon, set()).add("acronym_alias")
            acronym_fired.append(tok + "→" + canon)
            continue
        norm = _number_normalize(tok)
        if norm != tok:
            tokens.add(norm)
            origin.setdefault(norm, set()).add("number")
            continue
        stem = _light_stem(tok)
        tokens.add(stem)
        if stem != tok:
            origin.setdefault(stem, set()).add("stem")
            stem_fired.append(tok + "→" + stem)
        else:
            origin.setdefault(stem, set()).add("identity")

    return {
        "tokens": frozenset(tokens),
        "origin": origin,
        "features": {
            "phrase_alias": phrase_fired,
            "acronym_alias": acronym_fired,
            "stem": stem_fired,
            "stopword_removed": stopword_removed,
        },
    }


def recall_probe_pair(
    title_left: Optional[str], title_right: Optional[str], *,
    routing_floor: float = DEFAULT_ROUTING_FLOOR,
) -> dict:
    """두 title → baseline(merge-path) vs probe(정규화) 유사도 + lift + feature 분해(reviewer-routing 신호).

    merge_allowed/same_event 단정 0 불변. score 는 reviewer 우선순위 신호이지 truth 아님. shared_normalized_tokens
    는 정규화 교집합(제목 전문 아님)·entity-canonical 여부로 (i)/(ii) 판별 근거 제공."""
    base_left, base_right = _title_tokens(title_left), _title_tokens(title_right)
    baseline = _jaccard(base_left, base_right)

    nl, nr = normalize_for_recall(title_left), normalize_for_recall(title_right)
    probe = _jaccard(nl["tokens"], nr["tokens"])
    shared = sorted(nl["tokens"] & nr["tokens"])

    def _entity_shared(t: str) -> bool:
        # entity-canonical 판정 = canonical 어휘 ∈ AND **양쪽 다 alias provenance**(phrase/acronym)로 산출.
        # raw 'sec'(seconds·origin=identity)는 canonical 어휘여도 alias provenance 가 아니라 entity 아님(거짓 (i) 차단).
        if t not in _ENTITY_CANONICAL_TOKENS:
            return False
        return bool((_ALIAS_ORIGINS & nl["origin"].get(t, set()))
                    and (_ALIAS_ORIGINS & nr["origin"].get(t, set())))

    shared_entity = [t for t in shared if _entity_shared(t)]

    # 공유 토큰을 만든 feature 분해(identity=정규화 없이 원래 공유 — lift 기여 아님).
    feats: set[str] = set()
    for t in shared:
        feats |= nl["origin"].get(t, set())
        feats |= nr["origin"].get(t, set())
    features_fired = sorted(feats - {"identity"})

    crosses = probe >= routing_floor
    baseline_below = baseline < routing_floor
    return {
        "baseline_title_jaccard": round(baseline, 4),       # merge-path 신호(cross_source_dedup._title_tokens).
        "recall_probe_score": round(probe, 4),              # 정규화 후 유사도(reviewer-routing 신호·truth 아님).
        "recall_lift": round(probe - baseline, 4),
        "shared_normalized_tokens": shared,                 # 정규화 교집합(제목 전문 아님·body 0).
        "shared_entity_canonical_tokens": shared_entity,    # alias 산출 기관 토큰 공유 → (i) recall-miss 지지 신호.
        "shared_entity_token_count": len(shared_entity),
        "features_fired": features_fired,                   # 공유 토큰을 만든 정규화(phrase_alias/acronym_alias/stem/number).
        "crosses_reviewer_routing_floor": crosses,
        "newly_routed_by_probe": bool(crosses and baseline_below),   # baseline 은 놓쳤으나 probe 가 routing 으로 올림.
        "routing_floor": routing_floor,
        # 불변 경계(false-merge 차단):
        "recall_probe_applies_to_merge": False,
        "merge_allowed": False,
        "same_event_asserted": False,
    }


def summarize_recall_probe(
    pairs: list[dict], *, routing_floor: float = DEFAULT_ROUTING_FLOOR, top_k: int = 5,
) -> dict:
    """candidate pair 목록(title_left/title_right 보유·`_near_pair_record` 형태) → recall probe 집계(body-free).

    각 pair 에 recall_probe_pair 적용 → max score·lift·newly-routed 수·entity 공유 수 집계 + 최고 lift 샘플 top-k
    (공유 정규화 토큰·feature 만·제목 전문 0). internal-only(score 노출 아님·labeler 미투입). merge 미적용 불변."""
    probed: list[dict] = []
    for p in pairs:
        r = recall_probe_pair(p.get("title_left"), p.get("title_right"), routing_floor=routing_floor)
        probed.append({
            "pair_id": p.get("pair_id"),
            "source_role_left": p.get("source_type_left"),
            "source_role_right": p.get("source_type_right"),
            "baseline_title_jaccard": r["baseline_title_jaccard"],
            "recall_probe_score": r["recall_probe_score"],
            "recall_lift": r["recall_lift"],
            "shared_normalized_tokens": r["shared_normalized_tokens"],
            "shared_entity_canonical_tokens": r["shared_entity_canonical_tokens"],
            "features_fired": r["features_fired"],
            "newly_routed_by_probe": r["newly_routed_by_probe"],
            "crosses_reviewer_routing_floor": r["crosses_reviewer_routing_floor"],
        })
    newly_routed = [p for p in probed if p["newly_routed_by_probe"]]
    entity_lifts = [p for p in newly_routed if p["shared_entity_canonical_tokens"]]
    max_score = max((p["recall_probe_score"] for p in probed), default=0.0)
    max_lift = max((p["recall_lift"] for p in probed), default=0.0)
    samples = sorted(probed, key=lambda p: (p["recall_lift"], p["recall_probe_score"]), reverse=True)[:max(0, top_k)]
    return {
        "probe_name": _PROBE_NAME,
        "candidate_pair_count": len(probed),
        "max_recall_probe_score": round(max_score, 4),
        "max_recall_lift": round(max_lift, 4),
        "pairs_newly_routed_by_probe": len(newly_routed),       # baseline 미달이나 probe 가 routing 으로 올린 쌍.
        "pairs_newly_routed_sharing_entity": len(entity_lifts),  # 그 중 entity-canonical 토큰 공유((i) 지지 강도).
        "normalization_features_tested": list(NORMALIZATION_FEATURES),
        "top_lift_samples": samples,                            # body-free(공유 정규화 토큰·feature 만).
        "routing_floor": routing_floor,
        "recall_probe_applies_to_reviewer_routing_only": True,
        "recall_probe_applies_to_merge": False,
        "score_exposed_to_reviewer": False,
        "score_exposed_to_public": False,
        "same_event_asserted": False,
        "raw_body_stored": False,
        "merge_allowed": False,
    }


# ── synthetic 검증 fixture(below-floor 같은-사건 paraphrase + different-events control·실 source 아님·명시) ────
def build_recall_probe_validation_fixture() -> list[dict]:
    """recall probe 메커니즘을 **결정론**으로 검증하는 synthetic pair fixture(실 source behavior 아님·라벨 아님).

    구성:
      1. below-floor 같은 사건(acronym+stem lift): 'Fed raises rates' ↔ 'Federal Reserve lifts interest rates'
         — baseline Jaccard < 0.2(fed≠federal·rates 만 일치) → probe 가 {federalreserve, rate} 공유로 routing 올림.
      2. below-floor 같은 사건(phrase alias lift): 'SCOTUS overturns abortion precedent' ↔ 'Supreme Court strikes
         down abortion ruling' — scotus≡supreme court·abortion 공유 → probe lift.
      3. different-events control: 'Fed raises rates' ↔ 'Hurricane batters Florida coastline' — 정규화 후에도
         무공유 → probe 가 **올리지 않음**(false lift 차단·(ii) 판별).
      4. already-detectable(near band·probe 무해): 거의 동일 제목 — baseline 도 high·probe 가 깨지 않음.
      5. stemming-only 일반화(alias/entity 없음·curated table 밖): 모든 content 어가 복수/시제로만 달라 baseline 0 →
         light stemming 만으로 routing 올림(entity 공유 0) — probe 가 alias 테이블에 **의존하지 않고** 일반화함을 시연.
    publishable×publishable(article)만. body 0(title 헤드라인만)."""
    day = "2026-06-22"

    def _pair(pid: str, ta: str, tb: str) -> dict:
        return {
            "pair_id": f"rp_syn:{pid}",
            "source_id_left": "syn:outlet_a", "source_id_right": "syn:outlet_b",
            "source_type_left": "article", "source_type_right": "article",
            "title_left": ta, "title_right": tb,
            "observed_at_left": day, "observed_at_right": day,
            "canonical_url_left": f"https://outlet-syn-a.test/{pid}",
            "canonical_url_right": f"https://outlet-syn-b.test/{pid}",
            "date_bucket_match": True, "source_role_compatible": True, "band": "below_floor",
        }

    return [
        _pair("fed_acronym", "Fed raises rates again",
              "Federal Reserve lifts interest rates"),
        _pair("scotus_phrase", "SCOTUS overturns abortion precedent",
              "Supreme Court strikes down abortion ruling"),
        _pair("diff_control", "Fed raises rates again",
              "Hurricane batters Florida coastline overnight"),
        _pair("near_identical", "Major port strike halts container shipping operations",
              "Major port strike halts container shipping operation"),
        _pair("stem_generalization", "Officials probe banks",
              "Official probes bank"),
    ]


# ── CLI(synthetic 검증·network 0·결정론; merge 미적용·score internal) ─────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="ADR#79 near-match recall probe (reviewer-routing recall only·merge 0·LLM 0·embedding 0; "
                    "synthetic 검증·network 0).")
    parser.add_argument("--routing-floor", type=float, default=DEFAULT_ROUTING_FLOOR,
                        help="reviewer-routing floor(기본 0.2·hard-negative band 진입선·merge threshold 아님).")
    parser.add_argument("--json", action="store_true", help="summary JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    fixture = build_recall_probe_validation_fixture()
    summary = summarize_recall_probe(fixture, routing_floor=ns.routing_floor)
    if ns.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(f"- probe={summary['probe_name']} pairs={summary['candidate_pair_count']} "
          f"max_score={summary['max_recall_probe_score']} max_lift={summary['max_recall_lift']}")
    print(f"- newly_routed={summary['pairs_newly_routed_by_probe']} "
          f"(sharing_entity={summary['pairs_newly_routed_sharing_entity']}) floor={summary['routing_floor']}")
    print(f"- normalization_features={summary['normalization_features_tested']}")
    print(f"- applies_to_merge={summary['recall_probe_applies_to_merge']} merge_allowed={summary['merge_allowed']} "
          f"same_event_asserted={summary['same_event_asserted']} score_to_reviewer={summary['score_exposed_to_reviewer']}")
    for s in summary["top_lift_samples"]:
        print(f"  · {s['pair_id']}: baseline={s['baseline_title_jaccard']} probe={s['recall_probe_score']} "
              f"lift={s['recall_lift']} newly_routed={s['newly_routed_by_probe']} "
              f"shared_entity={s['shared_entity_canonical_tokens']} features={s['features_fired']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
