# 00_MASTER_PLAN — Agentic Crawling Pipeline

## 목적

RSS 수집기(`workers/collectors/`) 외, **임의 웹 소스 본문을 안정적으로 추출**하고
source별 운영 가능성(SUCCESS / PARTIAL / BLOCKED / FAILED)을 진단하는 실험 파이프라인.

기존 backend/frontend/agents/workers는 **읽기 참조만** — 직접 수정·import 금지.

---

## 폴더 구조

```
crawling/
  plans/         설계 문서 (이 파일 포함 8종)
  configs/       YAML (source_registry, phase1~3, extraction/retry/llm/playwright policy)
  core/          DataClass + 비즈니스 로직
  schemas/       Pydantic v2 모델 6종
  agents/        LangGraph 14-node state machine
  tools/         추출 도구 래퍼 (playwright, readability, trafilatura …)
  sources/       base.py + 소스별 SourceCrawler (_dummy 포함, 30개는 Step C~E)
  runners/       CLI 진입점
  logs/          JSONL 로그 (runs/attempts/errors)
  outputs/       보고서 + 추출 결과 + 스크린샷
  tests/         pytest 단위 테스트
```

---

## 원칙

1. **분리** — `crawling/`은 독립 패키지. 기존 서비스 모듈 import 안 함.
2. **무리한 우회 금지** — CAPTCHA/로그인/paywall/robots 차단 시 `BLOCKED_*` 기록 후 중단.
3. **HTML → LLM 직접 전달 금지** — DOM heuristic으로 후보 블록 축소 후 title/metadata 만 전달.
4. **모든 LLM 출력 Pydantic 검증** — `complete_json(schema=...)`.
5. **SecretMaskingFilter** — 모든 로그에 `.env` 키 값 노출 없음.
6. **정보 제공** — 투자 조언·매수/매도 표현 금지.

---

## 4단계 로드맵

| Step | 내용 | 상태 |
|---|---|---|
| A | Skeleton (core, schemas, agents/graph, tools, _dummy, tests) | **완료** |
| B | Agent Graph (14 nodes, mock LLM, playwright wrapper) | **완료** |
| C | Phase 1 — 기사형 뉴스 10개 실구현 | 다음 라운드 |
| D | Phase 2 — 커뮤니티 10개 실구현 | 다음 라운드 |
| E | Phase 3 — 공식 데이터 10개 실구현 | 다음 라운드 |
| F | Error-driven 개선 (retry 조정, DOM 선택자 튜닝) | 다음 라운드 |

---

## 의존성

```text
requirements/crawler.txt  — playwright, trafilatura, readability-lxml, bs4, httpx
requirements/ai.txt       — langgraph, langchain, openai, tenacity
```

```powershell
uv pip install -r requirements/crawler.txt -r requirements/ai.txt
python -m playwright install chromium
```

---

## 검증 명령

```powershell
# Step A+B smoke test
python -m crawling.runners.run_one_source --source _dummy

# graph 노드 수 확인
python -c "from crawling.agents.graph import build_graph; g=build_graph(); print(list(g.get_graph().nodes))"

# 단위 테스트
pytest crawling/tests/ -v

# playwright smoke
python -c "import asyncio; from crawling.tools.playwright_browser_tool import dom_snapshot; print(asyncio.run(dom_snapshot('https://example.com'))[:200])"
```
