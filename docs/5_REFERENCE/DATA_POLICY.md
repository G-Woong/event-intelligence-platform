# Data Policy

## 저장 정책

### 무엇을 저장하는가

| 항목 | 저장 | 비고 |
|---|---|---|
| RSS 제목 (title) | YES (최대 1024자) | |
| RSS 요약 (summary) | YES (HTML 제거 후) | 본문 전체 저장 금지 |
| 기사 본문 | **NO** | 저작권 경계 — 크롤링/저장 불가 |
| 기사 URL (canonical link) | YES | |
| RSS 게시 시각 (published_at) | YES | UTC 변환 |
| Feed 메타데이터 (feed_title, tags) | YES | JSONB raw_metadata |
| 작성자/개인정보 | **NO** | 수집/저장하지 않음 |

### raw_events 보존 정책

- **현재**: TTL 미정 (STEP 008+에서 결정)
- **예정**: 90일 후 아카이브 또는 삭제 (STEP 008+ 정의)
- **status=processed**: agent가 처리 완료한 row (STEP 008에서 업데이트)

### stream:raw_events 보존

- Redis Stream은 consumer group이 ACK한 메시지를 자동 정리.
- 장기 보관 불필요 — DB raw_events에 영구 저장됨.

## 저작권

- **RSS 요약(summary)** 은 일반적으로 공개 배포 목적으로 제공됨 (fair use / 합리적 사용).
- **본문 크롤링 금지** — `docs/COMPLIANCE_BOUNDARY.md` 참조.
- 수집 출처를 UI에 항상 표시할 것 (source_name + url).

## 개인정보

- 이 시스템은 개인 사용자 데이터를 수집하지 않음.
- RSS 피드에 포함된 저자명 등은 `raw_metadata`에만 저장되며 검색/인덱싱에 사용되지 않음.
