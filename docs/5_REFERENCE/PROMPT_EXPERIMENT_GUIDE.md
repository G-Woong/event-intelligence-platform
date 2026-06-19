# PROMPT_EXPERIMENT_GUIDE.md — STEP 005

prompt 파일 추가/수정, 새 노드 연결, OpenAI smoke 테스트, A/B 실험 패턴을 설명한다.

---

## 1. Prompt 파일 추가/수정 방법

### 위치

```
agents/
└── prompts/
    ├── impact_analysis.md
    ├── fact_check.md
    └── summarize.md
```

### 새 prompt 파일 추가

1. `agents/prompts/` 에 `{기능명}.md` 파일을 생성한다.
2. 파일 내용은 자연어 지시문 + `{placeholder}` 조합으로 작성한다.
3. 파일명은 해당 tool helper 함수명과 일치시킨다 (예: `fact_check.md` → `fact_check()` 함수).

### 기존 prompt 수정

- 파일을 직접 편집한다. Python 재시작 없이 반영된다 (`load_prompt`는 매 호출마다 파일 읽기).
- 동작이 크게 달라지는 수정은 아래 A/B 실험 패턴을 사용한다.

---

## 2. str.format Placeholder 규약

모든 placeholder 는 중괄호 단일 쌍 `{이름}` 형식이다.

| placeholder | 타입 | 의미 | STEP 005 임시값 |
|---|---|---|---|
| `{title}` | `str` | 이벤트 제목 | 이벤트 원본 title |
| `{body}` | `str` | 이벤트 본문 | 이벤트 원본 body |
| `{entities}` | `str` (JSON) | 추출된 엔티티 목록 | `json.dumps([])` |
| `{theme}` | `str` | 이벤트 테마 | `event["theme"]` |
| `{past_context}` | `str` | 과거 유사 이벤트 요약 | `"(없음)"` — STEP 006 에서 Milvus 결과로 교체 |
| `{evidence}` | `str` | 팩트체크 근거 텍스트 | 수집된 원문 snippet |
| `{sectors}` | `str` (JSON) | 영향 섹터 목록 | `json.dumps([])` |

규칙:
- JSON 타입 placeholder 는 `json.dumps(value, ensure_ascii=False)` 로 직렬화 후 주입한다.
- 미사용 placeholder 를 prompt 파일에 남겨두면 `str.format()` 에서 `KeyError` 가 발생한다. 반드시 모든 placeholder 에 값을 공급하거나 파일에서 제거한다.
- 빈 값이 허용되는 경우 빈 문자열(`""`) 을 사용한다.

---

## 3. 출력 Schema 위치

모든 structured output schema 클래스는 `agents/tools/llm.py` 에 정의한다.

```python
# agents/tools/llm.py
from pydantic import BaseModel, Field


class ImpactAnalysisOutput(BaseModel):
    severity: str = Field(description="low | medium | high | critical | unknown")
    affected_sectors: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class FactCheckOutput(BaseModel):
    verdict: str = Field(description="confirmed | unconfirmed | false | unknown")
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[str]


class SummaryOutput(BaseModel):
    summary: str
    key_points: list[str]
    tags: list[str]
```

규칙:
- schema 가 늘어나도 `agents/tools/llm.py` 한 파일에 유지한다.
- schema 를 분산시키지 않는다 — tool helper 가 import 경로를 일관되게 유지해야 한다.
- `MockLLMClient.complete_json()` 은 schema 클래스명(`schema.__name__`) 으로 분기해
  고정 픽스처를 반환한다.

---

## 4. 새 노드 추가 절차

4단계를 순서대로 완료해야 한다.

### 4-1. Prompt 파일 작성

`agents/prompts/{기능명}.md` 를 작성한다. placeholder 목록을 확정한다.

### 4-2. Output Schema 정의

`agents/tools/llm.py` 에 `{기능명}Output(BaseModel)` 클래스를 추가한다.

```python
class SentimentOutput(BaseModel):
    sentiment: str = Field(description="positive | neutral | negative")
    intensity: float = Field(ge=0.0, le=1.0)
```

### 4-3. Tool Helper 함수 작성

`agents/tools/llm.py` 에 helper 함수를 추가한다.

```python
def analyze_sentiment(client: BaseLLMClient, event: dict) -> SentimentOutput:
    prompt = load_prompt("sentiment").format(
        title=event["title"],
        body=event["body"],
    )
    result = client.complete_json(prompt, SentimentOutput)
    if result is None:
        return SentimentOutput(sentiment="neutral", intensity=0.0)
    return result
```

### 4-4. LangGraph Node 등록

```python
# agents/graph.py
from agents.tools.llm import analyze_sentiment

def sentiment_node(state: AgentState) -> AgentState:
    result = analyze_sentiment(state["llm_client"], state["event"])
    return {**state, "sentiment": result}

graph.add_node("analyze_sentiment", sentiment_node)
graph.add_edge("previous_node", "analyze_sentiment")
```

---

## 5. OpenAI Smoke 실행법

OpenAI API 를 실제로 호출하는 smoke 테스트는 **opt-in** 이다.
환경변수 `RUN_OPENAI_SMOKE=1` 을 설정해야만 실행된다.

```powershell
# PowerShell — 현재 세션에서만 활성화
$env:RUN_OPENAI_SMOKE="1"
pytest agents/tests/test_openai_smoke.py -q
```

```powershell
# 한 줄로 실행 (세션 오염 없음)
$env:RUN_OPENAI_SMOKE="1"; pytest agents/tests/test_openai_smoke.py -q
```

테스트 파일 내 opt-in 패턴:

```python
# agents/tests/test_openai_smoke.py
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_OPENAI_SMOKE") != "1",
    reason="opt-in: set RUN_OPENAI_SMOKE=1 to run",
)
```

주의:
- CI 파이프라인에서는 `RUN_OPENAI_SMOKE` 를 설정하지 않아 기본적으로 skip 된다.
- `OPENAI_API_KEY` 가 없으면 테스트 내부에서 별도 skip 처리한다.
- smoke 테스트는 실제 API 비용이 발생하므로 최소 호출(1회)로 유지한다.

---

## 6. A/B 실험 패턴 (prompt_versions 필드 활용)

이벤트/분석 결과 모델에 `prompt_versions` 필드를 두어 어떤 버전의 prompt 로
생성된 결과인지 추적한다.

### Schema 확장

```python
class ImpactAnalysisOutput(BaseModel):
    severity: str
    affected_sectors: list[str]
    confidence: float
    rationale: str
    prompt_versions: dict[str, str] = Field(
        default_factory=dict,
        description="실험 추적용. {노드명: prompt 파일명} 형식.",
    )
```

### 호출 시 버전 기록

```python
def analyze_impact(client: BaseLLMClient, event: dict, prompt_name: str = "impact_analysis") -> ImpactAnalysisOutput:
    prompt = load_prompt(prompt_name).format(...)
    result = client.complete_json(prompt, ImpactAnalysisOutput)
    if result is None:
        return ImpactAnalysisOutput(..., prompt_versions={"analyze_impact": prompt_name})
    result.prompt_versions["analyze_impact"] = prompt_name
    return result
```

### 실험 진행 방법

1. 새 버전 prompt 파일을 `impact_analysis_v2.md` 와 같이 별도 파일로 저장한다.
2. 환경변수 또는 설정으로 `prompt_name` 을 분기한다.
3. 결과 DB에 `prompt_versions` 를 JSON 컬럼으로 저장한다.
4. 버전 간 `confidence`, downstream metric 을 비교해 승자를 결정한다.
5. 실험 종료 후 패배 버전 파일을 `agents/prompts/archive/` 로 이동한다.

```python
# 환경변수 기반 분기 예시
import os
prompt_name = os.getenv("IMPACT_PROMPT_VERSION", "impact_analysis")
result = analyze_impact(client, event, prompt_name=prompt_name)
```
