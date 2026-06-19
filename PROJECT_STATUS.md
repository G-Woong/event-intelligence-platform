# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 하는 중인가:** 하네스 재구축 전, 레포에 쌓인 **찌꺼기 메모리·죽은 코드·중복 문서**를 누락 없이 전수조사해서, "무엇을 지우고/합치고/옮길지"를 파일 단위로 규정한 **리펙토링 구현 명세서**를 작성했습니다.
- **이번 턴에 실제로 끝낸 것:** 3개 독립 감사(docs 91 전수 / 죽은코드 전수 / 메모리·설정·하네스)를 grep 교차검증해, 134개 문서 + 코드/설정 찌꺼기의 처리 명세를 1개 문서로 완성. 정렬축(생애주기)·통폐합 강도(공격적)·고아 pipeline 모듈(유지) 결정 확정.
- **지금 막힌 것:** 없음. **단, 실행은 사용자 검토 후로 동결**(대량 git mv/rm이라 승인 전 미실행).

## 📋 자동 수집 사실 (machine_status.json)
- repo: WEB_INTELLIGENCE · turn 4 · 변경 **1건(docs: 스펙 1, untracked)** · code 0
- audit_required: **false** · audit_types/flags: **[] (강제 감사 라우팅 없음 — 가벼운 docs 턴)**
- 열린 RISK: **17건**(HIGH 3 / MED 7 / LOW 7) — 본 턴 신규/종결 0(스펙은 계획서일 뿐 미실행)
- 비밀 스캔: (직전 PASS 유지, code 무변경) · dead-code 후보: 직전 221건 유지(본 턴 재스캔 안 함, code 무변경)
- 팀 감사: 없음(flag 0). 대신 **3개 인벤토리 감사 에이전트**(docs/deadcode/memory)를 본 작업 입력으로 병렬 실행

## ✅ 이번 턴에 달성한 것 (리펙토링 명세)
- **전수조사:** docs 91 + 루트 plans 35 + ingestion/plans 8 = **134 .md**, code 찌꺼기(outputs smoke/tmp 10·고아 pipeline 5·dead yaml 6·dup yaml 3·DEAD `narrative_marker.json`)까지 grep 근거로 식별.
- **명세서 산출:** `docs/Harness_Construction/07_REPO_REFACTOR_AND_CONSOLIDATION_SPEC.md` — 타깃 구조(생애주기 5버킷), 파일별 액션표(DELETE/MERGE/ARCHIVE/KEEP+이관), 9단계 실행 플랜, 매 단계 검증게이트(테스트 1517 유지·링크깨짐 0).
- **직전 감사 오판 2건 교정:** `markdown_extractor`(live), `agent_worker.py`(Docker entrypoint)·CLI runner·alembic을 삭제대상에서 제외(false-positive 차단). `ingestion/agents`↔`agents`는 둘 다 live(네이밍 스멜).
- **결정 확정:** 정렬축=생애주기 / 레거시=공격적 통폐합 / 고아 pipeline 5모듈=유지+ROADMAP 명시(삭제 금지).

## ❌ 달성하지 못한 것 & 왜
- **실행(삭제·이동·통폐합):** 미수행. 사용자가 "명세서 검토 먼저" 선택 → 대량 git mv/rm은 승인 후 Phase 0(태그+브랜치)부터 진행.
- **미결정 D2~D6:** plans/ 자동생성 slug 3개 삭제, `ingestion/agents` rename, `docs_lifecycle_audit.json` 처리 등은 사용자 확정 대기.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- **고아 pipeline 5모듈의 미래:** "미래 배선"인지 확정은 사용자 의도에 의존 — 유지로 결정했으나 배선 시점은 UNKNOWN(2_ROADMAP에 명시 예정, 명세 실행 시).
- **명세 실행 전 정합성:** 명세의 MERGE 흡수 정확도는 실행·검증게이트(테스트 1517·링크 0)를 통과해야 확정. 현재는 계획 단계.

## ⚠️ 이번 턴 종결/갱신 RISK
- **신규/종결 0.** R-StaleDocs(LOW)·R-DeadCodeAudit(LOW)에 **본 명세서를 통폐합 실행 계획서로 포인터 연결**(단일출처: 실제 처리 맵은 스펙에 존재).

## 👉 다음 턴 진입 조건
- **사용자 검토 후 실행:** 명세서 읽고 구조/삭제목록/D2~D6 확정 → "실행" 지시 시 Phase 0부터 단계별 게이트 통과하며 진행.
- **병행 가능:** 명세 검토와 무관하게 기능 개발 진입은 가능(명세는 정리용, 차단 아님).

## 📁 근거 (이번 턴 핵심)
- `docs/Harness_Construction/07_REPO_REFACTOR_AND_CONSOLIDATION_SPEC.md`(산출물)
- 감사 입력: docs 전수/죽은코드 전수/메모리·설정 3 에이전트(grep 근거)
- `docs/_DECISIONS/2026-06.md`(#11), `docs/_RISK/RISK_REGISTER.md`(R-StaleDocs 포인터)
