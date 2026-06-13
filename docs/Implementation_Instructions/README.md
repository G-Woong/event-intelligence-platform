# Implementation_Instructions — INDEX

소스 연결 Closing 라운드의 지시문/진행 문서 모음. **신규 세션은 개별 00~10을 진입점으로 쓰지 말 것.**

## 읽는 순서 (신규 에이전트)

1. **[IMPLEMENTATION_TRACE_FINAL.md](./IMPLEMENTATION_TRACE_FINAL.md)** — 적용 완료 상태 단일 출처(1순위).
2. `docs/ingestion/70_source_status_master.md` · `86_source_role_classification_matrix.md` · `92_mvp_collection_frequency_draft.md` — 소스 status/역할/주기.
3. `ingestion/outputs/jsonl/runner_orchestration_readiness_*.jsonl` — 호출 가능한 runner 계약(최신).
4. [_progress/closing_checklist.md](./_progress/closing_checklist.md) — 15 checklist iter 기록.

## 문서 상태

| 문서 | 상태 | 비고 |
|---|---|---|
| 00_OVERVIEW_AND_CLOSING_LOOP.md | **ROOT (유효)** | 절대 제약/Closing Loop 원문 — 운영 제약은 계속 유효 |
| 01~10_*.md | **APPLIED / SUPERSEDED — stub** | 원래 경로는 1~2줄 stub. 원문 전체는 `_archive_applied/`에 보존 |
| _archive_applied/01~10_*.md | 보존(historical) | 적용 완료된 원본 지시서 전문. 활성 지시로 재실행 금지 |
| ROADMAP.md | **APPLIED / SUPERSEDED — stub** | 방법론은 TRACE_FINAL 부록 A로 흡수. 활성 로드맵 아님 |
| IMPLEMENTATION_TRACE_FINAL.md | **현재 1순위** | 통합 trace (부록 A=실행 순서/방법론) |
| _progress/closing_checklist.md | 활성 | iter 기록 누적 |

01~10/ROADMAP은 원래 경로에 **stub**만 남기고 원문 전체를 `_archive_applied/`로 `git mv`(경로 이력 보존)했다.
신규 세션은 stub/archive를 활성 지시로 재실행하지 말고 **TRACE_FINAL**을 단일 출처로 사용하라.

## 아직 유효한 운영 제약 (00 문서 요약)

- 실제 `.env` 키 값 출력/로그/저장 금지(존재/길이만). 키 하드코딩 금지.
- rm / Remove-Item / git reset --hard / git clean / git push 금지(사용자 명시 전).
- CAPTCHA/Turnstile/로그인/페이월 우회 금지. proxy rotation/내부 RPC 해킹 금지.
- provider rate limit 무시 연속 재시도 금지. 실패를 PASS로 보고 금지.
- 정보 제공이지 투자 조언 아님.

## 현재 종료 상태 (2026-06-13)

15 checklist 중 **PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1**(google_trends_explore, fallback chain으로 비차단).
수정 가능한 코드 결함 0건. 다음 단계 = plans/012 Celery/LangGraph 오케스트레이션.
