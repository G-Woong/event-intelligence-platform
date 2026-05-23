# STEP 002.7 — Worktree Isolation Audit Report

**감사 일시**: 2026-05-23  
**판정**: ✅ PASS — 두 worktree는 정상적으로 격리되어 있음

---

## 1. git worktree list --porcelain 원본 출력

```
worktree C:/Users/computer/Desktop/business/claude
HEAD 9dd85f07d9af4062d3e5fea43ac9336534771948
branch refs/heads/main

worktree C:/Users/computer/Desktop/business/codex
HEAD e21ee3d9489290b41fcd07761d369d3743e24aeb
branch refs/heads/codex
```

- 두 worktree가 **별도 entry**로 등록되어 있음
- HEAD 커밋이 서로 다름 (main ≠ codex)

---

## 2. rev-parse --show-toplevel

| worktree | 실제 top-level 경로 |
|---|---|
| claude | `C:/Users/computer/Desktop/business/claude` |
| codex  | `C:/Users/computer/Desktop/business/codex`  |

→ 경로가 서로 다름. **격리 정상.**

---

## 3. 현재 브랜치

| worktree | branch |
|---|---|
| claude | `main`  |
| codex  | `codex` |

---

## 4. symlink / junction 여부 (Windows)

| 경로 | LinkType | Target |
|---|---|---|
| `C:\Users\computer\Desktop\business\claude` | `` (빈 값) | `` (빈 값) |
| `C:\Users\computer\Desktop\business\codex`  | `` (빈 값) | `` (빈 값) |

→ SymbolicLink, Junction 모두 아님. **일반 디렉토리로 확인.**

---

## 5. 격리 테스트 결과 (Test-Path 4건)

| 테스트 항목 | 결과 | 판정 |
|---|---|---|
| `claude/__CLAUDE_ONLY_TEST.txt` 실재 확인 | `True`  | 파일 생성 성공 |
| `codex/__CODEX_ONLY_TEST.txt` 실재 확인  | `True`  | 파일 생성 성공 |
| `codex/__CLAUDE_ONLY_TEST.txt` 에 claude 파일이 보이는가 | `False` | ✅ 격리 정상 |
| `claude/__CODEX_ONLY_TEST.txt` 에 codex 파일이 보이는가  | `False` | ✅ 격리 정상 |

---

## 6. 원인 분류 (격리 실패 후보 매칭)

본 감사에서 격리 실패는 발생하지 않았으나, 사용자가 관찰했던 현상의 가능한 설명:

| 후보 원인 | 본 감사 결과 |
|---|---|
| symlink / junction | ❌ 해당 없음 (LinkType 빈 값) |
| top-level 경로 동일 | ❌ 해당 없음 (경로 상이) |
| 같은 브랜치 (commit 공유) | ❌ 해당 없음 (main ≠ codex) |
| editor 표시 오류 | 가능성 있음 — IDE가 git worktree를 인식 못하고 claude 경로를 두 탭에 표시한 경우 |
| `.claude/` 전역 설정 공유 | `.claude/` 설정 파일은 Claude Code 동작에만 영향, 파일시스템 격리와 무관 |
| main→codex merge를 실시간 반영으로 오해 | 가능성 있음 — `codex` 브랜치는 `main`에서 파생됐으므로 공통 커밋 이력 보유 |

**결론**: 파일시스템·git 수준에서 격리는 정상. 사용자가 관찰한 현상은 editor 표시 문제 또는 브랜치 공통 이력 오해일 가능성이 높음.

---

## 7. 임시 테스트 파일 처리

다음 두 파일은 이번 감사용 임시 파일로, **commit 대상이 아닙니다**:

- `C:\Users\computer\Desktop\business\claude\__CLAUDE_ONLY_TEST.txt`
- `C:\Users\computer\Desktop\business\codex\__CODEX_ONLY_TEST.txt`

**처리 방식을 사용자에게 문의합니다.** (CLAUDE.md destructive 금지 정책에 따라 자동 삭제 불가)
삭제를 원하시면 직접 또는 명시적 지시를 주시면 처리합니다.

---

## 8. 체크리스트

- [x] `git worktree list --porcelain` 에 두 worktree가 다른 branch로 명시
- [x] claude/codex `rev-parse --show-toplevel` 결과가 서로 다른 경로
- [x] `Get-Item ... LinkType` 두 곳 모두 빈 값 (symlink/junction 아님)
- [x] `Test-Path` 4건 결과 기록
- [x] **PASS** 판정 명시

---

## 9. STEP 003 진입 조건

**격리 감사 PASS** — STEP 003 (앱 scaffold) 재개 가능.  
사용자의 명시적 승인 후 진행.
