# repo-sunny-barto — 실시간 사건/이벤트 인텔리전스

> 전세계 실시간 사건/이벤트를 다양한 소스에서 **수집·정규화·랭킹**하여 신뢰 가능한 "사건 카드"로 제공하는 웹앱.
> **정보 제공이 목적** — 투자 권유·매수/매도 추천·금융 조언을 출력하지 않습니다.

---

## 한눈에 (비개발자용)

자동화된 글로벌 뉴스룸입니다. **기자(소스 수집) → 편집부(중복 제거) → AI 분석팀(LangGraph) → 독자(웹 화면)** 순으로
뉴스·공시·이벤트가 흘러가며 사람이 빠르게 읽는 카드로 가공됩니다. 상세 비유: `docs/system_overview/01_BIG_PICTURE_FOR_NON_DEVELOPERS.md`.

> **지금 진행 상황은 루트의 [`PROJECT_STATUS.md`](./PROJECT_STATUS.md)** 한 파일에 매 턴 갱신됩니다(가장 최근 1턴만 표시).

---

## 데이터 흐름

```
[소스]            [수집 엔진]         [브리지]          [다운스트림 앱]                 [독자]
RSS/API/HTML  →  ingestion/     →  raw_events(PG)  →  Redis stream → worker →      →  Next.js
공시/커뮤니티     57 소스 수집        BackendApiRaw      agent-worker → LangGraph        프론트 + Admin
                  정규화·랭킹        EventsWriter        (6노드: 분류·팩트체크·요약)
```

---

## 저장소 구조

```
repo-sunny-barto/
├── README.md                    # (이 파일) 구조도 + 진입점
├── PROJECT_STATUS.md            # 📊 매 턴 자동 갱신되는 진행 현황 (덮어쓰기, 비개발자용)
├── CLAUDE.md                    # 에이전트 운영 원칙(오케스트레이션/보안/금지 명령)
├── docker-compose.dev.yml       # 공유 인프라(Milvus·Redis·PG·app)
├── pyproject.toml / requirements* # uv 기반 Python 3.11 의존성
│
├── ingestion/                   # ① 소스 수집 엔진 (57 소스, Phase A~G-4 구현 완료)
│   ├── collectors/              #    API/RSS/HTML/Playwright 러너
│   ├── integration/             #    BackendApiRawEventsWriter (수집→raw_events 배선)
│   ├── outputs/ (gitignored)    #    수집 산출물(JSONL/리포트/본문)
│   └── tools/                   #    scan_secrets 등
│
├── backend/                     # ② FastAPI — /api/events, Admin API, raw_events 적재
├── workers/                     # ② Celery/worker — raw_events → 큐 → 처리
├── agents/                      # ② LangGraph 추론 그래프
│   └── nodes/baselines.py       #    결정론적 입력파생 baseline(mock 상수 제거)
├── frontend/                    # ② Next.js — 사건 카드 UI + Admin 대시보드
├── tests/                       # pytest 스위트
├── scripts/                     # 운영/검증 스크립트
│
├── plans/                       # 단계별 PLAN/REPORT (000~012)
│
├── docs/                        # 📚 메모리·설계 문서
│   ├── _CANONICAL/              #    단일 출처 index (신규 세션 최우선)
│   ├── _RISK/                   #    ⚠️ RISK 등록부 (열림/닫힘) — 별도 폴더 [신규]
│   ├── _DECISIONS/              #    세션별 의사결정/사고 로그 (ADR) [신규]
│   ├── _ARCHIVE_SUPERSEDED/     #    적용 완료/미사용 메모리 보관(되돌림 가능) + _INDEX
│   ├── _TRASH/ (gitignored)     #    보존기간 경과분 (복구 가능)
│   ├── Harness_Construction/    #    🛠️ 턴 종료 하네스 설계도 (00~06) [신규]
│   ├── system_overview/         #    비개발자용 전체 그림
│   ├── ingestion/ Orchestration_Construction/ Environment_setup/ …
│   └── (ARCHITECTURE·TRD·API_CONTRACT·EVENT_SCHEMA 등 스펙)
│
└── .claude/                     # 🤖 하네스 (오케스트레이션 구성)
    ├── settings.json            #    모델·권한(allow/deny)·훅 배선
    ├── agents/ (15종)           #    감사·구현 서브에이전트
    ├── skills/ (6종)            #    docs-sync / test-validation / turn-closeout(오케스트레이터) …
    └── hooks/                   #    PreToolUse(금지명령 차단) · PostToolUse(audit_flagger) · Stop(secret/docs/turn_state)
```

---

## 턴 종료 하네스 (stamp-gated, agent-orchestrated)

역할 분리: **hook=센서/게이트 · main agent=오케스트레이터 · skills=절차 · subagents=감사단 · stamp=완료 증거.**

```
PostToolUse(audit_flagger) → .harness/audit_required.json (변경유형 flag)
Stop(turn_state_snapshot)  → .harness/machine_status.json (사실 + audit_types + sig)
main agent (turn-closeout) → flag별 subagents/`/code-review` 라우팅 → PROJECT_STATUS/_RISK/_DECISIONS 갱신
                           → .harness/closeout_stamp.json (완료 증거)
Stop 게이트: stamp.working_tree_signature ≠ 현재 sig 면 "closeout 미완" 1회 알림 (stop_hook_active 가드)
```

| # | 기능 | 산출물 | 담당 |
|---|---|---|---|
| 1 | 진행 현황 리포트(비개발자용) | `PROJECT_STATUS.md` (덮어쓰기) | 사실=훅 / 서술=에이전트 |
| 2 | docs 코드기반 동기화 + 의사결정 ledger | `_ARCHIVE_SUPERSEDED/`·`_TRASH/`·`_DECISIONS/<YYYY-MM>.md`(월별) | 에이전트(curator) + 훅 |
| 3 | 변경유형별 팀 다각도 감사(flag→라우팅) | `closeout_stamp.subagents_*` + 1·2·4 반영 | 훅(flag) → 메인 에이전트(호출) |
| 4 | RISK 수집·종결 + dead-code 후보 | `docs/_RISK/` · `scripts/dead_code_scan.py`→`.harness/dead_code_candidates.json` | 사실=훅 / 판정=에이전트 |

> 원칙: 진짜 삭제(`rm`) 없이 `Move-Item`/`git mv` 되돌림 가능 lifecycle, destructive는 **dry-run→audit→apply**. 팀 감사엔 항상 `adversarial-reality-critic`(긍정편향 차단). 모든 Stop 훅은 `stop_hook_active` 가드(무한루프 방지). 설계도: `docs/Harness_Construction/`.

### ⚙️ 하네스 setup / 재현성 (신규 clone·머신·worktree 필수)

> **`.claude/settings.json` 은 gitignored** 입니다(`.gitignore` 가 `.claude/*` 를 제외하고 `agents/`·`skills/`·`hooks/` 만 다시 포함). 따라서 clone 하면 훅 *스크립트*는 받지만 **훅을 등록하는 `settings.json` 은 없어** 하네스가 **조용히 비활성**(Stop 스냅샷·PostToolUse 감사 flag·금지명령 가드 모두 미동작)이 됩니다.

- **신규 clone/머신/worktree 1-step 복구:** `.claude/settings.example.json`(tracked, **비밀 없음**)을 `.claude/settings.json` 으로 복사 → 훅 5개가 재등록됩니다. (PowerShell: `Copy-Item .claude/settings.example.json .claude/settings.json`). 로컬 전용 오버라이드는 `.claude/settings.local.json`(gitignored) 에.
- **등록해야 하는 훅(5):** PreToolUse `forbidden_command_guard.py` · PostToolUse `audit_flagger.py` · Stop `secret_scan_reminder.py`·`docs_conflict_grep_check.py`·`turn_state_snapshot.py`. 정확한 배선은 `settings.example.json` 또는 `docs/Harness_Construction/05_HOOKS_AND_SKILLS_WIRING.md §3`.
- **등록 확인 명령:** `python scripts/harness_doctor.py` → 누락 시 `FAIL` + 구체 remediation 출력(exit 1).
- **누락 증상:** PROJECT_STATUS 미갱신·`closeout_stamp.json` 미생성·턴 마감 알림 없음·`rm` 가드 미작동.
- **content-hash 게이트:** closeout 시 `python scripts/closeout_sig.py` 출력을 stamp `working_tree_signature` 에 복사(내용변경 감지).

---

## 진입점

- **진행 상황 즉시 확인:** [`PROJECT_STATUS.md`](./PROJECT_STATUS.md)
- **신규 세션 컨텍스트:** `docs/_CANONICAL/00_DOCS_INDEX.md`
- **위험 목록:** `docs/_RISK/RISK_REGISTER.md`
- **운영 원칙:** `CLAUDE.md`

## 환경

- OS: Windows 11 / PowerShell 5.1 · Python 3.11(`py -3.11`) · 패키지 매니저 **uv**(conda 금지)
- 런타임 격리: Docker Desktop(compose v2), 공유 인프라 `docker-compose.dev.yml`
- 키는 `.env`에서만 로드(`os.getenv`/pydantic-settings), 값 출력·하드코딩 금지
