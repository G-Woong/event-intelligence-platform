# 04_AGENT_PIPELINE_DESIGN — LangGraph 14-Node Graph

## 목적

source별 크롤링·추출·품질 판정·이벤트 추출의 전 과정을 14개 LangGraph 노드로 구성.
retry / error_analysis 분기 엣지가 핵심.

---

## State: CrawlingAgentState

`crawling/agents/state.py` — TypedDict 전체 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| source_id | str | 소스 ID |
| source_spec | dict | SourceSpec 직렬화 |
| phase | int | 1/2/3/0(_dummy) |
| attempt_no | int | 현재 시도 번호 (0-indexed) |
| max_attempts | int | 최대 시도 횟수 |
| strategy_sequence | list[str] | 10개 전략 순서 |
| current_strategy | str | 현재 활성 전략 |
| strategies_tried | list[str] | 시도한 전략 목록 |
| entry_url | str | 진입 URL |
| candidate_urls | list[str] | 후보 URL 목록 |
| current_url | str | 현재 처리 중인 URL |
| raw_html | str? | 현재 fetch 결과 HTML |
| extraction_result | dict? | 추출 결과 (title/body/…) |
| quality_score | float | 품질 점수 (0.0~1.0) |
| quality_status | str | SUCCESS/PARTIAL/BLOCKED/FAILED |
| event_candidates | list[dict] | LLM 추출 이벤트 후보 |
| errors | list[dict] | 누적 ErrorRecord 목록 |
| current_error | dict? | 현재 오류 |
| llm_judge_result | dict? | LLM 판정 결과 |
| screenshots | list[str] | 스크린샷 경로 목록 |
| dom_snapshots | list[str] | DOM 스냅샷 경로 목록 |
| status | str | RUNNING/SUCCESS/PARTIAL/BLOCKED/FAILED |
| should_retry | bool | 재시도 여부 |
| retry_reason | str | 재시도 이유 |
| strategy_exhausted | bool | 전략 소진 여부 |
| final_report | dict? | 최종 보고서 |

---

## 14개 노드

| # | 노드 | 설명 |
|---|---|---|
| 1 | initialize | 상태 초기화 |
| 2 | build_search_query | 진입 URL 결정 |
| 3 | fetch_entry_url | 진입 페이지 fetch |
| 4 | extract_candidate_urls | 후보 URL 파싱 |
| 5 | fetch_target_page | 타겟 페이지 fetch (전략 적용) |
| 6 | select_extraction_strategy | 다음 전략 선택 |
| 7 | extract_content | 본문 추출 |
| 8 | score_quality | 품질 점수 계산 |
| 9 | retry_decision | 재시도/통과/소진 결정 |
| 10 | error_analysis | 오류 분류 (ErrorType) |
| 11 | extract_event_candidates | 이벤트 후보 LLM 추출 |
| 12 | llm_quality_judge | LLM 품질 판정 |
| 13 | strategy_reflection | 전략 회고 기록 |
| 14 | write_source_report | 최종 report 생성 |

---

## 엣지 / 분기

```
initialize → build_search_query → fetch_entry_url
  ↓ success                        ↓ error
extract_candidate_urls          error_analysis
  ↓                                 ↓
fetch_target_page ←── retry ── retry_decision
  ↓ success    ↓ error               ↓ pass         ↓ exhaust
select_strategy  error_analysis  extract_events  strategy_reflection
  ↓                                  ↓               ↓
extract_content                 llm_judge      write_report → END
  ↓ success  ↓ error               ↓
score_quality  error_analysis  strategy_reflection
  ↓                               ↓
retry_decision                write_report → END
```

---

## LLM 사용 위치

- `extract_event_candidates`: title + body[:500] → EventCandidate (Pydantic 검증)
- `llm_quality_judge`: title + body[:300] → JudgeOutput (is_valid, confidence, reason)
- **HTML 전체 전달 금지** — DOM 축소 후 metadata/snippet 만 전달.

---

## Mock → OpenAI 전환

`LLM_PROVIDER=openai` 환경변수로 전환.
비용 발생 시점: Step C+ Phase 1 실소스 검증 시.
