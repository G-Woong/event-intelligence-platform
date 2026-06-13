# docs/47 — Remaining Source Security Check

**Date**: 2026-06-08  
**Round**: Remaining Source Resolution & Browser Strategy Audit  
**Status**: SECURITY PASS

---

## Step 0 보안 검사 결과

### rg 스캔 (ingestion/outputs)

대상 패턴: `EIA_API_KEY|api_key=|Authorization|Bearer|token|CLIENT_SECRET|PRODUCT_HUNT_ACCESS_TOKEN|OPENAI_API_KEY|SERVICE_KEY|serviceKey`

**매칭 파일 목록** (경로만, 원문 미출력):

| 파일 | 위험여부 |
|---|---|
| `reports/api_connectivity_report.md` | SAFE — "Bearer token required" 설명 텍스트만. 실값 없음. |
| `reports/api_live_probe_report.md` | SAFE — 보고서 표 헤더 텍스트. |
| `jsonl/api_connectivity_results.jsonl` | SAFE — status/next_action 필드만. |
| `raw_payload/igdb/*.json` | SAFE — API 응답 본문만 (Twitch 토큰 포함 안 됨). |
| `extracted_payload/naver_news_search/*.json` | SAFE — 추출 결과만. |
| `raw_payload/youtube/*.json` | SAFE — 응답 본문만. |
| `extracted_payload/coinbase_market/*.json` | SAFE — 응답 본문만. |
| `jsonl/x_results.jsonl` | SAFE — BLOCKED 결과 메타만. |
| `jsonl/product_hunt_results.jsonl` | SAFE — MISSING_KEY 결과 메타만. |
| `jsonl/*.jsonl` | SAFE — 결과 상태 데이터. |
| `reports/x_report.md` | SAFE — "bearer token required" 설명만. |

**결론**: 실제 API 키/토큰 값 없음. 모든 매칭은 설명 텍스트 또는 상태 코드.

### env_hygiene 검사

```
[AMBIGUOUS_ALIAS] line 75 key=CLIENT_ID | use NAVER_CLIENT_ID instead
[AMBIGUOUS_ALIAS] line 76 key=CLIENT_SECRET | use NAVER_CLIENT_SECRET instead
```

**위험여부**: LOW — .env의 `CLIENT_ID`/`CLIENT_SECRET` bare 키가 NAVER alias와 중복. 실키 노출 아님.  
**권고**: `.env`에서 `CLIENT_ID`→`NAVER_CLIENT_ID`, `CLIENT_SECRET`→`NAVER_CLIENT_SECRET`으로 이름 변경.

### 공공 API 4종 키 존재 여부 (값 없이 present/missing만)

| 키 | 상태 |
|---|---|
| CULTURE_INFO_API_KEY | present |
| CULTURE_INFO_KEY | present |
| KMA_API_KEY | present |
| TOUR_API_KEY | present |
| ITS_API_KEY | present |

→ 모두 present. Live 프로브 진행 가능.

---

## 판정

**SECURITY PASS** — 실키 노출 없음. AMBIGUOUS_ALIAS 2건은 WARNING 수준 (사용자 후속조치 권고).
