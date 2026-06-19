# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 하는 중인가:** 하네스 재구축 전 **docs 대청소(생애주기 통폐합)** 를 실제로 실행하고, 그 과정에서 드러난 **`.env` 파서 계약 버그**(전체 테스트를 막던)를 코드 수정으로 해결했습니다.
- **이번 턴에 실제로 끝낸 것:** 134개 문서를 생애주기 구조로 재편(삭제 17·ARCHIVE 62·REFERENCE/ROADMAP 통합 32·신규 진입점 1). `.env`를 건드리지 않고 코드 파서를 고쳐 테스트 **1517 passed** 복구. 적대 리뷰 지적(JSON-array CORS·테스트 부재)까지 반영.
- **지금 막힌 것:** 없음. (이전에 PROJECT_STATUS가 안 갱신된 건 버그가 아니라 `/turn-closeout` 미실행 때문 — 아래 설명.)

## 📋 자동 수집 사실 (machine_status.json)
- repo: WEB_INTELLIGENCE · turn 9 · 직전 변경 code 1(config.py) — 이번 closeout 시점엔 docs/config/test 추가 변경
- audit_types: **architecture_review · code_review · test_review** (config.py code 변경)
- 열린 RISK: **17건**(HIGH 3 / MED 7 / LOW 7) · test_stale: False
- 비밀 스캔: PASS · git status: clean(커밋 4개로 분리)

## ✅ 이번 턴에 달성한 것
- **docs 생애주기 리팩토(commit 546d377):** `00_START_HERE` 단일 진입점 + `_CANONICAL`(현재)/`2_ROADMAP`/`3_ARCHIVE`(시간순)/`5_REFERENCE`/`Harness_Construction`. 루트 평면노출 plans 35·중복 stale 문서 10·dead/dup yaml 6 제거. **live 하네스 연동 폴더(_CANONICAL·*_FINAL·ingestion)는 의도적으로 제자리**(rename 시 하네스 파손 방지).
- **env 파서 계약 수정(commit 57a0049·f8512b3):** `.env.example` 의 "빈값=기본값"·CSV CORS 계약을 코드가 흡수(NoDecode + model_validator + JSON-array 허용 가드). `.env` 무수정. 회귀 테스트 8 신규.
- **적대 리뷰 반영:** SOUND_WITH_CAVEATS → JSON-array CORS fail-loud 가드 + 파서 직접 테스트 추가.

## ❌ 달성하지 못한 것 & 왜
- **07 spec의 `_CANONICAL→1_CURRENT` rename:** 의도적 미실행 — 41개 live 참조(skill/hook/agent/코드)가 걸려 하네스를 깸. `_CANONICAL`은 이미 깨끗한 코어라 통증 원인 아님. 생애주기 구조는 주변 정리+진입점으로 달성.
- **07 §10 D2~D6:** 미결정(ingestion/agents rename, docs_lifecycle_audit 처리 등) — 사용자 확정 대기.
- **blank-drop unix 관용구 한계:** "빈 env로 비-빈-기본값 필드 비활성화" 불가(현재 그런 필드 없음, 미래 주의).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- **PROJECT_STATUS 갱신 = `/turn-closeout` 전용(설계):** 훅은 사실(machine_status)만 쓰고 서술은 안 씀(writer 단일화). 직전 턴들이 closeout 없이 commit으로 끝나 PROJECT_STATUS가 stale했음 — 버그 아님, 이번에 closeout 실행으로 해소.
- **commit-first nudge 침묵(R-CloseoutTrust gap4):** 커밋 후 closeout 실행 시 machine_status가 1사이클 stale. soft 운영이라 수용.
- **고아 pipeline 5모듈 배선 시점:** UNKNOWN(유지+ROADMAP, 사용자 승인).

## ⚠️ 이번 턴 종결/갱신 RISK
- 신규/종결 0. R-StaleDocs(LOW)는 07 실행으로 실질 완화(루트 sprawl 제거)되었으나 잔여 stale 수치 정정은 미완 → 유지.

## 👉 다음 턴 진입 조건
- docs 구조 정리 완료 + 테스트 green → **기능 개발 진입 가능**.
- 07 §10 D2~D6 확정 시 추가 정리 진행.

## 📁 근거 (이번 턴 핵심)
- commits: `546d377`(docs refactor) · `57a0049`(env 파서) · `f8512b3`(CORS 가드+테스트) · 태그 `pre-refactor-2026-06-19`
- `docs/00_START_HERE.md`, `backend/app/core/config.py`, `backend/tests/test_config_env_contract.py`
- `docs/_DECISIONS/2026-06.md`(#11·#12), `docs/Harness_Construction/07_REPO_REFACTOR_AND_CONSOLIDATION_SPEC.md`
