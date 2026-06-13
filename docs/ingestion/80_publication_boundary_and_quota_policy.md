# 80. Publication Boundary / Quota Policy 보고서 (RISK 12-7)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

수집(ingestion)과 게시(publication)의 경계가 정의되지 않아, 향후 게시 계층이 수집
artifact를 그대로 노출하면 저작권/약관(RISK-L01) 리스크가 있었다. 이번 라운드에서
게시 정책을 **운영 정책으로 명문화**하고 코드 레벨 가드를 준비했다.

## 2. 정책 파일 (`ingestion/configs/publication_policy.yaml`)

`default:` (보수적 기본):

| 항목 | 값 | 의미 |
|------|-----|------|
| allow_full_text_publication | false | 원문 전문 게시 금지 — 프리뷰+원문 링크만 |
| max_public_preview_chars | 200 | 공개 프리뷰 절단 길이 |
| attribution_required | true | 출처 표기 필수 |
| source_url_required | true | 원문 URL 없으면 게시 후보 불가 |
| raw_artifact_visibility | internal_only | raw_html/raw_payload/screenshot 외부 노출 금지 |
| quota_limit_notes | — | 게시 계층은 artifact 재사용, 소스 API 직접 호출 금지 |

`per_source:` 오버라이드 (재배포 제한이 강한 소스는 더 보수적으로):
- serper/tavily/exa/newsapi → `max_public_preview_chars: 0` (내부 시그널 전용, 비게시)
- reddit/dcinside/fmkorea → 100자 (개인 게시물 인용 최소화)
- federal_register/sec_edgar → 500자 (공공 정보, attribution 유지)

**registry 57개 entry는 수정하지 않았다** — 게시 정책은 별도 파일로 분리 (수집 메타데이터와
게시 정책의 변경 주기가 다르기 때문).

## 3. 코드 가드 (`ingestion/core/publication_policy.py`)

- `load_publication_policy(source_id)` — default+per_source merge (rate_limit_policy와 동일
  패턴). yaml 부재 시 무예외 + 보수적 기본값.
- `public_preview(text, source_id) -> str` — 절단 헬퍼 (limit=0이면 빈 문자열).
- `is_publication_candidate(item) -> (bool, reason)` — source_url 필수 가드.
- `raw_artifact_is_internal(source_id) -> bool`.

**수집 경로에는 연결하지 않았다** (테스트로 가드) — 이 모듈은 미래 게시 계층(API/프론트)용
이며, 수집을 막지 않는다.

## 4. 검증

`ingestion/tests/unit/test_publication_policy.py` — **10 passed**:
보수적 기본값, per_source merge, 프리뷰 절단/짧은 입력/limit=0/빈 입력,
source_url 없으면 후보 불가, raw internal-only, yaml 부재 무예외,
수집 경로 미연결 가드.

## 5. 이월

- 게시 계층(API/프론트) 구현 시 `is_publication_candidate`/`public_preview`를 출력 직전에
  적용하는 것이 통합 지점이다.
- 소스별 약관 정밀 검토(특히 NewsAPI developer plan, Reddit Data API)는 게시 기능 출시 전
  법무 확인 사항으로 남긴다.
