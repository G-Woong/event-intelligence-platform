# 10 — DOCS REFACTOR RESULT MANIFEST (생애주기 재편 결과)

> **목적:** 2026-06-19 구조 리팩토링(`3_ARCHIVE/2026-06_harness_design/07` 실행 + 후속 검증 마감)의 **최종 결과 지도**. "원본 134 .md가 어디로 갔는가 / 무엇이 단일출처인가"를 한 곳에서 추적한다. 현재 docs 진입점은 **`docs/00_START_HERE.md`**.
> (구 버전 = 2026-06-16 "50-doc 배너라운드 전수처리 증명문". 그 증명은 역할을 다했고 본 문서가 결과 manifest로 대체. 원본 인벤토리는 `3_ARCHIVE/_DOCS_MD_INVENTORY_BEFORE.txt`에 보존.)

---

## 1. 최종 구조 (생애주기 정렬축)

| 경로 | 성격 | 단일출처 역할 |
|---|---|---|
| `00_START_HERE.md` | 진입점 | "지금 무엇이 사실 / 어디를 읽나" |
| `_CANONICAL/` (00~12) | **현재 사실** 코어 | 구현된 시스템의 단일 진실 (live 하네스가 직접 참조) |
| `_RISK/`, `_DECISIONS/` | governance | risk register / ADR 결정 로그 |
| `2_ROADMAP/` (02~18) | **미래 계획** | 미구현 레이어·상업화·업그레이드 경로 |
| `3_ARCHIVE/` | **과거 기록** | 빌드 히스토리·설계 원문·ideation 스냅샷 (시간순) |
| `5_REFERENCE/` | 상태중립 참조 | 스키마·런북·정책·**ENV_KEYS**·용어·파일맵 |
| `Harness_Construction/` (00~05) | 레포 운영도구 설계 | live turn-closeout 하네스 청사진 (실행 스펙 06·07 → `3_ARCHIVE/2026-06_harness_design/`) |
| `_ARCHIVE_SUPERSEDED/`, `_TRASH/` | live 하네스 타깃 | turn-closeout 아카이브 흐름 (제자리 유지) |
| `ingestion/`·`Environment_setup/`·`Implementation_Instructions/` | 제자리 유지 | 9 agents+4 skills 연동 *_FINAL (canonical이 수치 supersede) |

## 2. 의도적 편차 (스펙 §2 대비 — 정당, live 하네스 보호)

- `_CANONICAL/`→`1_CURRENT/`, `_RISK/_DECISIONS`→`governance/`, `Harness_Construction/`→`4_HARNESS/` **rename 미수행**: skill/hook/agent 41파일과 코드가 직접 참조 → rename 시 live 턴-마감 하네스 파손. 코어는 이미 깨끗하므로 sprawl 제거만으로 목적 달성.
- `*_FINAL`·`docs/ingestion/*` 제자리 유지: 9 agents+4 skills 연동. 대신 canonical(03·09)이 권위 수치, *_FINAL은 SUPERSEDED 배너로 시점 기록 보존.
- `_ARCHIVE_SUPERSEDED/`·`_TRASH/`는 3_ARCHIVE로 흡수하지 않음: turn-closeout 아카이브 타깃(live).
- plans slug 3개: DEL 아닌 ARCHIVE (실제 history).

## 3. 원본 클러스터 → 결과 (전수 추적)

| 원본 묶음 | 수 | 결과 |
|---|---:|---|
| docs/ 루트 reference (API_CONTRACT·EVENT_SCHEMA·COMPLIANCE·DATA_POLICY·DEPLOYMENT·OBSERVABILITY·PROMPT·RAG·SEARCH·FRONTEND·COMPATIBILITY·LLM_AGENT) | 12 | `git mv`→`5_REFERENCE/` |
| docs/ 루트 순수중복 (AGENT_WORKFLOW·ARCHITECTURE·COLLECTOR_DESIGN·DOCS_FINAL·SKELETON·TRD) | 6 | **DEL**(history 보존) — 01/02/04/09에 흡수 |
| system_overview reference (02·04·06·07·08·12) | 6 | `5_REFERENCE/` |
| system_overview 삭제 (00·03·09·10) | 4 | **DEL** — 01/09 흡수, false-TODO 제거 |
| system_overview legacy (01·05·11) | 3 | `3_ARCHIVE/2026-06_system_overview_legacy/` |
| Orchestration_Construction 설계원문 (01·02·03·04·05·07·08·09·10·12·README) | 11 | `3_ARCHIVE/2026-06_orchestration_design/` |
| Orchestration_Construction 유지 (00·06·11) | 3 | **이관(2026-06-19 후속)**: 06→`2_ROADMAP/16`, 11→`_CANONICAL/11`, 00→`_CANONICAL/12`(stale 헤더 정정) |
| _IDEATION 로드맵 (02·04~15·18) | 14 | `2_ROADMAP/` (레이어순) |
| _IDEATION 스냅샷 (00·01·03·16·17) | 5 | `3_ARCHIVE/2026-06_ideation_snapshots/` |
| 루트 plans/ 000~012 + slug 3 | 33 | `3_ARCHIVE/2026-05_build_phases/` |
| ingestion/plans/ 00~07 | 8 | `3_ARCHIVE/2026-06_ingestion_design/` |
| _CANONICAL 00~10 | 11 | 제자리 (00→START_HERE 재작성, 10→본 manifest) |

## 4. 단일출처 통합 (중복 제거)

| 클러스터 | 단일출처 | 처리 |
|---|---|---|
| env-key (★구 4벌) | `5_REFERENCE/ENV_KEYS.md` + 루트 `.env.example` | **2026-06-19 신설.** 08 카탈로그 포인터화(`CORS_ORIGINS` stale 정정), COMPATIBILITY/DEPLOYMENT 포인터 |
| commercialization (★구 3벌) | `2_ROADMAP/13` | Orch/10 archive, 18은 포인터 |
| 테스트/소스 수치 | `_CANONICAL/09`(1293) · `_CANONICAL/03`(46/57) | *_FINAL(509/648/635) SUPERSEDED 배너 |
| architecture / implemented-flow | `_CANONICAL/02` / `01` | 설계원문 archive |

## 5. 코드·설정 정리

- dead yaml 6개(extraction/llm/playwright_policy + phase1/2/3_sources) **DEL**(로더 0). 잔존 7 yaml은 LIVE.
- `ingestion/plans/__init__.py` DEL.
- `.harness/narrative_marker.json` = DEAD(closeout_stamp.json이 대체, hook read/write 0). Harness 01/05 SUPERSEDED 배너 부착 완료.

## 6. 잔여(정책 차단 — 사용자 수동 실행 필요)

deny 리스트가 `rm`/`Remove-Item`을 하드 차단(CLAUDE.md §4) → 아래는 untracked라 `git rm` 불가, 사용자가 직접 삭제:
- `ingestion/outputs/` §5.1 smoke/tmp 10개 (참조 0, gitignored)
- `.harness/narrative_marker.json` (dead artifact)
- 빈 폴더 `docs/system_overview/`, `docs/_IDEATION_WEB_INTELLIGENCE/`, `docs/Orchestration_Construction/` (내용 이관 완료)

> 누락 검증: 원본 134 .md(docs 91 + plans 35 + ingestion/plans 8) 전부 DEL(history 보존)·ARCHIVE·이관 중 하나로 추적됨. 삭제분은 `git log --diff-filter=D`로 복구 가능, `pre-refactor-2026-06-19` 태그로 전체 롤백 가능.
