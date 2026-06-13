# Playwright Required Sources

> Round 2 구현 대상 소스 목록 및 사유.

## KRX KIND (한국거래소 KIND 공시시스템)

- **URL**: https://kind.krx.co.kr/disclosure/todaydisclosure.do
- **사유**: JS 렌더링 의존 — 공시 목록이 JavaScript로 동적 로드됨. httpx 단순 fetch로는 빈 페이지 반환.
- **현재 status**: `PLAYWRIGHT_REQUIRED`
- **대안**: KRX 공식 OpenDART 연동 (`opendart` 소스 이미 구현됨). KRX API 신청(한국거래소 API 포털)으로 대체 가능.
- **Round 2 계획**: Playwright CDP 세션 + 공시 테이블 파싱. robots.txt 확인 필수.

## EU Press Corner (유럽연합 집행위원회 프레스코너)

- **URL**: https://ec.europa.eu/commission/presscorner/home/en
- **사유**: Angular SPA — 보도자료 목록이 JavaScript로 렌더링됨. RSS/Atom 피드 없음.
- **현재 status**: `PLAYWRIGHT_REQUIRED` (Round 1에서 `NO_KEY_REQUIRED` 오인 → 교정 완료)
- **대안**: EU Open Data Portal API (https://data.europa.eu/api) — 일부 공식 문서 접근 가능. 단 프레스코너 실시간 보도자료는 공식 API 없음.
- **Round 2 계획**: Playwright 렌더링 후 보도자료 카드 파싱. 쿼터: 수동 트리거 또는 30분+ 간격.

## 공통 주의사항

- login/CAPTCHA/paywall 페이지 접근 금지 — 순수 공개 페이지 렌더링만 허용
- 도입 전 대상 사이트 robots.txt + ToS 확인 필수
- User-Agent: `event-intelligence/0.7 (+ei)` 사용; 위장 금지
