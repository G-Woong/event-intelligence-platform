# Event Schema (contract spec — root pointer)

> **루트 계약 문서(thin).** 권위 본문(단일 출처)은 [`docs/5_REFERENCE/EVENT_SCHEMA.md`](5_REFERENCE/EVENT_SCHEMA.md).
> 이 파일은 핵심 스키마 계약을 루트에서 즉시 발견할 수 있게 하는 얇은 포인터다 — 전체 필드표·DDL·변경은 canonical에서 관리한다.
> 불변 계약 스펙: `docs_lifecycle_audit`가 PROTECTED·move 금지로 고정(`tests/test_docs_lifecycle.py::test_contract_specs_protected`).

## 핵심 계약 (요약 — 권위는 canonical)
- **RawEvent:** `source / url / fetched_at(UTC) / raw_text / raw_metadata / raw_event_id` — 수집 원본 + agent 파이프라인 추적 키.
- **event_cards:** 정규화된 공개 카드(entity/sector/impact/summary/evidence + status published|hold). 본문 전체 비저장(요약+증거 URL만).
- **Event 타임라인(설계, 🔲 미구현):** `events`/`event_updates`/`cluster_event_map`/`event_links` + `event_cards.event_id` nullable FK — Part 2(진화하는 사건 객체) 참조, ADR#16.

**Authoritative source:** [`docs/5_REFERENCE/EVENT_SCHEMA.md`](5_REFERENCE/EVENT_SCHEMA.md)
