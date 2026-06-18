"""P0 통합 배선 — ingestion 엔진 → raw_events PG → Redis → worker → LangGraph → event_cards.

이 패키지는 ingestion(A) 출력과 downstream 앱(B)을 잇는 adapter layer다.
ingestion 코드를 backend에 섞지 않고, 명확한 writer/contract 경계로 연결한다.

핵심 원칙:
  - bridge_to_raw_events 의 db_writer 주입점을 그대로 사용(중복 경로 생성 금지).
  - raw_events 적재는 backend 의 POST /api/admin/raw-events 를 경유한다.
    backend 가 PG upsert(on_conflict content_hash) + Redis XADD(stream:raw_events) 를
    모두 수행하므로, 그 뒤(worker→agent→LangGraph→event_cards)는 기존 다운스트림이 처리한다.
  - source 특성(record_type)별 계약을 검증한다(generic text 로 밀어넣지 않음).
  - mirror writer 는 fallback 일 뿐 P0 complete 판정 단독 근거가 될 수 없다.
"""
