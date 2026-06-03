# Agentic Crawling Pipeline

독립 실험 파이프라인 — 30개 소스의 운영 가능성 진단.

## 목적

RSS 외 임의 웹 소스에서 본문을 안정적으로 추출할 수 있는지 검증하고, source별 운영 가능성 진단 결과를 logger/report로 완전 추적한다.

## 구조

```
crawling/
  plans/       설계 문서 (00~07)
  configs/     YAML 설정 (source_registry, policy 등)
  core/        DataClass + 비즈니스 로직 (error_taxonomy, quality_score 등)
  schemas/     Pydantic v2 모델 (raw_document, extracted_article 등)
  agents/      LangGraph 14-node pipeline (state, graph, nodes, llm_judge)
  tools/       추출 도구 래퍼 (playwright, readability, trafilatura 등)
  sources/     소스별 crawl 전략 (base.py + 30개 *.py)
  runners/     CLI 진입점 (run_one_source, run_phase 등)
  logs/        JSONL 로그 (runs/, attempts/, errors/)
  outputs/     산출물 (reports/, extracted_text/, screenshots/ 등)
  tests/       pytest 단위 테스트
```

## 실행 (Step A 검증)

```powershell
# 의존성 설치 (최초 1회)
uv pip install -r requirements/crawler.txt -r requirements/ai.txt
python -m playwright install chromium

# dummy source smoke test
python -m crawling.runners.run_one_source --source _dummy

# 단위 테스트
pytest crawling/tests/ -v

# graph 노드 확인
python -c "from crawling.agents.graph import build_graph; g=build_graph(); print(list(g.get_graph().nodes))"
```

## 주요 설계 원칙

- **기존 서비스와 완전 분리**: backend/frontend/agents/workers import 없음.
- **무리한 우회 금지**: CAPTCHA/로그인/paywall/robots 차단 시 `BLOCKED_*` 기록 후 중단.
- **HTML → LLM 직접 전달 금지**: DOM heuristic으로 후보 블록 축소 후 title/metadata만 전달.
- **모든 LLM 출력 Pydantic 검증**: `complete_json(schema=...)` 패턴.
- **SecretMaskingFilter**: `.env` 키 값이 로그에 노출되지 않음.
