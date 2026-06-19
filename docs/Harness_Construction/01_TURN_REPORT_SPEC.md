# 01 — 턴 진행 리포트 (Req 1)  · rev2

> 산출물: **`PROJECT_STATUS.md`** (레포 루트, git tracked, **매 턴 전체 덮어쓰기**, 누적 안 함)
> 독자: **비개발자/비연구자 포함 누구나** "지금 어디까지·무엇이 안 됐고·왜"를 즉시 이해.
> **rev2 변경(R1 race 해소):** PROJECT_STATUS.md 는 **에이전트만 쓴다.** 훅은 이 파일을 건드리지 않고 사실을 `.harness/machine_status.json` 에만 기록한다. 에이전트가 그 JSON 을 읽어 사람이 읽을 요약으로 렌더링한다. → 두 주체가 같은 파일을 동시에 쓰던 race 제거.

---

## 1. 왜 루트 단일 파일 + 덮어쓰기인가
- **루트:** 가장 눈에 띈다 = "주도권" 목표에 직결.
- **단일·덮어쓰기:** "파일 증식 절대 불가" 요구. 이력은 **git**(`git log -- PROJECT_STATUS.md`).
- **에이전트 전용 writer:** 사실(JSON)은 훅이 신뢰성 보장, 사람용 서술은 에이전트가 해석가능성 보장 → **계층 분리**(사용자 Q1 지시: "자동 기록 계층과 의미 기록 계층의 책임을 분리").

---

## 2. 두 계층 (사실 vs 의미)

| 계층 | 위치 | writer | 신뢰 보장 | 내용 |
|---|---|---|---|---|
| **사실(machine)** | `.harness/machine_status.json` | **Stop 훅**(결정론) | **매 턴 100%**(훅은 턴 완료 시 항상 1회 발화 — 공식 확인) | 변경 파일 분류·LOC, 테스트 캐시(+as_of_commit/STALE), risk 카운트, trigger flag, turn id, session id |
| **의미(narrative)** | `PROJECT_STATUS.md` | **메인 에이전트**(`turn-closeout`) | **best-effort**(에이전트 규율 + 훅 nudge) | 목표·달성/미달성·왜·다음 액션·닫을 수 없는 문제 |

> **보장 모델(사용자 Q1 채택):** 사실은 매 턴 자동·신뢰. 의미부는 best-effort. closeout 미실행 턴은 JSON 은 최신이되 PROJECT_STATUS 서술이 stale → 훅이 nudge, 다음 closeout 이 STALE 배지와 함께 갱신. **거짓 안심 방지를 위해 사실 블록에 항상 `as_of` 를 표기.**

---

## 3. 템플릿 (에이전트가 이 형식으로 덮어쓰기)

```markdown
# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` (turn #N · as_of <commit/시각>)

## 🟢 한눈에 (비개발자용 3줄)
- 지금 무엇을 하는 중인가: (한 문장, 전문용어 금지)
- 이번 턴에 실제로 끝낸 것: (한 문장)
- 지금 막힌 것: (한 문장, 없으면 "없음")

## 📋 자동 수집 사실 (machine_status.json 에서 렌더)
- 변경 파일: 코드 3 · 문서 2 · 설정 0   ·   추가/삭제 LOC: +120 / -8
- 테스트: 612 passed / 0 failed  (as_of <commit8>; ⚠ 현재 HEAD 와 다르면 STALE 표시)
- 비밀 스캔: PASS   ·   열린 RISK: 9 (HIGH 2·MED 4·LOW 3) 신규 1·종결 0
- 팀 감사 트리거: (코드 착지) → 호출 3종   ·   서술 갱신: ✅ (turn #N)

## ✅ 이번 턴에 달성한 것
- (요구 항목별, 비개발자 표현)

## ❌ 달성하지 못한 것 & 왜
- 항목 / 이유 / 왜 어려운가(직관적 비유)

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- (외부 rate limit·법무 미검토 등 + 왜 내가 못 닫나)

## ⚠️ 이번 턴 신규 RISK (요약, 상세 docs/_RISK)
- (없으면 "없음")

## 👉 다음에 할 일 (우선순위)
1. … 2. …

## 📁 근거 (핵심 변경 파일)
- path:line — 무엇을 왜
```

> **분량 가드:** 서술부 화면 1~2개. 길면 상세는 `docs/_RISK`·`docs/_DECISIONS` 로 보내고 링크만.

---

## 4. 비개발자 가독성 규칙 (스킬이 강제)
- 전문용어는 괄호로 1줄 풀이/비유(뉴스룸 비유, `system_overview/01` 톤).
- "왜 못했나"는 변명이 아니라 **원인 + 직관 비유**. 예: "외부 사이트가 분당 요청을 막아(번호표가 꽉 참) 새 데이터를 못 받음."
- §1 원칙(투자조언 금지): 가치판단 표현 배제.

---

## 5. freshness 판정 (R5/rev3 — sig 기반, mtime 금지, race-free)
- 훅은 mtime 으로 판정하지 **않는다**(자기 쓰기로 오염되던 문제).
- **파일 분리(R1 race 완전 해소):** 에이전트는 `.harness/machine_status.json` 을 쓰지 않는다. 대신 **에이전트 전용** `.harness/narrative_marker.json` 에 `{session_id, narrated_sig, narrative_turn_id}` 를 기록한다(closeout 마지막 단계, `05 §2-9`). 훅은 이 marker 를 **읽기만** 한다. → machine_status.json=훅 전용, narrative_marker.json=에이전트 전용, PROJECT_STATUS.md=에이전트 전용. **어느 파일도 writer 가 둘이 아니다.**
- **sig(change signature):** 훅이 매 턴 계산하는 "비-서술 미커밋 파일 경로 집합"(sorted). **서술 산출물**(`PROJECT_STATUS.md`, `docs/_DECISIONS/**`, `docs/_RISK/**`, `docs/_ARCHIVE_SUPERSEDED/**`)과 gitignored 는 제외. → closeout 자신의 출력·정적 dirty tree 는 sig 를 바꾸지 않는다.
- **판정:** `marker.session_id==현재 session` 이고 `marker.narrated_sig == 현재 sig` 이면 `narrative_fresh=true`. nudge 는 `현재 sig 가 비어있지 않고 not fresh` 일 때만 → **실제 새 작업이 있을 때만** 조르고, 정적 dirty tree 는 침묵(rev3, 적대 M2 해소). 내용-only 변경(경로 불변)은 못 잡는 한계.

---

## 6. 동작 흐름 (순서 명확화)
```
턴 진행 중:
  └─ (이상적) 에이전트가 종료 직전 turn-closeout 실행
       ├─ .harness/machine_status.json 읽기(직전 훅이 남긴 사실)
       ├─ PROJECT_STATUS.md 서술 덮어쓰기  ← 에이전트만 쓰는 파일
       └─ .harness/narrative_marker.json 갱신(narrative_turn_id) ← 에이전트만 쓰는 파일
턴 종료 시점:
  └─ Stop 훅(turn_state_snapshot.py)  ← PROJECT_STATUS.md 는 안 건드림
       ├─ git status/diff 분석 → machine_status.json 재기록(다음 턴용 사실)
       └─ narrative_fresh=false 면 additionalContext nudge (block 안 함, soft)
```
> 훅과 에이전트가 **서로 다른 파일**을 쓰므로 순서/race 무관.
