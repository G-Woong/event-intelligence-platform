"""ADR#92 §13 — Hot Post preview guard tests.

검증: public body/comment reply 생성 0·no R1 → public 차단(blocked or internal-only)·no MERGE_GATE → public 차단·
hotness-only/community-only rejected·uncertainty 필수·internal-only placeholder 는 게시 불가.
"""
from __future__ import annotations

from backend.app.tools.hot_post_preview_guard import (
    HPV_BLOCKED,
    HPV_INTERNAL_ONLY,
    build_hot_post_preview_guard,
    sanitized_hot_post_preview_guard,
)


def _valid_internal_draft() -> dict:
    # structural 통과(official evidence anchor·uncertainty·community reaction-only) — 단 gold/merge 부재로 public 차단.
    return {
        "anchor_role": "official",
        "official_evidence": {"url": "https://www.federalregister.gov/doc", "source_type": "official"},
        "uncertainty_summary": "single official source; news corroboration pending",
    }


# ── 50. no public body generated ──
def test_no_public_body_generated():
    out = build_hot_post_preview_guard(_valid_internal_draft())
    assert out["public_post_body_generated"] is False
    assert out["preview_publishable"] is False


# ── 51. no comment reply generated ──
def test_no_comment_reply_generated():
    out = build_hot_post_preview_guard(_valid_internal_draft())
    assert out["comment_reply_generated"] is False


# ── 52. no R1 -> preview blocked or internal-only placeholder (never publishable) ──
def test_no_r1_blocks_public():
    out = build_hot_post_preview_guard()  # empty draft, no gold
    assert out["hot_post_preview_status"] in (HPV_BLOCKED, HPV_INTERNAL_ONLY)
    assert out["requires_r1_gold"] is True
    assert out["hot_post_preview_public_blocked"] is True
    assert out["preview_publishable"] is False


# ── 53. no MERGE_GATE -> public blocked ──
def test_no_merge_gate_blocks_public():
    out = build_hot_post_preview_guard(_valid_internal_draft())
    assert out["requires_merge_gate"] is True
    assert out["hot_post_preview_public_blocked"] is True


# ── 54. hotness-only rejected ──
def test_hotness_only_rejected():
    out = build_hot_post_preview_guard({"hotness_score": 0.95})
    assert out["hot_post_preview_status"] == HPV_BLOCKED
    assert out["preview_allowed_internal_only"] is False
    assert out["official_evidence_present"] is False
    assert out["hotness_alone_preview"] is False


# ── 55. community-only rejected ──
def test_community_only_rejected():
    out = build_hot_post_preview_guard({
        "anchor_role": "community",
        "official_evidence": {"url": "x", "source_type": "official"},
        "uncertainty_summary": "x",
    })
    assert out["hot_post_preview_status"] == HPV_BLOCKED
    assert out["community_used_as_anchor"] is True
    assert out["source_role_guard_passed"] is False


# ── 56. uncertainty required ──
def test_uncertainty_required():
    out = build_hot_post_preview_guard({
        "anchor_role": "official",
        "official_evidence": {"url": "x", "source_type": "official"},
        # no uncertainty_summary
    })
    assert out["hot_post_preview_status"] == HPV_BLOCKED
    assert out["uncertainty_summary_present"] is False
    assert "uncertainty" in out["blocked_reason"].lower()


# ── 57. internal-only placeholder cannot publish ──
def test_internal_only_cannot_publish():
    out = build_hot_post_preview_guard(_valid_internal_draft())
    assert out["hot_post_preview_status"] == HPV_INTERNAL_ONLY
    assert out["preview_allowed_internal_only"] is True
    # internal-only 이지만 게시 불가.
    assert out["preview_publishable"] is False
    assert out["public_post_body_generated"] is False
    assert out["hot_post_preview_public_blocked"] is True


# ── invariants: no same_event / merge / runtime ──
def test_invariants():
    out = build_hot_post_preview_guard(_valid_internal_draft())
    assert out["preview_asserts_same_event"] is False
    assert out["same_event_asserted"] is False
    assert out["merge_allowed"] is False
    assert out["runtime_enabled"] is False
    assert out["r2_r7_no_go"] is True


# ── sanitized projection (frontier 용) ──
def test_sanitized_projection_keys():
    out = build_hot_post_preview_guard()
    s = sanitized_hot_post_preview_guard(out)
    assert set(s.keys()) == {
        "hot_post_preview_status", "hot_post_preview_public_blocked", "preview_allowed_internal_only",
        "public_post_body_generated", "comment_reply_generated",
    }
