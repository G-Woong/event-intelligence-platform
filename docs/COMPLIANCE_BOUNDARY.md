# Compliance Boundary (contract spec — root pointer)

> **루트 계약 문서(thin).** 권위 본문(단일 출처)은 [`docs/5_REFERENCE/COMPLIANCE_BOUNDARY.md`](5_REFERENCE/COMPLIANCE_BOUNDARY.md).
> 이 파일은 절대 금지선을 루트에서 즉시 발견할 수 있게 하는 얇은 포인터다 — 전체 금지 목록·근거·변경은 canonical에서 관리한다.
> 불변 계약 스펙: `docs_lifecycle_audit`가 PROTECTED·move 금지로 고정(`tests/test_docs_lifecycle.py::test_contract_specs_protected`).

## 절대 금지 (요약 — 권위는 canonical)
- **우회 전면 금지:** login·CAPTCHA·paywall·robots.txt·bot-protection(UA 위장 포함)·IP/proxy 남용 (CFAA/정보통신망법 위험).
- **비밀 노출 금지:** API 키·토큰·인증정보를 로그/화면/외부 전송에 노출 금지. `.env` 실값 출력·커밋·외부 전송 금지(길이/존재만).
- **개인정보:** 개인 SNS 계정 스크레이핑 금지.
- **소스 정책:** X(Twitter)·Blind = 로그인 필수 → BLOCKED. Reuters = bot_protection+paywall → NEEDS_LICENSE_OR_API.

**Authoritative source:** [`docs/5_REFERENCE/COMPLIANCE_BOUNDARY.md`](5_REFERENCE/COMPLIANCE_BOUNDARY.md)
