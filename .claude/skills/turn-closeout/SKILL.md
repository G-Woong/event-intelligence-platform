---
name: turn-closeout
description: 매 턴 종료 직전 실행하는 단일 마감 절차. 자동 수집된 사실(.harness/machine_status.json)을 읽어 PROJECT_STATUS 서술을 갱신하고, docs 코드기반 동기화 후보를 점검하고, risk를 감사하고, 의미형 트리거(결정 완료/risk 종결/archive)를 판정하고, 유의미 변경 시 팀 감사를 라우팅하고, 중요한 설계 판단을 _DECISIONS ADR로 남긴다.
when_to_use: 매 턴 응답을 마치기 직전(코드/문서/설정 변경이 있던 모든 턴). "턴 마감 / closeout / 진행현황 갱신 / risk 감사" 류 요청.
user-invocable: true
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent
---

# turn-closeout

매 턴 마감을 한 절차로 묶는 단일 진입점. 사실 계층(훅)과 의미 계층(이 스킬)의 책임을 분리한다 —
훅은 `.harness/machine_status.json`에 사실을 자동 기록하고, 이 스킬은 그 사실을 사람이 읽을 의미로 해석한다.

## 핵심 불변식 (어기지 말 것)
- **파일 writer 단일화(R1):** `PROJECT_STATUS.md`와 `.harness/narrative_marker.json`은 **이 스킬(에이전트)만** 쓴다. `.harness/machine_status.json`은 **훅만** 쓴다 — 이 스킬은 읽기만.
- **삭제 금지:** `rm`/`Remove-Item` 금지. 파일 정리는 `Move-Item`/`git mv`(되돌림 가능)만.
- **단일 출처(R4):** docs 권위 정점은 `docs/_CANONICAL/*`. risk 권위는 `docs/_RISK/RISK_REGISTER.md`.
- **비가역 이동은 감사 후에만:** docs/risk archive·trash 이동은 팀 감사(아래 5단계) 통과분만.

## procedure
1. **사실 읽기:** `.harness/machine_status.json` 읽기 (turn, changed buckets, code_files, audit_required, risk 카운트, test_stale, delta_incomplete).
2. **의미형 트리거 판정(훅 불가, 03 §2b):**
   - `docs/_DECISIONS/*.md`에 `상태: 진행중→완료` 전이 + 대응 코드 변경 동시 → "인사이트→코드 구현" 트리거.
   - `docs/_RISK/*`에서 risk severity→CLOSED 전이 + 코드 변경 → "risk 종결" 트리거.
   - docs/risk archive·trash 이동 의도 있음 → "archive 게이트" (이동 직전 항상 감사).
3. **[Req4] risk 감사:** `docs/_RISK/RISK_REGISTER.md`의 각 열린 risk Closure 조건을 **grep 근거로** 검증. 충족 후보(→CLOSED 이관 후보) 표시. 이번 턴 신규 risk(에러·dead code·감사 결과) 식별.
4. **[Req2a] docs 동기화 후보:** "이미 적용/미사용" 메모리 md를 grep 근거로 식별(`02 A.4`). 추측 금지, 근거 첨부. 이동은 5단계 감사 후.
5. **[Req3] 팀 감사 라우팅:** `machine_status.audit_required==true` 또는 2단계 의미형 트리거가 있으면 `03 §3` 표대로 에이전트를 **병렬 호출**(항상 `adversarial-reality-critic` 포함). 같은 턴 중복 발동은 디바운스. 결과 종합 → REAL 이슈는 risk 등록, archive/trash 후보 승인/기각.
6. **[확정 이동] 승인분만** `Move-Item`/`git mv`로 `docs/_ARCHIVE_SUPERSEDED/`(+`_INDEX.md` 1줄) 또는 `docs/_TRASH/`. 반대 의견 있으면 ACTIVE 유지 + risk 등록.
7. **[Req2b] 의사결정 ADR:** 이번 턴에 설계 판단/아이디어 착지/방향 전환/폐기가 있었으면 `docs/_DECISIONS/SESSION_<날짜>_<해시>.md`에 블록 1개 append. **`02 B.2`의 사용자 지정 양식 정확히 사용** — `날짜·섹터·상태 / 문제·배경·가설·도입 아이디어·선택 이유·구현·결과·한계·후속 과제·관련 문서`. "왜 > 무엇", 각 필드 1~2줄 간략, 구현체-비종속. 사소한 턴엔 추가 안 함.
8. **[Req1] PROJECT_STATUS.md 덮어쓰기:** `01 §3` 템플릿으로, machine_status 사실을 렌더 + 비개발자 톤 서술(목표·달성/미달성·왜·다음·닫을 수 없는 문제). `as_of`(turn/commit) 표기. test_stale 이면 "테스트 결과 STALE" 배지.
9. **freshness 신호:** `.harness/narrative_marker.json`에 `{"session_id": <machine_status.session_id>, "narrated_sig": <machine_status.sig 그대로 복사>, "narrative_turn_id": <machine_status.turn>}` 기록. `narrated_sig`는 machine_status의 `sig` 배열을 **그대로** 복사한다(= "이 비-서술 변경 집합까지 서술 반영함"). 이게 다음 턴 nudge 억제의 핵심. **machine_status.json은 절대 쓰지 말 것.**
10. **(필요 시) 테스트 캐시:** 코드 변경이 컸으면 `test-validation-skill`로 pytest 실행 후 `.harness/last_test_result.json`에 `{"as_of_commit": <HEAD>, "passed": n, "failed": m}` 기록.

## safety constraints
- `rm`/`Remove-Item`/`rmdir` 금지(이동은 `Move-Item`/`git mv`). `git push`/`git reset --hard`/`git clean` 금지.
- `.env` 값 출력·로그 금지(존재/길이만). 비밀이 든 파일을 `_TRASH`로 옮기지 말 것(guard가 차단).
- google_trends_explore를 PASS로 오표기 금지(CONFIRMED_EXTERNAL_RATE_LIMIT 유지).
- 추측을 사실처럼 적지 말 것. 모르면 UNKNOWN, 막히면 BLOCKED.

## success criteria
- PROJECT_STATUS.md가 이번 턴 사실+서술로 갱신됨, narrative_marker.narrative_turn_id == machine_status.turn.
- 열린 risk 카운트가 machine_status.risk와 일치.
- 비가역 이동은 전부 팀 감사 통과분.

## output format (한국어 보고)
```
턴 마감: turn #N
- 갱신: PROJECT_STATUS ✅ / _DECISIONS (추가 여부) / risk (신규 a·종결 b)
- 팀 감사: (트리거/호출 에이전트/결론) 또는 "트리거 없음"
- docs 이동: (이동 파일 또는 "없음")
- WARNING/BLOCKED/UNKNOWN
```
