# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 하는 중인가:** 턴 종료 비서를 단순 "알림" 수준에서 **"누가 무슨 검토를 했는지 증거로 남기는 관제 시스템(stamp-gated)"**으로 격상했습니다.
- **이번 턴에 실제로 끝낸 것:** 변경 유형별 자동 감사 플래그 + 완료 증거 도장(stamp) + 죽은코드 후보 스캐너 + 월별 결정 기록 전환을 구현하고, **팀 검토 3종으로 스스로를 감사해 발견된 핵심 결함(감사 누락이 그냥 통과되던 구멍)을 고쳤습니다.**
- **지금 막힌 것:** 없음(닫을 수 없는 문제는 아래 ⚠️에 정직히 명시).

## 📋 자동 수집 사실 (machine_status.json)
- 변경 파일(비-서술 sig): 8 · 감사 필요 유형(audit_types): adversarial / harness_runtime / security / risk_closure / evidence
- 열린 RISK: 15건 (HIGH 3 · MEDIUM 8 · LOW 4) — `docs/_RISK/RISK_REGISTER.md` (신규 R-CloseoutTrust)
- 비밀 스캔: PASS (131 files) · dead-code 후보: 0건(=미탐 가능, 클린 아님)
- 팀 감사: security-permission-guardian + orchestrator-architect + adversarial-reality-critic (3종 호출, 결함 수정 완료)

## ✅ 이번 턴에 달성한 것
- **stamp-gated hybrid(Option C) 전환:** PostToolUse `audit_flagger`(변경유형 flag) + Stop `turn_state_snapshot`(사실+audit_types+게이트) + `turn-closeout` 오케스트레이터 + `closeout_stamp.json`(완료 증거).
- **게이트 강화(팀 감사 핵심 결함 수정):** 훅이 계산한 **객관 audit_types가 stamp에 모두 addressed돼야** 통과 → "감사 건너뛰고 통과"하던 구멍을 닫음.
- **dead-code 파이프라인:** `scripts/dead_code_scan.py`(447 모듈 스캔, 삭제 X) → `R-DeadCodeAudit` 갱신.
- **docs 증식 방지:** `_DECISIONS`를 월별 ledger(`2026-06.md`)로 전환(연 최대 12파일 상한).
- **03 라우팅을 실제 15에이전트로 매핑**, README 구조도 갱신.

## ❌ 달성하지 못한 것 & 왜
- **완전 강제(block) 게이트:** Stop hook block은 `stop_hook_active` 가드 미문서라 보류(soft 유지). 미완 closeout은 "차단"이 아니라 "다음 턴 재알림"으로 노출 — 사용자 수용한 trade-off.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- **자기보고 한계:** 게이트는 "required 감사 유형을 다뤘다고 *기록*했는가"를 검증할 뿐, LLM이 실제로 그 추론을 했는지는 어떤 훅도 검증 불가. → `R-CloseoutTrust`로 등록(완화책 포함).
- **sig 내용변경 미감지:** 같은 경로의 내용만 바뀌면 게이트가 못 잡음(경로 집합 기반). → 같은 risk에 phase-2(content-hash) 등록.

## ⚠️ 이번 턴 신규/갱신 RISK
- **R-CloseoutTrust (MEDIUM, 신규):** closeout 게이트 자기보고 한계 + sig 내용변경 미감지. 완화: 객관 커버리지 검사·transcript 사후검증·재알림.
- **R-DeadCodeAudit (갱신):** 파이프라인 구축됐으나 참조 휴리스틱 recall 낮음(0 후보) + `vulture`/`pyflakes` 미설치 → phase-2 필요.

## 👉 다음에 할 일 (우선순위)
1. `vulture`(또는 동급) venv 추가 → dead-code 실탐 + closeout 배선(R-DeadCodeAudit 종결 경로).
2. closeout 게이트에 subagent 산출물 존재 증거 or sig content-hash 추가(R-CloseoutTrust 완화).
3. 실제 코드 변경 턴에서 `/code-review` 스킬 라이브 호출 관찰.

## 📁 근거 (이번 턴 핵심)
- `.claude/hooks/turn_state_snapshot.py`(게이트+audit_types), `.claude/hooks/audit_flagger.py`(신규 PostToolUse)
- `.claude/skills/turn-closeout/SKILL.md`(오케스트레이터), `scripts/dead_code_scan.py`(신규)
- `docs/Harness_Construction/03·05`, `docs/_RISK/RISK_REGISTER.md`, `docs/_DECISIONS/2026-06.md`
