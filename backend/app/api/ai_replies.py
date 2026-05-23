from __future__ import annotations

from fastapi import APIRouter
from backend.app.schemas.comments import AIReplyRequest
from backend.app.services.llm_client import LLMClient

router = APIRouter(prefix="/api/ai-replies", tags=["ai-replies"])
_client = LLMClient(provider="mock")


@router.post("/request")
def request_ai_reply(req: AIReplyRequest) -> dict:
    reply = _client.complete(f"event_id={req.event_id} hint={req.prompt_hint}")
    return {"event_id": req.event_id, "reply": reply}
