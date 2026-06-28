"""ADR#79 — near_match_recall_probe 테스트(reviewer-routing recall only·merge 분리·feature attribution·결정론).

핵심 잠금:
  - below-floor 같은-사건 paraphrase 를 probe 가 routing 으로 lift(recall 개선 — 알려진 synthetic case 에서 측정).
  - different-events 는 probe 가 올리지 않음(false lift 차단·(i)/(ii) 판별).
  - merge 불변: recall_probe_applies_to_merge=False·merge_allowed=False·same_event_asserted=False.
  - 물리적 merge 분리: 모듈이 cluster_records/semantic_identity_fingerprint 를 import/참조하지 않음.
  - score 는 internal-only(reviewer/public 미노출)·body-free 요약.
"""
from __future__ import annotations

import pathlib

from backend.app.tools import near_match_recall_probe as rp
from ingestion.orchestration.cross_source_dedup import _jaccard, _title_tokens

ROUTING_FLOOR = rp.DEFAULT_ROUTING_FLOOR


def _pair_by_id(summary: dict, pid: str) -> dict:
    for s in summary["top_lift_samples"]:
        if s["pair_id"] == pid:
            return s
    raise AssertionError(f"{pid} not in samples")


# ── normalize_for_recall ────────────────────────────────────────────────────────────────────────────────
def test_phrase_alias_collapses_federal_reserve():
    norm = rp.normalize_for_recall("Federal Reserve raises interest rates")
    assert "federalreserve" in norm["tokens"]
    assert any("federal reserve" in f for f in norm["features"]["phrase_alias"])


def test_acronym_alias_maps_fed_to_canonical():
    norm = rp.normalize_for_recall("Fed signals pause")
    assert "federalreserve" in norm["tokens"]
    assert any(f.startswith("fed→") for f in norm["features"]["acronym_alias"])


def test_fed_and_federal_reserve_collapse_to_same_token():
    a = rp.normalize_for_recall("Fed raises rates")
    b = rp.normalize_for_recall("Federal Reserve lifts rates")
    assert "federalreserve" in (a["tokens"] & b["tokens"])


def test_light_stem_common_cases():
    assert rp._light_stem("rates") == "rate"
    assert rp._light_stem("operations") == "operation"
    assert rp._light_stem("increases") == "increase"
    assert rp._light_stem("halting") == "halt"
    assert rp._light_stem("shipping") == "ship"
    assert rp._light_stem("companies") == "company"
    assert rp._light_stem("halted") == "halt"


def test_light_stem_guards_short_and_double_s():
    assert rp._light_stem("us") == "us"          # too short — untouched.
    assert rp._light_stem("press") == "press"    # -ss not stripped.
    assert rp._light_stem("crisis") == "crisis"  # -is not stripped.


def test_number_normalize_strips_leading_zeros():
    norm = rp.normalize_for_recall("Magnitude 007 quake")
    assert "7" in norm["tokens"]


def test_routing_stopword_removes_generic_filler():
    # ADR#77 generic 오염 토큰(it/over/day)은 routing stopword 로 제거.
    norm = rp.normalize_for_recall("It rained over the day")
    assert "it" not in norm["tokens"]
    assert "over" not in norm["tokens"]
    assert "day" not in norm["tokens"]


def test_acronym_table_excludes_ambiguous_words():
    # 소문자화 후 일반 단어와 충돌하는 약어는 제외(false lift 방지).
    for amb in ("who", "us", "un", "eu", "it", "we"):
        assert amb not in rp._ACRONYM_ALIAS


# ── recall_probe_pair: below-floor 같은-사건 lift ────────────────────────────────────────────────────────
def test_below_floor_same_event_lifted_by_acronym_alias():
    r = rp.recall_probe_pair("Fed raises rates again", "Federal Reserve lifts interest rates")
    assert r["baseline_title_jaccard"] < ROUTING_FLOOR          # merge-path detector 가 놓침.
    assert r["recall_probe_score"] >= ROUTING_FLOOR             # probe 가 routing 으로 올림.
    assert r["newly_routed_by_probe"] is True
    assert "federalreserve" in r["shared_entity_canonical_tokens"]
    assert "acronym_alias" in r["features_fired"] or "phrase_alias" in r["features_fired"]


def test_below_floor_same_event_lifted_by_phrase_alias():
    r = rp.recall_probe_pair("SCOTUS overturns abortion precedent",
                             "Supreme Court strikes down abortion ruling")
    assert r["baseline_title_jaccard"] < ROUTING_FLOOR
    assert r["recall_probe_score"] >= ROUTING_FLOOR
    assert r["newly_routed_by_probe"] is True
    assert "supremecourt" in r["shared_entity_canonical_tokens"]


# ── recall_probe_pair: different-events 판별(false lift 차단) ──────────────────────────────────────────────
def test_different_events_not_lifted():
    r = rp.recall_probe_pair("Fed raises rates again", "Hurricane batters Florida coastline overnight")
    assert r["recall_probe_score"] < ROUTING_FLOOR
    assert r["newly_routed_by_probe"] is False
    assert r["shared_entity_canonical_tokens"] == []


def test_generic_shared_tokens_do_not_count_as_entity():
    # 정규화 후 generic content 토큰만 공유 → entity 신호 0((i) 과대해석 차단).
    r = rp.recall_probe_pair("City council approves housing plan",
                             "City council approves stadium plan")
    assert r["shared_entity_canonical_tokens"] == []


# ── adversarial: 짧은 canonical 값의 raw 동음 충돌(provenance 게이트) ──────────────────────────────────────
def test_raw_short_canonical_token_not_entity():
    # raw 'sec'(seconds·Section)는 canonical 어휘('sec'=Securities and Exchange Commission)와 같지만 alias provenance 가
    # 아니므로 **entity 아님**(거짓 (i) recall-miss 신호 차단·adversarial MEDIUM). string membership 만으로 승격하면 FAIL.
    r = rp.recall_probe_pair("Winning shot in final sec of the game",
                             "Buzzer beater with one sec on the clock")
    assert "sec" not in r["shared_entity_canonical_tokens"]
    assert r["shared_entity_canonical_tokens"] == []


def test_phrase_derived_canonical_is_entity():
    # 반대로 multi-word phrase 'Securities and Exchange Commission'→'sec'(phrase_alias provenance)는 entity.
    r = rp.recall_probe_pair("Securities and Exchange Commission opens probe",
                             "Securities and Exchange Commission files charges")
    assert "sec" in r["shared_entity_canonical_tokens"]


def test_raw_acronym_key_still_entity():
    # raw 'nato'(unambiguous acronym key)는 acronym_alias provenance 로 entity 유지(과교정 회귀 방지).
    r = rp.recall_probe_pair("NATO summit opens in the capital",
                             "NATO leaders gather for the summit")
    assert "nato" in r["shared_entity_canonical_tokens"]


def test_stemming_only_generalization_lift_without_alias():
    # alias 테이블에 **없는** 어휘가 복수/시제로만 달라 baseline 0 → light stemming 만으로 routing 올림(entity 0).
    # probe 가 curated table 에 의존하지 않고 일반화함을 잠금(adversarial: fixture tautology 보완).
    r = rp.recall_probe_pair("Officials probe banks", "Official probes bank")
    assert r["baseline_title_jaccard"] < ROUTING_FLOOR
    assert r["recall_probe_score"] >= ROUTING_FLOOR
    assert r["newly_routed_by_probe"] is True
    assert r["shared_entity_canonical_tokens"] == []        # entity alias 없이 stem 만으로 lift.
    assert "stem" in r["features_fired"]


def test_same_entity_different_event_routes_but_not_asserted():
    # 같은 기관·다른 사건(Fed 사임 ↔ Fed 증언)은 entity 공유로 routing 될 수 있으나 **same_event 단정 0**.
    # probe 는 reviewer 라우팅 신호일 뿐(라벨은 reviewer/gold)·merge 0 — 이 정직 경계를 잠금.
    r = rp.recall_probe_pair("Fed official resigns suddenly today",
                             "Federal Reserve official testifies before Senate")
    assert r["same_event_asserted"] is False                # routing 되어도 같은 사건 단정 0.
    assert r["merge_allowed"] is False
    assert r["recall_probe_applies_to_merge"] is False


def test_already_detectable_pair_not_broken():
    r = rp.recall_probe_pair("Major port strike halts container shipping operations",
                             "Major port strike halts container shipping operation")
    assert r["baseline_title_jaccard"] >= ROUTING_FLOOR
    assert r["recall_probe_score"] >= r["baseline_title_jaccard"]   # 깨지 않음(>=).
    assert r["newly_routed_by_probe"] is False                      # 이미 floor 위 — 'newly' 아님.


# ── baseline = merge-path 토큰화(정직 대조) ────────────────────────────────────────────────────────────────
def test_baseline_uses_merge_path_tokenization():
    a, b = "Fed raises rates", "Federal Reserve lifts rates"
    r = rp.recall_probe_pair(a, b)
    expected = round(_jaccard(_title_tokens(a), _title_tokens(b)), 4)
    assert r["baseline_title_jaccard"] == expected


# ── merge 불변(false-merge=cardinal sin) ──────────────────────────────────────────────────────────────────
def test_pair_output_never_allows_merge():
    r = rp.recall_probe_pair("Fed raises rates", "Federal Reserve lifts rates")
    assert r["merge_allowed"] is False
    assert r["recall_probe_applies_to_merge"] is False
    assert r["same_event_asserted"] is False


def test_summary_merge_and_exposure_invariants():
    summary = rp.summarize_recall_probe(rp.build_recall_probe_validation_fixture())
    assert summary["recall_probe_applies_to_merge"] is False
    assert summary["recall_probe_applies_to_reviewer_routing_only"] is True
    assert summary["merge_allowed"] is False
    assert summary["same_event_asserted"] is False
    assert summary["score_exposed_to_reviewer"] is False
    assert summary["score_exposed_to_public"] is False
    assert summary["raw_body_stored"] is False


def test_module_does_not_reference_merge_path():
    """물리적 merge 분리 잠금(Q10/Q11): 모듈이 merge 함수(cluster_records/semantic_identity_fingerprint)를
    import 하거나 호출하지 않음. docstring 산문 언급은 허용 — AST 로 실제 import/참조만 검사."""
    import ast
    tree = ast.parse(pathlib.Path(rp.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    for forbidden in ("cluster_records", "semantic_identity_fingerprint"):
        assert forbidden not in imported, f"{forbidden} must not be imported (merge path)"
        assert forbidden not in referenced, f"{forbidden} must not be referenced (merge path)"
        assert getattr(rp, forbidden, None) is None      # 모듈 네임스페이스에 부재 → 호출 불가.


def test_contract_constant_names_forbidden_shortcuts():
    c = rp.RECALL_PROBE_CONTRACT
    assert c["applies_to_merge"] is False
    assert c["same_event_asserted"] is False
    assert any("merge decision" in f for f in c["forbidden"])


# ── summarize: recall 개선 측정(§13 closure) + body-free ──────────────────────────────────────────────────
def test_recall_improvement_on_constructed_known_cases():
    # 정직 범위: 이 fixture 는 정규화 메커니즘을 **구성된 known case** 에서 결정론적으로 행사함을 잠근다(대표 표본의
    # recall 일반화 측정이 아님 — held-out/live 는 deferred). below-floor 같은-사건을 routing 으로 올림(entity 2 + stem 1).
    summary = rp.summarize_recall_probe(rp.build_recall_probe_validation_fixture())
    assert summary["pairs_newly_routed_by_probe"] >= 3          # fed·scotus(entity) + stem_generalization(non-entity).
    assert summary["pairs_newly_routed_sharing_entity"] >= 2    # entity alias lift(fed·scotus).
    # **alias 테이블 밖 일반화**: entity 공유 없이 routing 으로 올라간 쌍이 존재(curated table 의존 아님·tautology 보완).
    assert summary["pairs_newly_routed_by_probe"] > summary["pairs_newly_routed_sharing_entity"]
    assert summary["max_recall_lift"] > 0.0


def test_summary_samples_are_body_free():
    summary = rp.summarize_recall_probe(rp.build_recall_probe_validation_fixture())
    for s in summary["top_lift_samples"]:
        assert "title_left" not in s and "title_right" not in s       # 제목 전문 미노출.
        assert "score" not in s                                       # bare 'score' 키 부재(recall_probe_score 만·forbidden 키 회피).
        assert isinstance(s["shared_normalized_tokens"], list)


def test_normalization_features_tested_listed():
    summary = rp.summarize_recall_probe([])
    assert summary["normalization_features_tested"] == list(rp.NORMALIZATION_FEATURES)
    assert "organization_phrase_alias" in summary["normalization_features_tested"]
    assert "acronym_alias" in summary["normalization_features_tested"]
    assert "light_stemming" in summary["normalization_features_tested"]


# ── 결정론·경계 입력 ──────────────────────────────────────────────────────────────────────────────────────
def test_determinism():
    a, b = "Fed raises rates", "Federal Reserve lifts interest rates"
    assert rp.recall_probe_pair(a, b) == rp.recall_probe_pair(a, b)


def test_empty_and_none_titles():
    assert rp.recall_probe_pair(None, None)["recall_probe_score"] == 0.0
    assert rp.recall_probe_pair("", "Fed raises rates")["recall_probe_score"] == 0.0


def test_routing_floor_parametrized():
    # 더 높은 floor → newly_routed 감소(0.5 에선 fed/scotus lift 가 floor 미달).
    lo = rp.summarize_recall_probe(rp.build_recall_probe_validation_fixture(), routing_floor=0.2)
    hi = rp.summarize_recall_probe(rp.build_recall_probe_validation_fixture(), routing_floor=0.5)
    assert hi["pairs_newly_routed_by_probe"] <= lo["pairs_newly_routed_by_probe"]


def test_validation_fixture_provenance_synthetic():
    for p in rp.build_recall_probe_validation_fixture():
        assert p["pair_id"].startswith("rp_syn:")               # synthetic 명시(production 둔갑 차단).
        assert p["source_type_left"] == "article" and p["source_type_right"] == "article"


def test_summarize_empty_pairs():
    summary = rp.summarize_recall_probe([])
    assert summary["candidate_pair_count"] == 0
    assert summary["max_recall_probe_score"] == 0.0
    assert summary["pairs_newly_routed_by_probe"] == 0
