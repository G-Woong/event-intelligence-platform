# dcinside Live Body Probe (list / detail / body)

- run: 2026-06-22T03:14:47Z (UTC)
- overall condition_class: **LIMITED_PUBLIC_BODY**
- list_records: 30 · detail_attempted: 6 · body_extracted: 1
- no-bypass: robots-allowed gallery only; Cloudflare/captcha/login → stop; no PII/comments/images
- body policy: char_len + preview(≤200) only

## gallery: stockus
- robots_allowed: True · ai_crawler_disallowed: True · policy: public_allowed
- list_verdict: COMMUNITY_SIGNAL_ALIVE · list_count: 30 · condition_class: **LIMITED_PUBLIC_BODY**
- sample_titles: ['📣 26년 07월 03일 (금) 은 휴장입니다.', '2026년 미국 주식시장 휴장일정', '3월 9일 (월) 부터 서머타임으로 인해 미장 1시간 일찍 오픈 예정', '미국 주식 갤러리 ETF 추천 리스트', '투자 지침서, 정보글 주식관련 사이트, ETF 목록']
- sample_times: ['2022-01-28T17:01:52+09:00', '2026-01-20T23:34:56+09:00', '2026-03-04T10:40:39+09:00', '2024-11-03T23:12:14+09:00', '2024-07-14T20:06:45+09:00']

| detail_url | status | body_status | raw_chars | meaningful_chars | failure |
|---|---|---|---|---|---|
| https://gall.dcinside.com/mgallery/board/view/?id= | 200 | BODY_BOILERPLATE_ONLY | 142 | 1 | meaningful_body_too_short:1<120(raw= |
| https://gall.dcinside.com/mgallery/board/view/?id= | 200 | BODY_TOO_SHORT | 66 | 1 | meaningful_body_too_short:1<120(raw= |
| https://gall.dcinside.com/mgallery/board/view/?id= | 200 | BODY_TOO_SHORT | 110 | 29 | meaningful_body_too_short:29<120(raw |
| https://gall.dcinside.com/mgallery/board/view/?id= | 200 | BODY_BOILERPLATE_ONLY | 230 | 30 | meaningful_body_too_short:30<120(raw |
| https://gall.dcinside.com/mgallery/board/view/?id= | 200 | BODY_BOILERPLATE_ONLY | 308 | 51 | meaningful_body_too_short:51<120(raw |
| https://gall.dcinside.com/mgallery/board/view/?id= | 200 | extracted | 371 | 341 | - |

## Failure taxonomy
LIST_OK_DETAIL_BLOCKED / DETAIL_HTTP_403 / DETAIL_TIMEOUT / DETAIL_PARSE_EMPTY / BODY_TOO_SHORT / BODY_BOILERPLATE_ONLY / POLICY_LIMITED / STRUCTURE_CHANGED

> BF-2(adversarial 반영): body_status=extracted는 **UI 크롬(추천/스크랩/신고 버튼·첨부파일명·장 시간 안내) 제거 후 의미있는 본문 길이 ≥120자**일 때만 부여한다. raw_chars만 넘고 meaningful이 부족하면 BODY_BOILERPLATE_ONLY(=본문 추출 실패로 분류, 둔갑 금지).

## condition_class 세분
- PREVIEW_ONLY: list 메타만(상세 본문 정적 부재/차단)
- PUBLIC_DETAIL_PROBE_SUPPORTED: 상세 페이지 접근 가능하나 정적 본문 미추출(JS/이미지 렌더)
- LIMITED_PUBLIC_BODY: 공개 본문 소량 추출 성공(대량 승격은 정책/ToS 검토 후 별도)

## 정책 보정 note
공개 본문 소량 검증 결과와 ToS/저작권 리스크는 분리 기록. full body 대량 수집으로 즉시 승격 금지.