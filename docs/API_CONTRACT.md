# API Contract (contract spec — root pointer)

> **루트 계약 문서(thin).** 권위 본문(단일 출처)은 [`docs/5_REFERENCE/API_CONTRACT.md`](5_REFERENCE/API_CONTRACT.md).
> 이 파일은 핵심 API 계약을 루트에서 즉시 발견할 수 있게 하는 얇은 포인터다 — 상세 표·엔드포인트·변경은 canonical에서 관리한다.
> 불변 계약 스펙: `docs_lifecycle_audit`가 PROTECTED·move 금지로 고정(`tests/test_docs_lifecycle.py::test_contract_specs_protected`).

## 핵심 계약 (요약 — 권위는 canonical)
- **Base URL:** `http://localhost:8000` (prod는 공개 도메인). API 버전 v0.1.0.
- **CORS:** `allow_origins=settings.CORS_ALLOW_ORIGINS`(기본 `http://localhost:3000`), methods `GET/POST/PATCH/OPTIONS`, `allow_credentials=False`.
- **공개 노출 계약:** `GET /api/events`(목록)·`/api/events/{id}`(단건)은 **published 카드만** 반환. hold 카드는 공개 404(fail-closed).
- **admin/internal:** `X-Admin-Token` 헤더(production/staging 필수, dev 빈값 bypass+WARNING).

**Authoritative source:** [`docs/5_REFERENCE/API_CONTRACT.md`](5_REFERENCE/API_CONTRACT.md)
