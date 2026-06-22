# Data Policy (contract spec — root pointer)

> **루트 계약 문서(thin).** 권위 본문(단일 출처)은 [`docs/5_REFERENCE/DATA_POLICY.md`](5_REFERENCE/DATA_POLICY.md).
> 이 파일은 핵심 저장 정책을 루트에서 즉시 발견할 수 있게 하는 얇은 포인터다 — 상세 표·보존 정책·변경은 canonical에서 관리한다.
> 불변 계약 스펙: `docs_lifecycle_audit`가 PROTECTED·move 금지로 고정(`tests/test_docs_lifecycle.py::test_contract_specs_protected`).

## 핵심 계약 (요약 — 권위는 canonical)
- **저장 O:** 제목(≤1024자), 요약(HTML 제거), 기사 URL(canonical), 게시 시각(UTC), feed 메타데이터.
- **저장 X:** 기사 **본문 전체**(저작권 경계 — 크롤/저장 금지), **작성자/개인정보**(미수집).
- **원칙:** 요약 + 증거 URL만 보관(전문 재배포 금지). raw_events 보존 정책은 canonical 참조.

**Authoritative source:** [`docs/5_REFERENCE/DATA_POLICY.md`](5_REFERENCE/DATA_POLICY.md)
