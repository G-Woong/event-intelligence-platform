# AGENT_WORKFLOW — Claude / Codex 운영 구조

## worktree 역할

| worktree | 브랜치 | 경로 | 역할 |
|---|---|---|---|
| claude | main | `C:\Users\computer\Desktop\business\claude` | PLAN / 통합 / 리뷰 / 최종 판단 / merge gate |
| codex | codex | `C:\Users\computer\Desktop\business\codex` | atomic task 구현 / 테스트 / 대안 코드 |

## 작업 흐름

1. Claude가 task spec(`plans/` 또는 `.codex/tasks/`)을 작성.
2. Codex는 codex 브랜치에서 atomic task 수행, diff/patch로 보고.
3. Codex는 origin에 직접 push/merge하지 않는다.
4. Claude가 diff 리뷰 → 수용 시 main으로 cherry-pick 또는 merge.
5. 같은 파일 동시 수정 금지.
6. `.env`, `.claude/`, `.codex/`, local config는 commit 금지.
7. commit 단위는 작게 유지 (atomic).

## Codex 파일 구조 (설계 참조용)

```
C:\Users\computer\Desktop\business\codex
├── AGENTS.md                # gitignore 대상 (로컬 운영 노트)
├── .codex/
│   ├── config.toml          # 로컬 실행 환경, gitignore
│   ├── tasks/               # 로컬 task spec, gitignore
│   ├── reports/             # 로컬 실행 보고, gitignore
│   └── local/               # 잡다한 로컬, gitignore
└── plans/                   # main과 동기화 (git 추적)
```

> `.codex/`, `AGENTS.md`는 필요 시 별도 생성. 본 문서는 설계 참조용.

## 브랜치 동기화 정책

- codex 브랜치는 main의 최신 commit을 주기적으로 rebase/merge.
- plans/, docs/, requirements/ 변경은 main → codex 방향으로만 흐른다.
- codex 브랜치의 app 코드 변경은 Claude가 리뷰 후 cherry-pick 또는 PR 방식으로 main에 통합.

## 금지 사항

- Codex가 `.claude/`, `.codex/`, `.env`를 commit하는 것 금지.
- Claude가 codex worktree 안의 파일을 직접 수정하는 것 금지 (리뷰용 읽기만 허용).
- 어느 쪽이든 `git push --force`, `git reset --hard` 단독 실행 금지.
