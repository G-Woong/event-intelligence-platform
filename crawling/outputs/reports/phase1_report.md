# Phase 1 크롤링 결과 보고서

생성일: 2026-05-31

## 전체 결과 요약

| source | status | score | body 확인 | 비고 |
|---|---|---|---|---|
| bbc | SUCCESS | 0.806 | ✓ PSG 챔피언스리그 기사 (실제 기사 본문) | - |
| ap_news | SUCCESS | 0.916 | ✓ 미국-이란 관련 기사 (published_at 포함) | CAPTCHA 오탐지 수정 |
| techcrunch | PARTIAL | 0.676 | ✓ Google Gemini Spark 기사 (published_at 미추출) | Turnstile 오탐지 수정 |
| the_verge | SUCCESS | 0.976 | ✓ 실제 기사 본문 확인 | 최고 점수 |
| zdnet_korea | PARTIAL | 0.676 | ✓ 한국어 자동차 산업 정책 기사 | published_at 미추출 |
| etnews | SUCCESS | 0.826 | ✓ 한국어 IT/산업 뉴스 기사 | - |
| yna | PARTIAL | 0.676 | ✓ 한-일 방위비 관련 연합뉴스 기사 | published_at 미추출 |
| hankyung | SUCCESS | 0.826 | ✓ 미국 동맹 압박 관련 경제지 기사 | 로그인 모달 오탐지 수정 |
| maekyung | SUCCESS | 0.826 | ✓ 한국 경제 뉴스 기사 | - |
| aljazeera | SUCCESS | 0.866 | ✓ 중동 뉴스 기사 | - |

- **SUCCESS**: 7개 (bbc, ap_news, the_verge, etnews, hankyung, maekyung, aljazeera)
- **PARTIAL**: 3개 (techcrunch, zdnet_korea, yna)
- **FAILED/BLOCKED**: 0개

## 공통 PARTIAL 원인

PARTIAL(0.676) 소스 3개 모두 **`published_at` 미추출**이 원인.
- `quality_score` 가중치에서 `published_at_present: 0.10` 누락으로 0.776 → 0.676.
- 본문은 정상 추출(800자 이상, 5문단 이상) — 운영 가능 수준.
- **다음 라운드**: 각 소스별 날짜 selector 추가 (`article:published_time`, 소스별 커스텀 태그).

## 수행한 Fallback/수정

1. **CAPTCHA 오탐지 수정** (`error_taxonomy.py`): `recaptcha`, `captcha` 일반 단어 → 실제 challenge 페이지 신호로 축소 (cf-challenge, `enable javascript and cookies`, `__cf_chl_opt` 등).
2. **Turnstile 오탐지 수정**: `challenges.cloudflare.com` 스크립트 태그 참조 → false positive 제거.
3. **로그인 모달 오탐지 수정**: `로그인이 필요` → 실제 redirect 패턴으로 교체.
4. **trafilatura `output_format="python"` 버그 수정**: 인수 제거.
5. **BBC 기사 URL 패턴 수정**: 섹션 URL → `/news/articles/` 패턴.

## Artifact 저장 위치

```
crawling/outputs/
  raw_html/{source_id}/          ← 진입 페이지 + 기사 페이지 HTML
  extracted_text/{source_id}/    ← 추출 텍스트 (header + body)
  jsonl/phase1_results.jsonl     ← 전체 결과 행
  jsonl/{source_id}_results.jsonl
  reports/{source_id}_report.md  ← 소스별 리포트
```

## 다음 라운드 우선순위

1. **published_at 추출 개선**: OG 태그, `article:published_time`, 소스별 JSON-LD 파싱 → PARTIAL → SUCCESS 전환.
2. **본문 품질 세분화**: boilerplate_ratio 계산 (현재 0.0 고정) → 품질 판단 정확도 향상.
3. **한국어 소스 인코딩 보강**: EUC-KR 혼용 감지 (`charset_normalizer`).
4. **Phase 2 소스 구현**: 커뮤니티 소스 (hackernews, naver_news 등).
