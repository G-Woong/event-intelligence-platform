# 07_VALIDATION_AND_REPORTING_PLAN — 검증 기준 + 보고서 형식

## 품질 판정 기준

| 상태 | 조건 |
|---|---|
| SUCCESS | quality_score >= 0.70 AND not blocked |
| PARTIAL | 0.40 <= quality_score < 0.70 AND not blocked |
| BLOCKED | CAPTCHA / 로그인 / paywall / robots 감지 |
| FAILED | quality_score < 0.40 AND not blocked |

---

## 10개 품질 지표 (가중합)

| 지표 | 가중치 | 설명 |
|---|---|---|
| title_present | 0.15 | title 비어있지 않음 |
| body_length | 0.20 | source_type별 min/max 기준 정규화 |
| body_text_ratio | 0.10 | 텍스트 비율 |
| published_at_present | 0.10 | 날짜 추출 성공 |
| author_present | 0.05 | 저자 추출 성공 |
| language_detected | 0.10 | 언어 감지 성공 |
| boilerplate_ratio | 0.15 | 낮을수록 좋음 (1 - ratio) |
| sentence_count | 0.05 | 10문장 이상이면 만점 |
| keyword_density | 0.05 | 고유 단어 비율 (10% = 만점) |
| metadata_completeness | 0.05 | OG/meta 필드 완성도 |

body_length 기준:

| source_type | min | full |
|---|---|---|
| news | 300 | 1500 |
| community | 50 | 500 |
| official | 200 | 1000 |

---

## 소스별 Report 필드

```
source_id, source_name, source_type, evidence_level, phase, run_at
status, quality_score, attempts, strategy_used
urls_crawled, articles_extracted, event_candidates_found
errors[], known_blockers_hit[], recommended_action, notes
```

파일: `outputs/reports/{source_id}_report.md` + `{source_id}_report.jsonl`

---

## Phase 요약 Report

파일: `outputs/reports/phase{n}_summary.md`

```
| Source | Status | Score | Strategy | Attempts |
|---|---|---|---|---|
| BBC News | SUCCESS | 0.823 | readability | 1 |
...
Total: 10  SUCCESS: 7  PARTIAL: 2  BLOCKED: 1  FAILED: 0
```

---

## 운영 가능성 진단 기준

| 판정 | 권장 조치 |
|---|---|
| SUCCESS | Phase C+ 실운영 편입 검토 |
| PARTIAL | 전략 튜닝(DOM selector, UA 변경) 후 재시도 |
| BLOCKED (paywall/login) | API 대체 또는 운영 범위 제외 |
| BLOCKED (CAPTCHA) | Playwright 세션 관리 또는 운영 범위 제외 |
| FAILED | 근본 원인 분석 후 Step F 개선 작업 |

---

## End-to-End 검증 체크리스트

- [ ] `python -m crawling.runners.run_one_source --source _dummy` → 보고서 생성 확인
- [ ] `crawling/logs/runs/_dummy_runs.jsonl` 존재
- [ ] `crawling/outputs/reports/_dummy_report.md` 존재
- [ ] `build_graph()` 노드 14개 확인
- [ ] `pytest crawling/tests/ -v` 전체 통과
- [ ] 로그에 OPENAI_API_KEY 값 미노출 확인
