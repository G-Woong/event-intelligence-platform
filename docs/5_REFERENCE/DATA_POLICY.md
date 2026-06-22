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

## 커뮤니티 공개 본문 수집 — dcinside `LIMITED_PUBLIC_BODY` (R-DcToS 유지)

라이브 재검증(`scripts/dcinside_live_body_probe.py`, `reports/dcinside_live_body_probe.md`) 결과,
robots 허용 갤러리(`stockus`)에서 공개 게시글 상세의 **소량 산문 본문이 기술적으로 추출 가능**함을
확인했다(보수적 필터로 UI 크롬·이미지 파일명·숫자 카운터·반복 URL 제거 후 의미있는 산문 ≥120자 1건).
이를 condition class **`LIMITED_PUBLIC_BODY`** 로 기록한다.

**정책 — 역량(가능)과 적법(허용)을 분리한다:**

| 구분 | 상태 |
|---|---|
| 공개 list 메타(title/url/time) 수집 | 허용 — community_signal |
| 공개 상세 **소량** 본문 추출 역량 | 기술적으로 확인됨(`LIMITED_PUBLIC_BODY`) |
| 공개 상세 본문 **대량** 수집/승격 | **금지** — ToS 자동수집 적법성 UNVERIFIED |
| publish(외부 공개) | **봉인** — CommunityCorroborationGate(외부 확인 전 차단) |
| 작성자 닉네임·댓글·이미지·PII | **수집 안 함** |
| robots(AI 크롤러 site-wide Disallow) | generic UA로 존중(우회 0) |

- `LIMITED_PUBLIC_BODY` 확인이 **수집 승격 근거가 되지 않는다.** 본문 대량 수집은 `R-DcToS`(ToS
  법무 검토) 통과 전까지 봉인 유지한다 — 역량 확인 ≠ 적법 허용.
- "본문 추출됨"은 **UI 크롬/이미지 캡션/링크 나열을 제거한 의미있는 산문 ≥120자**일 때만 인정한다
  (`BODY_BOILERPLATE_ONLY` 강등 — 둔갑 금지).
- 본문 전문은 저장하지 않는다(요약/길이/증거 URL만, 위 "저장 정책" 동일 적용).
- 단일 갤러리(`stockus`) 검증 범위이며 일반화하지 않는다.

관련: `docs/_RISK/RISK_REGISTER.md` §R-DcToS · `docs/COMPLIANCE_BOUNDARY.md`(no-bypass).
