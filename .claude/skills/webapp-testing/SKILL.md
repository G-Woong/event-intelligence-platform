---
name: webapp-testing
description: 로컬 Next.js 프론트(:3000) + FastAPI 백엔드(:8000)를 동시 기동해 Playwright로 브라우저 E2E를 돌릴 때 사용. Event Card 렌더·증거 pane·도메인 타임라인 노출 검증, 프론트↔API 계약 회귀, hold 카드 비노출(공개 404) 시각 확인. pytest가 못 잡는 UI/렌더 경로 전용. (단위/통합은 test-validation-skill.)
license: Apache-2.0 (upstream)
upstream: https://github.com/anthropics/skills/tree/main/skills/webapp-testing
adapted_for: WEB_INTELLIGENCE_HARNESS_EVOLUTION.md S2
---

# webapp-testing (Next.js + FastAPI E2E)

> upstream `anthropics/skills/webapp-testing`(Apache-2.0)를 본 프로젝트 포트/기동 커맨드로 적응.
> **MCP M4(Playwright MCP)와 역할 분담:** M4=사람이 보며 즉석 디버그 / 이 skill=재현 가능한 CI식 고정 시나리오.

## 언제 쓰나
- 프론트 변경 후 UI 렌더 회귀 검증(현재 frontend e2e 8개 → 확장).
- `/api/events`·`/api/domains/{d}` 응답이 화면에 바르게 매핑되는지(additive 필드 heat/domains/timeline).
- fail-closed 게이트 시각 검증: hold 카드가 공개 목록·상세에서 404인지.

## 절차
1. `scripts/with_server.py`로 백엔드·프론트를 동시 기동(서버 준비될 때까지 대기 후 테스트 실행, 종료 시 정리).
2. Playwright(Python)로 navigate → `snapshot`(accessibility tree) → assertion.
3. 네트워크 캡처로 프론트→FastAPI 계약 확인.
4. 실패 시 스크린샷을 `ingestion/outputs/` 외 임시 경로에 남기고 artifact-manifest-skill로 기록(전문/비밀 금지).

## 안전·제약
- **localhost 전용.** 외부 네트워크/소스 크롤 아님(우회 정책 무관).
- `.env` 미열람(서버는 기존 기동 스크립트가 로드). 비밀 출력 금지.
- Playwright `run_code_unsafe` 류 임의코드 실행 금지.

## 의존
- `pip/uv`로 `playwright` (Python) + `python -m playwright install chromium` 1회 필요(사용자 환경).
- Node 측 `npm run dev`(frontend), `uvicorn app.main:app`(backend) 기동 가능해야 함.
