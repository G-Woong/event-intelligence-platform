# LLM_AGENT_DESIGN.md — STEP 005

이 문서는 STEP 005 에서 도입한 LLM 클라이언트 추상화, Provider 확장 방법,
structured output 정책, fallback 전략, prompt 관리 규약을 정의한다.

---

## 1. BaseLLMClient 계약

```python
# agents/llm_client.py
from typing import Protocol, Type
from pydantic import BaseModel


class BaseLLMClient(Protocol):
    """모든 LLM Provider가 구현해야 하는 최소 계약."""

    def complete(self, prompt: str) -> str:
        """자유 형식 텍스트 응답을 반환한다."""
        ...

    def complete_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel | None:
        """prompt를 전송하고 schema 인스턴스를 반환한다.
        파싱 실패 또는 API 오류 시 None을 반환한다.
        """
        ...
```

### 계약 규칙

- `complete_json`은 절대 예외를 외부로 전파하지 않는다. 내부에서 잡고 `None` 반환.
- `complete`는 API 호출 자체 오류(`httpx.TimeoutException` 등)만 `LLMClientError`로 래핑해 전파.
- 인스턴스는 stateless — 메서드 간 상태 공유 없음.
- timeout / max_tokens / temperature는 생성자에서 받고 메서드 시그니처에 노출하지 않는다.

---

## 2. Provider 추가 절차 (LocalSLLMClient 예시)

로컬에서 Ollama 등 SLLM을 사용하고 싶을 때 새 Provider를 추가하는 4단계 절차.

### 2-1. 클라이언트 파일 생성

```
agents/llm_client.py          ← BaseLLMClient Protocol 정의 (기존)
agents/providers/
    openai_client.py          ← OpenAILLMClient (STEP 005 기본 구현)
    local_client.py           ← LocalSLLMClient (신규)
    mock_client.py            ← MockLLMClient (테스트 전용)
```

`local_client.py` 최소 골격:

```python
import json
import httpx
from pydantic import BaseModel
from typing import Type


class LocalSLLMClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout_sec: float = 30.0,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout = timeout_sec
        self._max_tokens = max_tokens
        self._temperature = temperature

    def complete(self, prompt: str) -> str:
        response = httpx.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["response"]

    def complete_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel | None:
        try:
            raw = self.complete(prompt)
            return schema.model_validate(json.loads(raw))
        except Exception:
            return None
```

### 2-2. Settings에 필드 추가

```python
# backend/app/config.py  (또는 agents/config.py)
LLM_PROVIDER: str = "openai"   # "openai" | "local"
LLM_MODEL: str = "gpt-4o-mini"
LLM_TIMEOUT_SEC: float = 30.0
LLM_MAX_TOKENS: int = 512
LLM_TEMPERATURE: float = 0.0
```

### 2-3. 팩토리 함수 등록

```python
# agents/llm_client.py
def make_llm_client(settings) -> BaseLLMClient:
    if settings.LLM_PROVIDER == "local":
        from agents.providers.local_client import LocalSLLMClient
        return LocalSLLMClient(
            model=settings.LLM_MODEL,
            timeout_sec=settings.LLM_TIMEOUT_SEC,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
        )
    from agents.providers.openai_client import OpenAILLMClient
    return OpenAILLMClient(
        model=settings.LLM_MODEL,
        timeout_sec=settings.LLM_TIMEOUT_SEC,
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=settings.LLM_TEMPERATURE,
    )
```

### 2-4. docker-compose.dev.yml에 환경변수 추가

```yaml
agent-worker:
  environment:
    LLM_PROVIDER: local
    LLM_MODEL: llama3
```

---

## 3. Structured Output 정책

**원칙: 순수 Pydantic + `json.loads`. instructor / pydantic-ai 미도입.**

이유:
- 의존성 최소화. instructor, pydantic-ai 는 STEP 005 범위에서 추가 이점이 없음.
- OpenAI `response_format={"type": "json_object"}` + 시스템 프롬프트로 충분.
- 필요 시 STEP 007+ 에서 instructor 도입 여부 재검토.

구현 패턴:

```python
# agents/providers/openai_client.py
import json
from pydantic import BaseModel
from typing import Type
import openai


class OpenAILLMClient:
    def complete_json(self, prompt: str, schema: Type[BaseModel]) -> BaseModel | None:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"Respond ONLY with valid JSON matching this schema:\n"
                            f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            raw = response.choices[0].message.content or ""
            return schema.model_validate(json.loads(raw))
        except Exception:
            return None
```

schema 클래스는 `agents/tools/llm.py` 에 모아서 정의한다 (아래 섹션 참조).

---

## 4. Fallback 정책

```
complete_json() 실패
    └─ None 반환
         └─ tool helper 함수에서 기본값(fallback) 반환
```

tool helper 예시:

```python
# agents/tools/llm.py

def analyze_impact(client: BaseLLMClient, event: dict) -> ImpactAnalysisOutput:
    prompt = load_prompt("impact_analysis").format(**event)
    result = client.complete_json(prompt, ImpactAnalysisOutput)
    if result is None:
        return ImpactAnalysisOutput(
            severity="unknown",
            affected_sectors=[],
            confidence=0.0,
            rationale="LLM unavailable — fallback default",
        )
    return result
```

규칙:
- fallback 값은 downstream 노드가 처리 가능한 최소 안전 값이어야 한다.
- fallback 발생 시 로그레벨 `WARNING` 으로 기록한다.
- fallback 값에 sentinel(`confidence=0.0`)을 포함해 후처리가 탐지 가능하게 한다.

---

## 5. Prompt 디렉터리 규약

```
agents/
└── prompts/
    ├── impact_analysis.md
    ├── fact_check.md
    └── summarize.md
```

### load_prompt()

```python
# agents/tools/llm.py
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """agents/prompts/{name}.md 를 읽어 반환한다."""
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
```

### Placeholder 규약

프롬프트 파일 내에서 `str.format()` placeholder 를 사용한다.

| placeholder | 의미 |
|---|---|
| `{title}` | 이벤트 제목 |
| `{body}` | 이벤트 본문 |
| `{entities}` | 추출된 엔티티 목록 (JSON 문자열) |
| `{theme}` | 이벤트 테마 (예: `"geopolitics"`) |
| `{past_context}` | 과거 유사 이벤트 요약 (RAG 결과, STEP 006 대상) |
| `{evidence}` | 팩트체크 근거 텍스트 |
| `{sectors}` | 영향 섹터 목록 (JSON 문자열) |

프롬프트 파일 예시:

```markdown
당신은 글로벌 사건 분석가입니다.

아래 이벤트를 분석하고 영향도를 평가하세요.

제목: {title}
본문: {body}
관련 엔티티: {entities}
테마: {theme}
과거 유사 사례: {past_context}

JSON 형식으로만 응답하세요.
```

호출:

```python
prompt = load_prompt("impact_analysis").format(
    title=event["title"],
    body=event["body"],
    entities=json.dumps(event["entities"], ensure_ascii=False),
    theme=event["theme"],
    past_context="(없음)",   # STEP 006 이전 임시값
)
```

---

## 6. RAG Node 연결 방법 (STEP 006 대상)

현재 STEP 005 에서 `past_context` 는 빈 문자열 또는 `"(없음)"` 임시값을 사용한다.

STEP 006 에서 Milvus retrieval 노드를 `retrieve_past_context` 자리에 끼운다:

```
현재 (STEP 005):
  analyze_impact_node
      └─ past_context = "(없음)"

STEP 006 이후:
  retrieve_past_context_node   ← Milvus ANN 검색 결과 주입
      └─ analyze_impact_node
              └─ past_context = retrieved_chunks
```

LangGraph 연결 패턴 (STEP 006 적용 예시):

```python
graph.add_node("retrieve_past_context", retrieve_past_context_node)
graph.add_node("analyze_impact", analyze_impact_node)
graph.add_edge("retrieve_past_context", "analyze_impact")
```

`retrieve_past_context_node` 내부에서 Milvus 클라이언트를 호출하고
결과를 state의 `past_context` 필드에 저장한다.

---

## 7. Retrieval 백엔드 로드맵

| 기술 | 도입 STEP | 비고 |
|---|---|---|
| Milvus ANN retrieval | **STEP 006** | primary vector store, 이미 인프라 준비됨 |
| OpenSearch full-text | 먼 미래 STEP | keyword 검색 보완, 도입 여부 미결정 |

---

## 8. LangChain / Runnable 정책

STEP 005 는 **raw openai SDK** 만 사용한다.

- `langchain`, `langchain-openai` 등 LangChain Runnable wrapper 는 미도입.
- LangChain 도입 시점: RAG 파이프라인(STEP 006) 또는 LangGraph 그래프 통합 확대 시 재검토.
- LangSmith tracing 은 별도 SDK(`langsmith`)로 처리하므로 LangChain 없이도 가능.
