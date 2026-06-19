# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 하는 중인가:** (웹 인텔리전스 프로젝트) 다음 턴부터 실제 수집/큐/크롤러 개발에 들어갈 수 있도록, 턴 마감 하네스의 **운영 결함**(출력 깨짐·헛알림·미검증 경로·죽은코드 도구)을 점검·정리했습니다.
- **이번 턴에 실제로 끝낸 것:** Stop hook 한글 깨짐 해결(영문 ASCII 출력), commit 직후 헛알림 제거, code-review 자동 경로를 **실제로 한 번 돌려** 진짜 결함 1건(CRLF) 잡아 고침, 죽은코드 도구에 vulture를 붙여 미사용 함수/클래스까지 탐지. 팀 검토 4종 반영.
- **지금 막힌 것:** 없음(닫을 수 없는 한계는 아래 ⚠️에 정직히 명시).

## 📋 자동 수집 사실 (machine_status.json)
- repo: WEB_INTELLIGENCE_CONFIRMED (remote=event-intelligence-platform) · HEAD 정리 대상
- 변경: harness 훅·스크립트·테스트·문서 + ingestion 주석 1(의미 있는 개선, 유지)
- 열린 RISK: **17건** — R-CodeReviewLivePath 완전종결(→RISK_CLOSED), R-HookOutputEncoding 종결 기록
- 비밀 스캔: PASS · dead-code 후보: **221건(결정적)** = 132 ruff symbol + 84 vulture(정의레벨 81: func42/class32/method6/property1) + 5 module · 삭제 0
- 팀 감사: adversarial-reality-critic + orchestrator-architect + security-permission-guardian + docs-memory-curator + **/code-review 라이브** (5)

## ✅ 이번 턴에 달성한 것 (운영 risk 정리)
- **R1 Stop hook 인코딩(종결):** nudge를 ASCII-safe 영문으로(+`json.dumps` ensure_ascii=True), harness CLI 4종 stdout UTF-8 reconfigure(doctor의 em-dash crash 포함). stdout 순수 ASCII 디코드 검증. `tests/test_harness_hooks.py`.
- **R2 commit 직후 헛알림(제거):** nudge를 uncommitted(porcelain) non-narration 기준으로 전환(`should_nudge`). clean tree+HEAD-only advance=무알림, dirty=알림. 테스트 4종.
- **R3 code-review live path(종결):** ingestion 주석 변경 → `code_review` flag → **`/code-review` 스킬 라이브 실호출** → CRLF churn 1건 적발 → 수정 → stamp evidence 적재. end-to-end 1회 관찰.
- **R4 vulture(연동):** `uv pip install vulture==2.16`, dead_code_scan 연동. per-kind confidence(정의=60, var/import=90)로 **uncalled function/class** 탐지(ruff 못 잡던 고유 가치), alembic 제외. 221 결정적, 삭제 0.

## ❌ 달성하지 못한 것 & 왜
- **dead-code 통폐합:** 후보 식별만(삭제 금지 준수). production 정의 레벨 70건은 phase-3에서 framework entrypoint 개별 검토 후 소규모 batch.
- **docs lifecycle actual apply:** LIFECYCLE 마커 0개 → 후보 0 → apply 대상 없음(공집합). 첫 apply는 마커 부여 + `02 §A.4` 팀 감사 + confirm 필요.
- **settings.json tracked 전환:** template(settings.example.json)로 부트스트랩 해결. 직접 tracked 전환은 **user decision**(임의 전환 금지).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- **evidence 자기보고 한계:** 게이트는 구조화 evidence 기록을 요구하나 LLM 실제 수행은 미검증(transcript 사후검증이 최종 방어선). → R-CloseoutTrust.
- **commit-first nudge 침묵(R2 trade-off):** `/turn-closeout` 없이 commit-first 하면 미마감 audit이 nudge로 안 뜸(machine_status.closeout_current=False에만 흔적). 보완: closeout 스킬이 진입 시 machine_status 소비. → R-CloseoutTrust gap(4).
- **Claude Code feedback 디코드:** ASCII 출력으로 깨짐 불가하게 했으나, feedback 채널의 디코드 자체는 repo 코드로 증명 불가(합리적 방어까지).

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-CodeReviewLivePath → CLOSED:** /code-review 라이브 실호출·finding·fix·evidence 1회 관찰.
- **R-HookOutputEncoding → CLOSED(신규 기록):** ASCII-safe 출력 + reconfigure.
- **R-DeadCodeAudit(갱신, LOW):** vulture 설치·연동, 221 후보. 잔존: 통폐합 미수행.
- **R-DocsLifecycle(갱신):** 첫 apply 승인 조건(02 A.4 팀 감사+confirm) 명시.
- **R-CloseoutTrust(갱신):** commit-first nudge 침묵 residual 추가.

## 👉 다음 턴 개발 진입 조건
- **바로 기능 개발 가능:** ✅ 운영 결함(R1/R2/R3)이 닫혔고 하네스가 안정적. 다음 턴부터 source registry/ingestion/crawler/event queue 개발 진입 가능.
- **개발과 병행 가능한 잔여(차단 아님):** dead-code phase-3 통폐합, docs 첫 lifecycle apply, settings.json tracked 결정.

## 📁 근거 (이번 턴 핵심)
- `.claude/hooks/turn_state_snapshot.py`(should_nudge/_nudge_message ASCII), `scripts/{harness_doctor,dead_code_scan,docs_lifecycle_audit,closeout_sig}.py`(reconfigure), `scripts/dead_code_scan.py`(vulture)
- `tests/test_harness_hooks.py`(신규 11), `tests/test_docs_lifecycle.py`(19), `ingestion/core/source_registry.py`(주석)
- `docs/_RISK/RISK_REGISTER.md`·`RISK_CLOSED.md`·`docs/_DECISIONS/2026-06.md`
