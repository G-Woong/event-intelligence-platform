# Round 2 Preflight Audit

> 작성: Round 1.5 감사 결과 (2026-06-03).

## 완료 (DONE)

| 항목 | 상태 |
|---|---|
| `crawling/ -> ingestion/` 평면 rename | DONE (Round 1) |
| 보안 env 툴링 (env_loader + check_env_hygiene) | DONE (Round 1) |
| dry-run connectivity harness (31개 소스) | DONE (Round 1) |
| COMPLIANCE_BOUNDARY.md 초안 | DONE (Round 1) |
| CAPTCHA taxonomy fix (`solve the captcha` 신호 추가) | DONE (Round 1.5) |
| Product Hunt 키명 정합성 (ACCESS_TOKEN alias) | DONE (Round 1.5) |
| EU Press Corner PLAYWRIGHT_REQUIRED override | DONE (Round 1.5) |
| layer 재분류 (뉴스 fast_signal → document_discovery) | DONE (Round 1.5) |
| `SourceSpec.layer` first-class 필드 추가 | DONE (Round 1.5) |
| source_registry.yaml Phase 4 확장 소스 등재 | DONE (Round 1.5) |
| pipeline 6모듈 스캐폴드 | DONE (Round 1.5) |
| `_SOURCE_MAP` 31개 import 검증 안전망 테스트 | DONE (Round 1.5) |
| sources/ 하위폴더 scaffold (news/community/official/search/media/blocked) | DONE (Round 1.5) |
| COMPLIANCE_BOUNDARY.md 현실화 | DONE (Round 1.5) |
| 확장 소스 ~26개 registry/docs/env 등재 | DONE (Round 1.5) |

## 부분 완료 (PARTIAL)

| 항목 | 상태 | 이유 |
|---|---|---|
| connectivity report 확장 소스 포함 재생성 | PARTIAL | runner 실행 필요 (코드 준비 완료) |

## 이연 (DEFERRED)

| 항목 | 이유 |
|---|---|
| sources/ 소스 파일 물리 이동 + `_SOURCE_MAP` dotted-path 재작성 | 안전망 테스트 확보 후 다음 라운드 |
| 모든 확장 소스 `--live` 실호출 + 실제 응답 기반 status | API 키 발급 후 Round 2 |
| Playwright 실제 구현 (KRX KIND, EU Press Corner) | Round 2 |
| pipeline 모듈 실제 로직 (LLM judge, Redis Stream, clustering) | Round 2 |
| fast_signal external scrape 가능성 평가 (signal_bz, loword) | Round 2 |

## 실패 테스트 (Round 1 pre-existing)

| 테스트 | 원인 | 해결 |
|---|---|---|
| `test_classify_content_blocker_captcha` | `"solve the captcha"` 신호 미등록 | Round 1.5에서 해결 (A1) |

## 보안 확인

- dry-run 결과 (MD + JSONL) 에 API 키·토큰·Authorization 헤더 없음 확인 (`test_dry_run_output_contains_no_secrets` PASS)
- `.env` 실값 미노출 — `env_status()` "present"/"missing"만 반환
- 신규 status `EXTERNAL_SIGNAL_SOURCE` — 키 없음, `keys_checked: []`

## 누락 확인된 항목

- EU Press Corner: `NO_KEY_REQUIRED`(ready) 오인 → `PLAYWRIGHT_REQUIRED`로 교정
- 뉴스 소스 layer `fast_signal` → `document_discovery` 재분류
- Product Hunt 키명 불일치 → ACCESS_TOKEN/alias 정합성 확보
