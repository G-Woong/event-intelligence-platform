---
name: turn-closeout
description: 매 턴 종료 직전 실행하는 stamp-gated 마감 오케스트레이터. 훅이 모은 사실(.harness/machine_status.json)과 감사 flag(.harness/audit_required.json)를 읽어, 변경 유형별 subagents/code-review 스킬을 라우팅 호출하고, PROJECT_STATUS·_RISK·_DECISIONS를 갱신하고, dead-code 후보를 식별하고, 완료 증거를 .harness/closeout_stamp.json에 남긴다.
when_to_use: 매 턴 응답을 마치기 직전(코드/문서/설정 변경이 있던 모든 턴). "턴 마감 / closeout / 진행현황 갱신 / risk 감사 / 감사 라우팅" 류 요청.
user-invocable: true
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent, Skill
---

# turn-closeout (stamp-gated 마감 오케스트레이터)

매 턴 마감의 **총괄 오케스트레이터**다. 단순 작성자가 아니라 closeout orchestration owner.
역할 분담: **훅=센서/게이트, 이 스킬=오케스트레이터, subagents=다각도 감사단, stamp=완료 증거.**

## 핵심 불변식 (어기지 말 것)
- **파일 writer 단일화:** `PROJECT_STATUS.md`·`.harness/closeout_stamp.json`은 **이 스킬(에이전트)만** 쓴다. `.harness/machine_status.json`·`audit_required.json`은 **훅만** 쓴다(이 스킬은 읽기만).
- **삭제 금지:** `rm`/`Remove-Item` 금지. 정리는 `Move-Item`/`git mv`(되돌림 가능)만.
- **dry-run → audit → apply:** destructive action(docs 이동, code/dead-code 통폐합)은 반드시 ①후보 식별(dry-run) ②팀 감사 ③소규모 apply 순서. **이번 단계에서 즉시 삭제 금지.**
- **단일 출처:** docs 권위 정점 `docs/_CANONICAL/*`, risk 권위 `docs/_RISK/RISK_REGISTER.md`.
- **flag 강제:** `audit_required.json`/`machine_status.audit_types`에 flag가 있으면 대응 감사를 **반드시 호출**하고 stamp의 `subagents_completed`에 기록. 호출 없이 stamp를 쓰면 Stop hook이 mismatch로 다음 턴 재적발.

## procedure (오케스트레이션)
1. **사실/플래그 읽기:** `.harness/machine_status.json`(turn, sig, **audit_types**, risk, test_stale) + `.harness/audit_required.json`(flags) 읽기. **`machine_status.audit_types`가 권위**(Stop hook이 git 전체 재스캔 → Bash 변경분도 포함). `audit_required.json`은 PostToolUse 보조(Edit/Write만 잡아 Bash 변경 누락 가능) — 둘의 **합집합**을 routing 대상으로 삼되 audit_types를 우선. `git status/diff` 요약.
2. **변경 유형 분류 확인:** audit_types/flags가 실제 변경과 맞는지 git diff로 교차 확인(훅 분류 신뢰하되 누락 보완).
3. **[Req3] subagent 라우팅 (강제):** flags 합집합 → `03 §3` 표대로 **실제 에이전트/`/code-review` 스킬을 병렬 호출**. `adversarial-reality-critic`은 flag 1개라도 있으면 필수 포함. 같은 턴 중복은 stamp로 디바운스. **code 변경(code_review flag)이면 `/code-review` 스킬을 호출**(hook에서 무겁게 돌리지 않고 여기서).
4. **[Req4] risk 감사:** `docs/_RISK/RISK_REGISTER.md` 각 열린 risk Closure를 **grep 근거로** 검증. 충족분 → CLOSED 이관 후보. 감사 결과 REAL 이슈 → 신규 risk 등록. machine_status.risk 카운트와 일치 확인.
5. **[Req2a] docs lifecycle 감사:** `python scripts/docs_lifecycle_audit.py`(read-only/dry-run) 산출 `.harness/docs_lifecycle_audit.json` 검토 — 각 doc의 role/protected/move_allowed/후보 여부. 이동 후보는 **머신 마커 `<!-- LIFECYCLE: superseded|dead -->`** 가 붙은 비보호 doc만(키워드 추측 금지). protected(PROJECT_STATUS/RISK/README/canonical/contract/source-registry/*_FINAL)은 절대 후보 아님. 불변식은 `tests/test_docs_lifecycle.py`로 고정. 이동은 6단계 감사 통과분만.
6. **[dry-run→audit→apply] 비가역 이동:** 승인분만 `Move-Item`/`git mv`로 `_ARCHIVE_SUPERSEDED`(+`_INDEX` 1줄)/`_TRASH`. 반대 의견 있으면 ACTIVE 유지 + risk 등록.
7. **[dead code] 후보 갱신:** `python scripts/dead_code_scan.py` 산출 `.harness/dead_code_candidates.json` 검토 → `R-DeadCodeAudit` 갱신. **삭제는 안 함**(다음 phase, dry-run→audit→apply). ⚠ **candidate=0 은 "dead code 없음"이 아니라 "참조 휴리스틱 미탐(recall 한계)"** — 클린 판정으로 렌더하지 말 것(거짓 안심 금지).
8. **[Req2b] 의사결정 ADR:** 설계 판단/착지/방향전환/폐기가 있었으면 **월별 ledger** `docs/_DECISIONS/<YYYY-MM>.md`에 블록 1개 append. `02 B.2` 사용자 양식 정확히(날짜·섹터·상태/문제·배경·가설·도입 아이디어·선택 이유·구현·결과·한계·후속 과제·관련 문서), 간략. 사소한 턴엔 추가 안 함.
9. **[Req1] PROJECT_STATUS.md 덮어쓰기:** `01 §3` 템플릿, machine_status 사실 렌더 + 비개발자 톤 서술(목표·달성/미달성·왜·다음·닫을 수 없는 문제). 감사 결과 요약 포함. test_stale면 STALE 배지.
10. **[stamp] 완료 증거 기록:** 먼저 **`python scripts/closeout_sig.py` 를 실행**(9단계 PROJECT_STATUS/risk/_DECISIONS 편집을 모두 마친 *뒤*)하여 출력 `signature` 배열을 `working_tree_signature`에 **그대로 복사**한다. (sig가 이제 **content-hash 를 포함**하므로 stale machine_status.sig 복사는 게이트를 못 맞춘다 — 반드시 이 스크립트로 현재 트리에서 재계산. commit 전에 실행.) 그 다음 `.harness/closeout_stamp.json`에 아래 스키마로 기록. **required audit 별 구조화 evidence**(`audit_evidence`)를 채우고, 호출/완료한 subagents, 미해결 작업을 정직히 남긴다.
11. **[보고]** 아래 output format으로 한국어 요약.

## closeout_stamp.json 스키마 (이 스킬만 기록)
```json
{
  "schema_version": 2,
  "session_id": "<machine_status.session_id>",
  "git_head": "<machine_status.head>",
  "working_tree_signature": ["<scripts/closeout_sig.py 의 signature 배열 그대로>"],
  "audit_types_addressed": ["<machine_status.audit_types 중 이번 closeout에서 처리한 것 — 전부 커버해야 게이트 통과>"],
  "audit_evidence": [
    {
      "audit_type": "<machine_status.audit_types 의 각 항목>",
      "reviewer_or_skill": "<호출한 에이전트/스킬, 예: adversarial-reality-critic>",
      "executed": true,
      "verdict": "<한 줄 결론 — 비면 게이트 실패>",
      "findings_count": 0,
      "blocking_findings_count": 0,
      "addressed_findings_count": 0,
      "summary": "<핵심 지적 1~2줄 (영구 리포트 파일 만들지 말 것, 03 §4)>",
      "completed_at": "<turn # 또는 ISO 시각>"
    }
  ],
  "closeout_turn": "<machine_status.turn>",
  "closeout_skill_version": "1.3",
  "project_status_updated": true,
  "decisions_updated": false,
  "risk_registry_updated": false,
  "docs_sync_checked": true,
  "code_review_required": false,
  "code_review_completed": false,
  "subagents_required": ["..."],
  "subagents_completed": ["..."],
  "unresolved_required_actions": ["..."],
  "generated_outputs": ["PROJECT_STATUS.md", "..."]
}
```
> **게이트(Stop hook 강제):** 아래가 **모두** 참이어야 closeout_current=true(다음 턴 무알림):
> ① `machine_status.audit_types ⊆ audit_types_addressed` (커버리지), ② **required audit_type 마다 `audit_evidence`에 구조화 레코드 존재**(`executed=true` + 비어있지 않은 `verdict`; blocking>addressed 면 `unresolved_required_actions`에 반영) — 단순 type 나열·`code_review_completed=true` 자기보고만으로는 **불통과**, ③ `working_tree_signature == 현재 sig`(**content-hash 포함** → 동일 경로 내용변경도 mismatch로 잡힘, R2 차단), ④ `unresolved 비어있음`. **required 측(audit_types)은 훅이 객관 계산하므로 감사를 빠뜨리고 stamp에서 누락해도 게이트가 잡는다.** 처리 못 한 감사는 반드시 `unresolved_required_actions`에 남겨라(숨기지 말 것).
> **정직한 한계(완화됨, 완전 제거 불가):** evidence 게이트는 "각 required 유형에 대해 *구조화 증거를 기록*했는가"까지 검증한다(자기보고 한 줄보다 위조 비용 ↑). 그러나 LLM이 그 추론을 실제로 했는지는 어떤 훅도 검증 못 한다 — 의도적 거짓 evidence 기록은 여전히 통과 가능(transcript 사후검증이 최종 방어선) — `R-CloseoutTrust`로 등록.

## safety constraints
- `rm`/`Remove-Item`/`rmdir`/`git push`/`git reset --hard`/`git clean` 금지. 이동은 `Move-Item`/`git mv`.
- `.env` 값 출력 금지(존재/길이만). 비밀 파일을 `_TRASH`로 옮기지 말 것(guard 차단).
- dead code/통폐합 **즉시 삭제 금지** — 후보 식별 + 감사까지만.
- google_trends_explore PASS 오표기 금지. 추측 금지(모르면 UNKNOWN).

## success criteria
- closeout_stamp.working_tree_signature == `scripts/closeout_sig.py` 출력(content-hash 포함, Stop hook 게이트 통과 → 다음 턴 무알림).
- required audit_type 마다 `audit_evidence` 구조화 레코드(executed=true+verdict) 존재 — 자기보고만으로 통과 불가.
- audit_types/flags의 모든 항목이 subagents_completed 또는 unresolved_required_actions에 반영.
- 열린 risk 카운트 = machine_status.risk. PROJECT_STATUS 갱신. 비가역 이동은 감사 통과분만.

## output format (한국어 보고)
```
턴 마감(stamp-gated): turn #N
- 갱신: PROJECT_STATUS ✅ / _DECISIONS(추가 여부) / risk(신규 a·종결 b)
- 감사 flag: [..] → 호출: [에이전트/스킬..] / 결론: ..
- docs 이동: (이동 또는 "없음")  · dead-code 후보: n건(삭제 안 함)
- stamp: working_tree_signature 기록 ✅ / unresolved: [..]
- WARNING/BLOCKED/UNKNOWN
```
