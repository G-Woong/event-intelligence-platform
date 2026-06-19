# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 하는 중인가:** (웹 인텔리전스 프로젝트) 작성된 문서가 이후 어디로 흘러가야 하는지(계속/덮어쓰기/보관/휴지통)를 **글이 아니라 자동 테스트로 고정**하고, 턴 마감 하네스의 남은 위험을 다음 단계로 넘길 준비를 했습니다.
- **이번 턴에 실제로 끝낸 것:** docs lifecycle을 분류기+19개 테스트로 동결, code-review 자동 감지 경로를 라이브로 확인(실제 리뷰 호출은 미관찰), dead-code 후보 스캔을 결정적으로 안정화(137건), 설정 재현성을 템플릿으로 실질 해결. 팀 검토 4종이 찾은 결함(스캔 비결정성·오탐·보호 누락·R3 과장)을 모두 반영.
- **지금 막힌 것:** 없음. 단, 자기보고 한계·`/code-review` 실호출 미관찰·dead-code 통폐합 미수행은 아래에 정직히 남김.

## 📋 자동 수집 사실 (machine_status.json)
- repo 정체성: **WEB_INTELLIGENCE_CONFIRMED** (remote=event-intelligence-platform, ingestion/source_registry/orchestration/event-queue 존재)
- 변경: harness 훅·스킬·스크립트·테스트·문서 (애플리케이션 코드 변경 0). 감사 유형: adversarial / evidence / harness_runtime / risk_closure / security
- 열린 RISK: **18건** (HIGH 3 · MEDIUM 7 · LOW 8) — 신규 R-DocsLifecycle, R-CodeReviewLivePath
- 비밀 스캔: PASS · dead-code 후보: **137건(결정적)** = 132 symbol(HIGH) + 5 module(LOW, CLI runner) · 삭제 0
- docs lifecycle: 136 docs 분류, **33 protected**, 이동 후보 0(마커 0) · lifecycle 테스트 **19 passed**
- 팀 감사: orchestrator-architect + docs-memory-curator + test-validation-agent + adversarial-reality-critic (4종)

## ✅ 이번 턴에 달성한 것
- **docs lifecycle audit-as-test (핵심):** `scripts/docs_lifecycle_audit.py`(read-only/dry-run 분류기) + `tests/test_docs_lifecycle.py`(19 invariant). 작성된 문서의 흐름(active→superseded→archive→trash)과 보호 규칙을 테스트로 고정. 이동은 머신 마커 `<!-- LIFECYCLE: ... -->` 기반(키워드 추측 배제), `moves_applied=0`/`manifests_created=0`.
- **code-review live path 라이브 관찰:** ingestion harmless probe → `audit_flagger`가 `code_review` flag 생성 + 게이트 mismatch 확인 후 원복. (단 `/code-review` 스킬 **실호출·evidence 적재는 미관찰** — R-CodeReviewLivePath로 정직히 남김.)
- **dead-code 스캔 결정성 수정:** corpus가 `.harness`/`.claude` 미독 → run간 변동 제거(137 고정), `from a.b import c` 포착 → `downstream_contracts` 오탐 제거. production 59(ruff symbol, HIGH)·tests 73·module 5(runner, LOW).
- **settings 재현성 (b) template:** `.claude/settings.example.json`(tracked, 비밀 없음) + gitignore 예외 → fresh clone `Copy-Item` 1-step 복구. settings.json 자체는 gitignored 유지(사용자 지시).

## ❌ 달성하지 못한 것 & 왜
- **`/code-review` 실호출 검증:** 이번 턴 application 코드 변경 0이라 실제 리뷰 호출/evidence 적재는 미관찰. 배선·flag·게이트까지만 검증.
- **dead-code 통폐합:** 후보 식별만(삭제 금지 준수). vulture 미설치로 uncalled function/class는 여전히 미탐.
- **settings.json 자동 재현:** template 복사는 수동 1-step. 완전 자동화는 settings.json tracked 전환(=user decision)이 필요.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- **자기보고 한계:** evidence 게이트도 가짜로 채우면 통과(위조 비용만↑). transcript 사후검증이 최종 방어선. → R-CloseoutTrust.
- **lifecycle 테스트 범위:** 분류기 계약+디스크 불변식은 고정하나, 실제 `Move-Item`을 수행하는 turn-closeout 스킬의 이동 안전성은 미테스트. → R-DocsLifecycle.

## ⚠️ 이번 턴 신규/갱신 RISK
- **R-DocsLifecycle (신규, LOW):** docs 흐름을 audit-as-test로 고정. 잔존: 스킬 이동 경로 미테스트, 마커 운용 미관찰.
- **R-CodeReviewLivePath (신규, LOW):** flag/게이트 라이브 검증, `/code-review` 실호출 미관찰.
- **R-DeadCodeAudit (갱신, LOW):** 결정적 137(132 HIGH/5 LOW), 오탐 수정. 잔존: vulture·통폐합.
- **R-HarnessReproducibility (갱신, LOW):** template으로 부트스트랩 실질 해결. 잔존: 자동화·settings.json tracked 결정(user).

## 🧭 settings 재현성 결정 (user decision 잔여)
- 채택: **(b) template만 추적**(settings.example.json) — orchestrator 권고, 비밀 누출 0, settings.json 미전환.
- 사용자 결정 필요: **(c) settings.json 직접 tracked 전환** 여부(완전 자동 재현 ↔ 로컬 prefs/비밀 유입 표면 trade-off). 임의 전환은 사용자 지시상 금지 → 보류.

## 👉 다음에 할 일 (우선순위)
1. **dead-code phase-3 통폐합:** `uv pip install vulture` → 재스캔, production 59 symbol 후보부터 dry-run→팀 감사→소규모 commit(TYPE_CHECKING/조건부 import/재export 개별 검토).
2. **settings 정책 결정:** (c) settings.json tracked 전환할지 사용자 결정.
3. **docs 실제 archive/trash apply:** 마커 부여 + 팀 감사 후 첫 lifecycle 이동 1회 라이브.
4. **`/code-review` 실호출 관찰:** 실제 ingestion/backend 코드 턴에서 evidence 적재 확인(R-CodeReviewLivePath 종결).
5. source registry/ingestion pipeline risk audit · closeout 안정성 관찰.

## 📁 근거 (이번 턴 핵심)
- `scripts/docs_lifecycle_audit.py`·`tests/test_docs_lifecycle.py`(신규), `scripts/dead_code_scan.py`(결정성·오탐 수정)
- `.claude/settings.example.json`(신규)·`.gitignore`·`scripts/harness_doctor.py`·README(setup)
- `.claude/skills/turn-closeout/SKILL.md`(step 5 배선), `docs/_RISK/RISK_REGISTER.md`, `docs/_DECISIONS/2026-06.md`
