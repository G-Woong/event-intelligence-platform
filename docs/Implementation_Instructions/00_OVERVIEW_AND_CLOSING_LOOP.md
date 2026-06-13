# 00. 소스 연결 문제 Closing 라운드 — 총괄 지시서 + 종결 루프 설계

> **이 디렉토리의 모든 문서는 "구현 지시 상세 명령서"다.**
> 실행 주체: Claude Sonnet 등 하위 모델 또는 에이전트 오케스트레이션.
> 각 문서는 ① 해석(왜) ② 설명(무엇을) ③ 구현 diff(어떻게) ④ 검증(어떻게 확인) 4요소를 전부 포함한다.
> 이 00 문서를 **반드시 먼저 정독**한 후 01 → 10 순서로 진행하라.

---

## 0. 절대 제약 (CLAUDE.md 상속 — 위반 시 즉시 중단)

1. `.env`의 실제 키 값을 **출력·로그·문서 저장 금지**. 키는 NAME과 존재 여부만 보고.
2. `rm`/`Remove-Item`/`git reset --hard`/`git clean`/`git push` **금지**.
3. CAPTCHA/Turnstile/로그인/페이월 **우회 금지** — 감지 시 해당 소스는 `BLOCKED_TERMINAL`로 문서화하고 종료 (fmkorea가 선례).
4. 보고는 **한국어**. 모르면 `UNKNOWN`, 막히면 `BLOCKED` 명시. 추측을 사실처럼 적지 말 것.
5. 원문 전문을 보고서에 복사 금지 — sample은 title 120자 / snippet 200자 절단 (기존 `_audit_common` 규칙).
6. live 호출은 소스당 검증 목적 최소 횟수만. quota 민감 소스(newsapi 100/day, alpha_vantage 25/day, nyt 500/day)는 검증 1~2회로 제한.
7. 모든 검증 명령은 `.\.venv\Scripts\python.exe` 로 실행 (Windows PowerShell 5.1, venv Python 3.11).
8. **pytest 기준선: 509 passed, 0 failed.** 어떤 단계든 변경 후 이 기준선이 깨지면 다음 단계로 넘어가지 말고 즉시 수정.

## 1. 라운드 목표 (직전 라운드 docs/85~93에서 이월된 미해결 전량)

직전 Live Collection Audit(판정 A)에서 "완전 성공이 아닌" 항목 전부를 닫는다. 대상과 담당 문서:

| # | 문제 | 출처(증거) | 담당 문서 | 종결 기준 |
|---|------|-----------|----------|----------|
| 1 | **RISK-T04**: Route 1(API) 429 시 cooldown 미기록 — `record_rate_limited` 미호출 + `ProbeResult.next_retry_at` 미설정 → health gate `should_skip` 무력화 | docs/90 §3 | **01** | 단위 테스트로 429→cooldown 기록 검증 + 기존 509 테스트 통과 |
| 2 | **gdelt**: 단일 호출에도 429, 2차에서 PARSE_ERROR(비-JSON 200 응답) — 실측 3/3 실패 | docs/88, docs/89 §5-2 | **02** | live 1회 LIVE_SUCCESS + phrase quoting 단위 테스트 + 비-JSON 응답 분류 테스트 |
| 3 | **ap_news**: RSS endpoint가 HTML 에러 페이지 반환 (`API_RETURNED_HTML_ERROR_PAGE`) | docs/88 | **03** | 대체 경로로 live 1회 title+url+timestamp 확보 |
| 4 | **newsapi**: top-headlines + q 조합 0건×2 | docs/89 §5-1 | **04** | `/v2/everything` 전환 후 live 1회 items≥1 + relevance high |
| 5 | **google_trends_explore**: DEFERRED(opt-in 기본 off) — 활용 경로 미검증 | docs/93 §2-17 | **05** | gate 준수 단일 live 호출로 keyword 추출 또는 429 시 cooldown 동작 입증 |
| 6 | **selector 미매칭 4종**: loword / google_trending_now / dcinside / eu_press_corner — page title만 추출 | docs/88 (RISK-S05) | **06+07** | 각 소스 실데이터 item ≥3건 추출 (page title fallback 아님) |
| 7 | **signal_bz**: keyword 3건은 성공했으나 rank/본문 보강 필요 | docs/88 | **07** | keyword ≥10건 + rank 메타 |
| 8 | **커뮤니티 검색 영구 path**: dcinside 검색 페이지 → 본문 추출 경로 부재 | 사용자 지시 | **07** | query → 검색 → 게시글 본문 추출 e2e 1회 성공 |
| 9 | **federal_register**: url/date 필드 부재 (fields[] 제한이 원인) | docs/88 | **08** | live 1회 url+publication_date 포함 sample |
| 10 | **igdb / culture_info**: timestamp/url 필드 부재 (partial) | docs/88 | **08** | sample에 날짜 필드 포함 |
| 11 | **hacker_news**: story id 목록만 — item detail 2차 호출 미설계 | docs/88 | **08** | title+url+time 포함 sample ≥3건 |
| 12 | **bok_ecos / eia / its**: `_SAMPLE_PATHS` 매핑 부재로 평가 불가 | docs/88 | **08** | sample 추출 단위 테스트 (저장된 artifact 기반, 네트워크 불필요) |
| 13 | **시장 수치 소스 seed_ready=no** (finnhub/alpha_vantage/polygon/coinbase): seed 필드 체계가 부적합 | docs/88 §3-5 | **08** | numeric_signal 평가 경로 신설로 분류 종결 |
| 14 | **장문 query 0건** (RISK-Q05): opendart 공시명 그대로 전달 | docs/89 §5-4 | **02 §6** | query 절단 헬퍼 + 테스트 |
| 15 | **상용 기법/의존성 흡수**: 구조 탐색, 본문 추출, API 스니핑, 프레임워크/MCP | 사용자 지시 | **06+09** | 의존성 점검 PASS + 기법별 테스트 설계 |

## 2. 적용 순서와 의존 관계 (반드시 이 순서)

```
01 (인프라 429)  ──→ 02 (gdelt)        : gdelt 검증은 01의 cooldown 기록에 의존
                ──→ 05 (trends_explore): 429 발생 시 01의 기록 경로로 보호됨
03 (ap_news), 04 (newsapi)             : 01 이후 아무 때나 (독립)
06 (구조 탐색 툴킷)  ──→ 07 (selector 소스 5종) : 07은 06의 runner를 사용
08 (API 소스 보강)                      : 01 이후 독립
09 (의존성/고급 기법)                    : 06 이전에 §1(의존성 점검)만 선행 실행, 나머지는 병행
10 (최종 체크리스트)                     : 전부 끝난 뒤
```

근거: 01은 모든 live 재검증의 안전망(429 재발 시 cooldown이 실제로 기록되어야 무한 재호출이 차단됨)이므로 최우선. 06은 07의 도구를 만든다. 09 §1(playwright chromium 설치 확인 등)은 06/07의 전제 조건.

## 3. 종결 루프 설계 (CLOSING LOOP) — 이 라운드의 핵심 운용 규칙

**이 섹션은 모든 담당 문서(01~08)의 작업에 공통 적용되는 마스터 루프다. 어떤 소스도 이 루프를 통과하지 못한 채 "완료"로 표기할 수 없다.**

### 3.1 루프 상태 모델

모든 대상 소스는 체크리스트 파일 `docs/Implementation_Instructions/_progress/closing_checklist.md`(첫 작업 시작 시 §3.6 템플릿으로 생성)에서 다음 5상태 중 하나를 가진다:

- `PENDING` — 미착수
- `IN_LOOP` — 루프 진행 중 (반복 횟수 함께 기록, 예: `IN_LOOP(2)`)
- `PASS` — 종결 기준 충족 + 증거(artifact 경로/테스트명) 기록 완료
- `BLOCKED_TERMINAL` — CAPTCHA/로그인/페이월/법적 차단 등 우회 불가 사유 확인 + 근거 문서화 (이것도 "닫힘"이다 — 단, 사유 없는 BLOCKED 표기는 금지)
- `DEFERRED(사유+조건)` — 외부 조건(예: quota 리셋 대기) 때문에 이번 턴 내 검증 물리적 불가. **반드시 재개 조건을 명시** (예: "newsapi quota 리셋 후 UTC 00:00 재실행")

**턴 종료 조건: 표 §1의 15개 항목 전부가 PASS / BLOCKED_TERMINAL / DEFERRED(조건부) 중 하나. PENDING이나 IN_LOOP가 하나라도 남아 있으면 턴을 종료하지 않는다.**

### 3.2 소스당 단일 반복(iteration)의 5단계

각 소스에 대해 아래 5단계를 1회 반복(iteration)으로 정의한다. 단계를 건너뛰는 것은 금지다.

**STEP A — 재현 (Reproduce)**: 현재 상태를 실측으로 확인한다. 직전 라운드의 실패가 그대로 재현되는지, 이미 외부 요인이 변해 해소되었는지부터 본다. 명령 예: `.\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source <id> --json`. 재현 결과(status, error_category, raw artifact 경로)를 체크리스트에 기록한다. **재현 없이 수정부터 시작하는 것을 금지한다** — 직전 라운드의 429는 일시적 IP 공유 문제였을 수도 있고, 그 경우 코드 수정은 과잉 대응이다.

**STEP B — 원인 분석 (Diagnose)**: raw artifact(`ingestion/outputs/raw_payload/<source_id>/` 또는 `rendered_dom/`)를 직접 읽고, 응답의 처음 500자·HTTP status·Content-Type을 확인한다. HTML이면 `<title>`과 에러 문구를 찾는다. Playwright 소스면 screenshot(`outputs/screenshots/`)을 확인한다. 가설을 **최소 2개** 세우고(예: "endpoint 폐기" vs "UA 차단"), 각 가설을 구분할 수 있는 최소 비용 실험을 설계한다. 가설과 실험 설계를 체크리스트에 한 줄씩 기록한다.

**STEP C — 수정 적용 (Fix)**: 담당 문서의 diff를 적용하거나, 진단 결과가 문서의 가정과 다르면 **문서의 '대안 경로' 섹션으로 분기**한다. 문서에 없는 제3의 원인이 확인되면 즉흥 수정하지 말고: ① 원인을 체크리스트에 기록 ② 최소 변경 원칙으로 수정 설계 ③ 적용. 수정은 atomic(소스 1개 단위)으로 하고 무관 파일을 건드리지 않는다.

**STEP D — 검증 테스트 (Verify)**: 두 겹으로 검증한다. ① **단위 테스트** — 수정이 테스트 가능한 로직이면 신규 테스트를 작성해 통과시키고, 전체 `pytest ingestion\tests -q`가 509+신규 전부 통과하는지 확인. ② **live 검증** — gate(`gate_check`) 통과 확인 후 단 1회 live 호출로 종결 기준 충족 여부를 확인. live 검증의 증거(artifact 경로, items_found, sample title 1건)를 체크리스트에 기록.

**STEP E — 결과 검토 (Review)**: 종결 기준 충족 → `PASS` 전환. 미충족 → 무엇이 부족한지 명시하고 반복 횟수 +1로 STEP B로 복귀. **단, 같은 가설로 같은 실험을 반복하는 것은 금지** — 매 반복은 새 가설 또는 새 정보에 기반해야 한다.

### 3.3 반복 한도와 탈출 규칙

- 소스당 최대 **4 iteration**. 4회 소진 시: live 증거를 첨부해 `BLOCKED_TERMINAL`(차단 확인) 또는 `DEFERRED(사유)`로 분류하고 docs/71 리스크 대장에 등재한다. 무한 루프 금지.
- 429/RATE_LIMITED를 만난 소스는 **cooldown 만료 전 재호출 금지** (gate_check가 cooldown_skip을 반환하는 동안 해당 소스의 루프를 일시정지하고 다른 소스를 진행 — 루프는 소스 간 인터리빙을 허용한다).
- 한 iteration 안에서 같은 소스 live 호출은 최대 2회 (진단 1 + 검증 1). google_trends 계열은 iteration당 1회.
- 인프라 코드(01) 수정이 다른 소스 루프 도중 필요해지면: 진행 중 소스 루프를 멈추고 인프라를 먼저 고친 뒤 **전체 pytest 통과를 확인하고** 소스 루프로 복귀한다.

### 3.4 증거 규율

"동작한다"는 주장에는 반드시 다음 3종 증거가 체크리스트에 있어야 한다: ① 실행한 명령 그대로 ② 핵심 출력(status/items_found/sample title 1건, 120자 절단) ③ artifact 또는 테스트 파일 경로. 증거 없는 PASS는 무효이며, 10번 문서의 최종 감사에서 IN_LOOP로 강등된다.

### 3.5 회귀 방지

매 소스 PASS 시점마다가 아니라, **문서(01~08) 단위 완료 시점마다** 전체 `pytest ingestion\tests -q` + `scan_secrets`를 실행한다. 실패 시 해당 문서 범위 내에서 원인을 닫은 후에만 다음 문서로 진행한다.

### 3.6 체크리스트 템플릿 (`_progress/closing_checklist.md` 생성용)

```markdown
# Closing Checklist — <시작일시 UTC>
| # | 항목 | 상태 | iter | 가설/원인 | 증거(명령/출력/경로) | 종결 시각 |
|---|------|------|------|----------|---------------------|----------|
| 1 | RISK-T04 Route1 429 | PENDING | 0 | | | |
| 2 | gdelt | PENDING | 0 | | | |
| 3 | ap_news | PENDING | 0 | | | |
| 4 | newsapi | PENDING | 0 | | | |
| 5 | google_trends_explore | PENDING | 0 | | | |
| 6a | loword selector | PENDING | 0 | | | |
| 6b | google_trending_now selector | PENDING | 0 | | | |
| 6c | dcinside selector+본문 | PENDING | 0 | | | |
| 6d | eu_press_corner selector | PENDING | 0 | | | |
| 7 | signal_bz 보강 | PENDING | 0 | | | |
| 8 | dcinside 검색 영구 path | PENDING | 0 | | | |
| 9 | federal_register fields | PENDING | 0 | | | |
| 10a | igdb 날짜/url | PENDING | 0 | | | |
| 10b | culture_info 날짜 | PENDING | 0 | | | |
| 11 | hacker_news detail | PENDING | 0 | | | |
| 12 | bok_ecos/eia/its 샘플 매핑 | PENDING | 0 | | | |
| 13 | 시장 numeric_signal 분류 | PENDING | 0 | | | |
| 14 | 장문 query 절단 | PENDING | 0 | | | |
| 15 | 의존성/기법 흡수 | PENDING | 0 | | | |
```

## 4. 공통 검증 명령 모음 (그대로 복사해 사용)

```powershell
# 전체 테스트 (기준선 509)
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q

# 단일 소스 live probe (한글 출력 안전)
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source <source_id> --json

# query 포함 probe
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_collection_probe --source <source_id> --query "<검색어>" --json

# secret scan (문서/출력물 작성 후 필수)
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths ingestion\outputs docs\ingestion docs\Implementation_Instructions plans

# 1차 audit runner 재실행 (특정 소스만)
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -m ingestion.runners.run_primary_seed_live_audit --sources <id1>,<id2>
```

## 5. 파일 맵 (이 라운드에서 수정/신설되는 전체)

| 구분 | 경로 | 담당 문서 |
|------|------|----------|
| 수정 | `ingestion/probes/api_probe.py` | 01, 02, 04, 08 |
| 수정 | `ingestion/runners/run_api_connectivity_check.py` (`_SERVICE_CONFIGS`) | 03, 04 |
| 수정 | `ingestion/configs/rate_limit_policy.yaml` | 02 |
| 수정 | `ingestion/configs/playwright_probe_sites.yaml` | 05, 07 |
| 수정 | `ingestion/runners/_audit_common.py` (`_SAMPLE_PATHS`, numeric signal) | 08 |
| 수정 | `ingestion/fetch_strategies/collection_probe.py` (start_url 템플릿) | 05 |
| 신설 | `ingestion/runners/run_structure_explorer.py` | 06 |
| 신설 | `ingestion/tools/check_dependency_readiness.py` | 09 |
| 신설 | `ingestion/fetch_strategies/article_body_extractor.py` (cascade) | 07, 09 |
| 신설 테스트 | `ingestion/tests/unit/test_route1_rate_limit_record.py` 외 문서별 명시 | 각 문서 |
| 신설 진행 기록 | `docs/Implementation_Instructions/_progress/closing_checklist.md` | 00 §3.6 |

## 6. 보고 형식 (턴 종료 시)

① 무엇을 했는가(문서별 1줄) ② 무엇을 검증했는가(체크리스트 최종 상태 표 + pytest 수치 + live 증거 수) ③ WARNING/BLOCKED/UNKNOWN/DEFERRED 목록(사유·재개 조건 포함). 마지막 문장은 "15개 항목 중 PASS n / BLOCKED_TERMINAL n / DEFERRED n" 형식의 정량 결론.
