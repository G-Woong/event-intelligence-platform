from __future__ import annotations

import os
import pytest

RUN = os.getenv("RUN_OPENAI_SMOKE") == "1"


@pytest.mark.skipif(not RUN, reason="RUN_OPENAI_SMOKE=1로만 실행")
def test_openai_complete_returns_string():
    from backend.app.services.llm_client import OpenAILLMClient, reset_llm_client_cache
    reset_llm_client_cache()

    client = OpenAILLMClient()
    prompt = "Reply with a single word: OK"
    result = client.complete(prompt, max_tokens=10)

    assert isinstance(result, str)
    assert len(result) > 0
    # 키 값 절대 미노출 — 길이/타입만 보고
    print(f"[smoke] OpenAI response len={len(result)}")
    reset_llm_client_cache()
