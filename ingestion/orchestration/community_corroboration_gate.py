"""Phase G-4 CommunityCorroborationGate — 익명 커뮤니티 신호의 publish 등급 결정.

dcinside 같은 익명 게시판은 community preview signal source로 정식 운영하되, 원문을 그대로
공개(publish)하지 않는다. 본 게이트는 EventQueue record에 publish 등급 metadata를 부여한다:

  - internal_queue_only       : 익명 금융/투자 갤러리 — 자동 publish 금지(내부 큐 적재만).
  - publish_blocked_until_corrob: 펌핑/투자권유성 제목 — 외부 교차확인 전 publish 차단.
  - preview_candidate          : 그 외 커뮤니티 신호 — 외부 확인 시 preview 후보.

원칙(§1 info-not-advice): 매수/매도/투자권유성 신호가 event로 직행하지 않도록 차단하고,
모든 익명 커뮤니티 신호는 requires_external_confirmation=True로 corroboration을 강제한다.
작성자 PII(닉네임)는 애초에 수집하지 않는다(dcinside_strategy). 네트워크 0, stdlib만. 신규 설치 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# publish 등급
PUBLISH_INTERNAL_QUEUE_ONLY = "internal_queue_only"
PUBLISH_BLOCKED_UNTIL_CORROB = "publish_blocked_until_corrob"
PUBLISH_PREVIEW_CANDIDATE = "preview_candidate"

# 익명 금융/투자 갤러리(자동 publish 금지). 알려진 dcinside 주식/코인 갤러리 + 휴리스틱.
_FINANCIAL_GALLERY_IDS = frozenset({"stockus", "stock_new", "neostock", "financ", "coinkorea"})
_FINANCIAL_GALLERY_HINTS = ("stock", "coin", "financ", "invest")

# 펌핑/투자권유성 제목 신호(매수/매도/목표가 등 가치판단·권유). 정보가 아니라 권유 → publish 차단.
_SOLICITATION_MARKERS = (
    "매수", "매도", "풀매수", "풀매도", "사라", "팔아", "들어가", "가즈아", "가즈앗",
    "떡상", "떡락", "상한가", "하한가", "목표가", "익절", "손절", "존버", "추천주", "급등주",
    "buy now", "sell now", "to the moon", "all in", "pump",
)


@dataclass(frozen=True)
class CommunityCorroborationDecision:
    source_id: str
    gallery_id: Optional[str]
    title: Optional[str]
    source_url: Optional[str]
    published_at: Optional[str]
    risk_tags: tuple[str, ...]
    requires_external_confirmation: bool
    publish_level: str


def _is_financial_gallery(gallery_id: Optional[str]) -> bool:
    if not gallery_id:
        return False
    g = gallery_id.lower()
    if g in _FINANCIAL_GALLERY_IDS:
        return True
    return any(h in g for h in _FINANCIAL_GALLERY_HINTS)


def _detect_solicitation(title: Optional[str]) -> bool:
    if not title:
        return False
    low = title.lower()
    return any(m in title or m in low for m in _SOLICITATION_MARKERS)


def evaluate_community_corroboration(
    *,
    source_id: str,
    gallery_id: Optional[str] = None,
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    published_at: Optional[str] = None,
) -> CommunityCorroborationDecision:
    """커뮤니티 신호 1건 → publish 등급 결정. 익명 source는 항상 외부확인 필수.

    우선순위: 금융 갤러리(internal_queue_only) > 펌핑/권유 제목(publish_blocked) > preview_candidate.
    """
    risk_tags: list[str] = ["anonymous_community"]
    financial = _is_financial_gallery(gallery_id)
    solicitation = _detect_solicitation(title)
    if financial:
        risk_tags.append("anonymous_financial_board")
    if solicitation:
        risk_tags.append("investment_solicitation_or_pump")

    if financial:
        publish_level = PUBLISH_INTERNAL_QUEUE_ONLY
    elif solicitation:
        publish_level = PUBLISH_BLOCKED_UNTIL_CORROB
    else:
        publish_level = PUBLISH_PREVIEW_CANDIDATE

    return CommunityCorroborationDecision(
        source_id=source_id, gallery_id=gallery_id, title=title,
        source_url=source_url, published_at=published_at,
        risk_tags=tuple(risk_tags), requires_external_confirmation=True,
        publish_level=publish_level,
    )


def annotate_records(records, *, source_id: str, gallery_id: Optional[str] = None) -> list[dict]:
    """community_signal record 목록에 corroboration metadata를 부여(EventQueue 적재 전).

    원본 record는 변경하지 않고 사본에 metadata 필드를 추가한다. publish_level/risk_tags/
    requires_external_confirmation을 record에 싣는다(하위 quality/safety gate가 소비).
    """
    out: list[dict] = []
    for r in records:
        d = dict(r)
        decision = evaluate_community_corroboration(
            source_id=source_id, gallery_id=gallery_id,
            title=d.get("title_or_label"), source_url=d.get("source_url_or_evidence"),
            published_at=d.get("published_at_or_observed_at"),
        )
        d["publish_level"] = decision.publish_level
        d["requires_external_confirmation"] = decision.requires_external_confirmation
        d["corroboration_risk_tags"] = list(decision.risk_tags)
        out.append(d)
    return out
