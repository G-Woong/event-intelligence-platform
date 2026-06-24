from __future__ import annotations

"""Identity eval dataset load/validation 단위 (ADR#43, R-IdentityEvalDataset).

JSONL labeled pair set 의 schema/중복/enum/raw-body 차단/결정론 로드를 검증. metric 산출은
test_semantic_identity_eval_metrics.py 에서.
"""

import json
from pathlib import Path

import pytest

from backend.app.services.identity_eval_dataset import (
    GOLD_LABELS,
    EvalPair,
    load_eval_pairs,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "identity_eval_pairs.jsonl"


def _row(**kw):
    base = {
        "pair_id": "x1", "label": "same_event", "language": "en",
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "Federal Reserve raises benchmark interest rates today",
        "title_right": "Federal Reserve raises benchmark interest rates today",
        "observed_at_left": "2026-06-24T09:00:00Z", "observed_at_right": "2026-06-24T10:00:00Z",
    }
    base.update(kw)
    return base


def _write(tmp_path, rows):
    p = tmp_path / "pairs.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


# ── 1. fixture 로드(schema validation) ─────────────────────────────────────────────
def test_load_fixture_pairs_ok():
    pairs = load_eval_pairs(_FIXTURE)
    assert len(pairs) >= 20
    assert all(isinstance(p, EvalPair) for p in pairs)
    assert all(p.label in GOLD_LABELS for p in pairs)


def test_fixture_has_all_four_quadrant_intent():
    # 진단 세트는 4사분면(TP/TN/FP/FN) 의도를 risk_tag/pair_id 로 표현 — 균형 확인.
    pairs = load_eval_pairs(_FIXTURE)
    ids = {p.pair_id for p in pairs}
    assert any(i.startswith("fp_") for i in ids)      # hard-negative false positive
    assert any(i.startswith("fn_") for i in ids)      # paraphrase/translation false negative
    assert any(i.startswith("tp_") for i in ids)
    assert any(i.startswith("tn_") for i in ids)
    assert any("hard_negative" in p.risk_tags for p in pairs)
    langs = {p.language for p in pairs}
    assert {"ko", "en", "mixed"} <= langs              # 언어 커버리지


# ── 2. 중복 pair_id 금지 ────────────────────────────────────────────────────────
def test_duplicate_pair_id_rejected(tmp_path):
    p = _write(tmp_path, [_row(pair_id="dup"), _row(pair_id="dup")])
    with pytest.raises(ValueError, match="duplicate pair_id"):
        load_eval_pairs(p)


# ── 3·4·5. label/language/source_type enum 검증 ──────────────────────────────────
def test_invalid_label_rejected(tmp_path):
    p = _write(tmp_path, [_row(label="merge_now")])
    with pytest.raises(ValueError, match="invalid label"):
        load_eval_pairs(p)


def test_invalid_language_rejected(tmp_path):
    p = _write(tmp_path, [_row(language="klingon")])
    with pytest.raises(ValueError, match="invalid language"):
        load_eval_pairs(p)


def test_invalid_source_type_rejected(tmp_path):
    p = _write(tmp_path, [_row(source_type_left="blog")])
    with pytest.raises(ValueError, match="invalid source_type_left"):
        load_eval_pairs(p)


# ── 6·7. raw body / PII-like 필드 금지(allowlist) ────────────────────────────────
def test_raw_body_field_rejected(tmp_path):
    row = _row()
    row["body"] = "full article text that should never be stored in eval set ..."
    p = _write(tmp_path, [row])
    with pytest.raises(ValueError, match="disallowed keys"):
        load_eval_pairs(p)


def test_pii_like_field_rejected(tmp_path):
    for pii in ("author", "email", "phone", "content", "raw_text"):
        row = _row()
        row[pii] = "x"
        p = _write(tmp_path, [row])
        with pytest.raises(ValueError, match="disallowed keys"):
            load_eval_pairs(p)


def test_oversized_title_rejected(tmp_path):
    p = _write(tmp_path, [_row(title_left="A" * 5000)])
    with pytest.raises(ValueError, match="전문 위장 차단|≤"):
        load_eval_pairs(p)


def test_missing_required_key_rejected(tmp_path):
    row = _row()
    del row["title_right"]
    p = _write(tmp_path, [row])
    with pytest.raises(ValueError, match="missing required keys"):
        load_eval_pairs(p)


# ── 8. 결정론 로드(comment/빈 줄 무시·반복 동일) ──────────────────────────────────
def test_deterministic_load_ignores_comments_and_blanks(tmp_path):
    p = tmp_path / "pairs.jsonl"
    p.write_text("# header comment\n\n" + json.dumps(_row(pair_id="a")) + "\n\n# mid\n"
                 + json.dumps(_row(pair_id="b")) + "\n", encoding="utf-8")
    a = load_eval_pairs(p)
    b = load_eval_pairs(p)
    assert [x.pair_id for x in a] == [x.pair_id for x in b] == ["a", "b"]


# ── export worksheet 순수 부분(no-PII 가드·write·summarize; DB 비의존) ──────────────
def _wrow(**kw):
    base = {
        "pair_id": "l1", "label": "unlabeled", "language": "ko",
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "연준 기준금리 인상 결정", "title_right": "연준 기준금리 인상 결정",
        "observed_at_left": "2026-06-24T09:00:00Z", "observed_at_right": "2026-06-24T10:00:00Z",
        "predicted_status": "likely_same_event", "score": 1.0, "reason": "x", "risk_tags": [],
    }
    base.update(kw)
    return base


def test_worksheet_no_pii_guard_rejects_body():
    from backend.app.tools.export_identity_eval_pairs import _assert_no_pii
    bad = _wrow()
    bad["body"] = "full text"
    with pytest.raises(ValueError, match="disallowed keys"):
        _assert_no_pii([bad])


def test_worksheet_write_deterministic(tmp_path):
    from backend.app.tools.export_identity_eval_pairs import write_worksheet_jsonl
    rows = [_wrow(pair_id="a"), _wrow(pair_id="b")]
    out = tmp_path / "w.jsonl"
    n1 = write_worksheet_jsonl(rows, out)
    t1 = out.read_text(encoding="utf-8")
    write_worksheet_jsonl(rows, out)
    assert n1 == 2 and t1 == out.read_text(encoding="utf-8")   # 결정론(sort_keys)


def test_worksheet_summary_counts():
    from backend.app.tools.export_identity_eval_pairs import summarize_adjudication_backlog
    s = summarize_adjudication_backlog([_wrow(pair_id="a"), _wrow(pair_id="b", predicted_status="ambiguous")])
    assert s["total"] == 2 and s["auto_merged"] == 0
    assert s["by_status"]["likely_same_event"] == 1 and s["by_status"]["ambiguous"] == 1


def test_export_language_normalized_to_eval_enum():
    # BUG 회귀: _language_hint 는 script 라벨('latin')을 주지만 export 는 eval language enum('en')으로 정규화.
    from backend.app.tools.export_identity_eval_pairs import _SCRIPT_TO_EVAL_LANGUAGE
    from backend.app.services.identity_eval_dataset import LANGUAGES
    assert _SCRIPT_TO_EVAL_LANGUAGE.get("latin") == "en"
    # 정규화 후 값은 전부 eval LANGUAGES enum 안.
    for v in (_SCRIPT_TO_EVAL_LANGUAGE.get(s, s) for s in ("latin", "ko", "mixed", "unknown")):
        assert v in LANGUAGES


@pytest.mark.parametrize("lang", ["en", "ko", "mixed"])
def test_worksheet_to_gold_roundtrip(tmp_path, lang):
    # export 워크시트(label=unlabeled)를 사람이 gold 로 승격(label 채움·보조 키 제거)하면 load_eval_pairs 통과.
    # 영어 워크시트가 language='latin' 이면 invalid language 로 깨졌을 것 — latin→en 정규화 회귀 방어.
    ws = _wrow(language=lang)
    gold = {k: v for k, v in ws.items() if k not in ("predicted_status", "score", "reason")}
    gold["label"] = "same_event"
    p = tmp_path / "promoted.jsonl"
    p.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    pairs = load_eval_pairs(p)
    assert len(pairs) == 1 and pairs[0].language == lang and pairs[0].label == "same_event"
