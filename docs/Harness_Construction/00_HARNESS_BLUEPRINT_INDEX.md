# 00 — 턴 종료 하네스 설계도 (INDEX)  · rev2

> **rev2(2026-06-19):** 팀 에이전트 3종(security/adversarial/orchestrator) 다각도 검토 + Stop 훅 공식 사실확인으로 10개 risk(R1~R10) 식별 → 반영. 핵심 변경: ① 훅과 에이전트가 **다른 파일**을 쓰도록 분리(MACHINE→`.harness/machine_status.json`, PROJECT_STATUS=에이전트 전용; R1 race 해소), ② 트리거를 파일경로형(훅)/의미형(스킬)으로 분리(R2/B3), ③ RISK 본문 통째 이동·단일출처 유지(R3), ④ 단일출처를 `_CANONICAL/*` 로 통일·동사 분리(R4), ⑤ turn=session_id+카운터·freshness=narrative_turn_id(R5), ⑥ 강제=soft 확정(R6), ⑦ `_DECISIONS` 를 의사결정 지식자산으로 격상(사용자 Q1). 이 결정의 ADR 은 `docs/_DECISIONS` 첫 블록 참조.

> 작성: 2026-06-19 / 상태: **설계(구현 진행 중)**
> 목적: "매 턴 종료 시 자동으로 ① 진행상황 리포트 ② docs 메모리 동기화 ③ 팀 감사 라우팅 ④ risk 수집"을
> **누락 없이, 비용 통제하며, Windows/PowerShell/py 환경에서 실제로 동작하도록** 만드는 단일 설계 묶음.

---

## 0. 한 문장 요약

> 매 턴 끝에 **Stop 훅**(결정론적 사실 + 강제)이 돌고, 그 신호를 읽은 **단일 스킬 `turn-closeout`**(에이전트 서술 + 동기화 + 감사 라우팅)이 4개 산출물을 갱신한다.
> 훅은 "반드시 돈다"를 보장하고, 스킬은 "사람이 읽을 의미"를 만든다. 둘의 분리가 이 설계의 전부다.

---

## 1. 왜 3계층인가 (하네스 사실에 근거한 결정)

| 계층 | 무엇 | 왜 이 계층이어야 하나 |
|---|---|---|
| **A. Stop 훅** (`py` 스크립트) | 결정론적 사실 스냅샷(git diff·변경 파일 분류·테스트 캐시·trigger flag) + 강제(enforcement) | 훅만이 **에이전트 의지와 무관하게 매 턴 100% 실행**된다. 에이전트 규율(CLAUDE.md "항상 X 해라")은 확률적이라 누락 가능. |
| **B. 스킬 `turn-closeout`** | 에이전트가 서술 작성·docs 동기화·감사 라우팅 수행 | "왜 목표를 못 이뤘나" 같은 **의미적 판단**은 LLM(에이전트)만 가능. 순수 Python 훅으론 불가. |
| **C. 기존 에이전트 fleet** | 스킬이 조건부로 호출하는 다각도 감사단 | **훅은 서브에이전트를 띄울 수 없다.** Agent 호출은 메인 에이전트(=스킬 실행 주체)만 가능. |

**핵심 제약 2가지가 계층 분리를 강제한다:**
1. 훅 → 서브에이전트 호출 불가 ⇒ req 3은 반드시 스킬(에이전트) 주도, 훅은 트리거 신호만.
2. 훅(Python) → 의미적 서술 불가 ⇒ req 1/2/4의 "왜"는 에이전트가, "무엇이 바뀌었나(사실)"는 훅이.

---

## 2. 요구사항 → 산출물 → 담당 매핑

| Req | 산출물 (단일/위치) | 누가 쓰나 | 매 턴? | 상세 |
|---|---|---|---|---|
| **1. 턴 진행 리포트** | `PROJECT_STATUS.md` (루트, **덮어쓰기**, 비개발자용) | 사실=훅 / 서술=에이전트 | **항상** | `01` |
| **2a. docs 코드기반 동기화** | `docs/**` 메모리 파일 정리 + `_ARCHIVE_SUPERSEDED/` + `_TRASH/` | 에이전트(curator) + 훅(후보 탐지) | **항상(탐지)**, 이동은 변경 시 | `02` |
| **2b. 의사결정/사고 로그** | `docs/_DECISIONS/SESSION_<id>.md` (세션 격리, 결정 단위 append) | 에이전트 | 결정/아이디어 착지 시 | `02` |
| **3. 팀 다각도 감사** | 감사 결과는 1·2·4 산출물에 반영 (별도 영구파일 X) | 메인 에이전트가 fleet 호출 | **트리거 시에만** | `03` |
| **4. risk 수집** | `docs/_RISK/RISK_REGISTER.md`(열림) + `RISK_CLOSED.md`(흐름만) | 사실=훅(후보) / 판정=에이전트 | **항상(감사)** | `04` |

> 배선(settings.json·훅 스크립트·스킬)의 구체 명세 = `05`. 구조 리팩토링·마이그레이션 순서 = `06`.

---

## 3. 비용/단순성 트레이드오프 (CLAUDE.md "단순함 우선"과의 화해)

user 요구는 "전부 매 턴 동작"이지만, **매 턴 팀 감사 풀가동은 토큰 폭증 + 사소한 작업엔 과잉**이다. 그래서 **티어링**한다:

- **T0 (항상, 0 토큰):** Stop 훅이 사실 스냅샷·trigger flag·freshness를 `.harness/turn_state.json`에 기록. 비용 무시 가능.
- **T1 (항상, 저비용):** `turn-closeout` 스킬이 `PROJECT_STATUS.md` 서술 갱신 + risk 감사 + docs 후보 점검. 메인 에이전트가 직접 수행(서브 호출 없음).
- **T2 (트리거 시에만, 고비용):** 코드 착지/리팩토링/risk 종결 등 "유의미 변경" 감지 시에만 팀 감사(req 3) 발동. 트리거 정의는 `03 §2`.

> **이 티어링이 "매 턴 동작"(T0/T1 항상)과 "사소한 작업은 판단"(T2 조건부)을 동시에 만족한다.**

---

## 4. 강제(enforcement) 방식 — soft 확정 (rev2)

매 턴 스킬 실행을 어떻게 보장하나? Stop 훅 `decision:"block"`으로 강제 가능하나:
- **공식 확인 결과**, payload 에 `stop_hook_active` 필드가 **문서화돼 있지 않고**, `block + additionalContext` 동시 출력의 병합 규칙도 **미정의**다. 즉 strict 루프가드의 안전성을 보증할 수 없다.
- 사용자 Q1 채택: **"사실은 매 턴 자동·신뢰, 의미부는 best-effort"**.

따라서 **soft 확정**:
- 훅은 `narrative_fresh=false`(변경 있는데 서술 미갱신) 시 `additionalContext`로 환기. **block 안 함, block+context 동시 출력 안 함.**
- 사실(`.harness/machine_status.json`)은 훅이 매 턴 100% 기록(신뢰). 사람용 서술은 closeout 이 best-effort.
- `enforce:"block"` 은 **미문서 가드 의존이라 현재 미지원**(실증 전 금지). 향후 공식 스펙 확인 시 재검토.

---

## 5. 파일 인벤토리 (이 설계도가 만들/바꿀 것)

**런타임 산출물(구현 후 생성):**
- `PROJECT_STATUS.md` (루트, tracked, 덮어쓰기, **에이전트만 쓰는 파일** — R1)
- `.harness/machine_status.json` (gitignored, **훅만 쓰는 사실 파일** — R1 race 해소)
- `.harness/last_test_result.json` (gitignored, test-validation-skill 이 갱신, `as_of_commit` 포함 — R8)
- `.harness/config.json` (tracked, 토글, `enforce:soft`)
- `docs/_DECISIONS/SESSION_<id>.md` (세션별, **의사결정 지식자산** — Q1 격상)
- `docs/_RISK/RISK_REGISTER.md`(열림/부분종결), `docs/_RISK/RISK_CLOSED.md`(완전종결)
- `docs/_ARCHIVE_SUPERSEDED/_INDEX.md` (tombstone 인덱스), `docs/_TRASH/` (gitignored)

**하네스 부품(구현 시 작성):**
- 훅: `.claude/hooks/turn_state_snapshot.py` (Stop)
- 스킬: `.claude/skills/turn-closeout/SKILL.md`
- `settings.json` Stop 훅 배열에 1줄 추가, `.gitignore`에 2줄 추가

**설계도(이번 턴 산출):** 이 폴더 `docs/Harness_Construction/00~06` + 루트 `README.md`.

---

## 6. 읽는 순서

- **의사결정자:** `00`(이 파일) → `01` → `03`
- **구현자(다음 턴):** `00` → `05`(배선) → `06`(마이그레이션) → `01·02·04`(산출물 명세)
