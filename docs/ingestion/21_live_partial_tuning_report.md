# 21. LIVE_PARTIAL 튜닝 보고서

작성일: 2026-06-03

## 수정된 소스

| 소스 | 문제 | 수정 내용 | 결과 |
|---|---|---|---|
| yna | RSS URL 404 (all.xml 삭제) | endpoint → news.xml | LIVE_SUCCESS (items=120) |
| bok_ecos | URL에 언어 파라미터 누락 + 필드명 오탐 | /json/kr/1/5/ + meaningful_fields 수정 | LIVE_SUCCESS (items=5) |
| culture_info | HTML 오류 페이지 반환 (날짜 파라미터 누락) | probe_spec extra_params 추가 + XML 형식 | LIVE_SUCCESS (items=2) |
| twelve_data | 엔드포인트 404 (필수 파라미터 누락) | probe_spec에 symbol/interval 추가 | LIVE_SUCCESS (items=3) |

## 미해결

| 소스 | 상태 | 사유 |
|---|---|---|
| gdelt | RATE_LIMITED | 429 응답, rate_limit_policy 적용 (cooldown 300s) |
| kma | INVALID_KEY | 키 인증 실패 (공공데이터포털 키 형식 확인 필요) |
| its | INVALID_KEY | 동일 |
| igdb | INVALID_KEY | Twitch OAuth 필요 (별도 라운드) |
| tour | NETWORK_ERROR | 서버 오류 (500) |
