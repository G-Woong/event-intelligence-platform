---
name: docs-sync-skill
description: Prevent documentation drift across TRACE_FINAL, README, checklists, docs/ingestion 70/86/92, and Environment_setup. Run targeted greps for status mis-labels and keep single-source-of-truth docs current after a feature lands.
when_to_use: After completing a feature, after status changes, or before session end. Invoke to detect and fix doc drift (mis-labeled statuses, stale PENDING, applied stubs re-read as active).
user-invocable: true
allowed-tools: Read, Grep, Glob, Write, Edit
---

# docs-sync-skill

TRACE_FINAL / README / checklist / docs/70·86·92 / Environment_setup 문서의 status drift를 방지한다.

## when_to_use
- 새 feature 구현 완료 후, status 변경 후, 세션 종료 전
- "문서 정리 / drift 점검 / trace 갱신" 류 요청

## procedure
1. **단일 출처 확인**:
   - 수집: `docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md`
   - 환경: `docs/Environment_setup/ENVIRONMENT_SETUP_FINAL.md`
2. **drift grep** (아래 patterns) 실행, 위반 라인 식별
3. **갱신**: 위반/누락 섹션을 Edit/Write로 교정
4. **단일 FINAL 유지**: 환경 설정은 `ENVIRONMENT_SETUP_FINAL.md` 하나가 canonical. obsolete trace/spec 문서를 되살리지 않음

## drift grep patterns
```powershell
# google_trends_explore를 PASS로 오표기 (단, "PASS 표기 금지" 맥락은 정상)
Select-String -Path docs -Recurse -Pattern 'google_trends_explore.*\bPASS\b' -Include *.md
# gdelt가 NOT_READY로 잔존
Select-String -Path docs -Recurse -Pattern 'gdelt.*NOT_READY' -Include *.md
# secret scan을 current status로 WARNING 오표기
Select-String -Path docs -Recurse -Pattern 'secret scan.*WARNING' -Include *.md
# PENDING/IN_LOOP가 current status로 남음
Select-String -Path docs -Recurse -Pattern '(?m)current.*\b(PENDING|IN_LOOP)\b' -Include *.md
```
> grep 결과는 맥락을 보고 판단한다. "PASS 표기 절대 금지" 같은 정책 문장은 위반이 아니다.

## failure conditions
- google_trends_explore가 실제 status로 PASS 표기됨 → 교정 필수
- gdelt가 NOT_READY로 잔존 → 교정 (실제 PASS)
- obsolete trace/spec 문서가 active 지시로 재서술됨 → 교정

## success criteria
- 핵심 패턴 오표기 0건 (정책 문장 제외)
- FINAL 문서가 단일 출처로 일관됨 (구현/환경 각 1개)
- 단일 출처 진입점 링크 유효

## safety constraints
- APPLIED 지시서를 active 지시로 재실행 금지
- obsolete trace/spec 문서를 canonical로 혼동 금지
- 문서 파일 무단 삭제 금지 (rm/Remove-Item 금지; 제거는 git rm + 사용자 확인)
- git push 금지 / .env 값 출력 금지

## output format
```
drift_found: [pattern: file:line, ...]
fixed: [...]
remaining_todo: [...]
single_source_ok: true|false
```
