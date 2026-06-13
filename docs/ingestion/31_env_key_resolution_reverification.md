# 31 — Env Key Resolution Reverification

**검증 일시**: 2026-06-03  
**보안**: 키 값 절대 미출력. present/missing 상태만 기재.  
**env_path**: `C:\Users\computer\Desktop\business\claude\.env`

---

## 1. env_loader 동작 검증

| 항목 | 결과 |
|---|---|
| load_env() env_path 명시 로딩 | PASS — env_path 전달 시 해당 파일 읽음 |
| present/missing만 반환 | PASS — env_status() 값 노출 없음 |
| alias 동작 | PASS (4개 alias 확인 아래) |
| GAC 경로 존재만 확인 | PASS — check_gcp_credentials()는 경로 존재만 반환 |

---

## 2. 현재 등록된 alias 4개

| 원래 키 | alias |
|---|---|
| NAVER_CLIENT_ID | CLIENT_ID |
| NAVER_CLIENT_SECRET | CLIENT_SECRET |
| BOK_ECOS_API_KEY | ECOS_API_KEY |
| PRODUCT_HUNT_ACCESS_TOKEN | PRODUCT_HUNT_API_KEY |

모두 정상 동작 확인. NAVER_CLIENT_ID, BOK_ECOS_API_KEY, PRODUCT_HUNT_ACCESS_TOKEN 모두 `present`.

---

## 3. 전체 키 상태

| 키 이름 | 상태 | 비고 |
|---|---|---|
| OPENAI_API_KEY | present | — |
| LANGSMITH_API_KEY | present | — |
| LANGSMITH_TRACING | present | — |
| LANGSMITH_PROJECT | present | — |
| MILVUS_HOST | present | — |
| MILVUS_PORT | present | — |
| REDIS_URL | present | — |
| NAVER_CLIENT_ID | present | alias ← CLIENT_ID |
| NAVER_CLIENT_SECRET | present | alias ← CLIENT_SECRET |
| BOK_ECOS_API_KEY | present | alias ← ECOS_API_KEY |
| PRODUCT_HUNT_ACCESS_TOKEN | present | alias ← PRODUCT_HUNT_API_KEY |
| GOOGLE_API_KEY | present | — |
| CSE_CX | present | — |
| EIA_API_KEY | present | — |
| OPENDART_API_KEY | present | — |
| IGDB_CLIENT_ID | present | — |
| IGDB_CLIENT_SECRET | present | — |
| KMA_API_KEY | present | 값은 있으나 서버에서 401 (키 형식 문제) |
| TOUR_API_KEY | present | — |
| ITS_API_KEY | present | — |
| KOFIC_API_KEY | present | — |
| KOPIS_API_KEY | present | — |
| ALADIN_TTB_KEY | present | — |
| CULTURE_INFO_KEY | present | — |
| TMDB_API_KEY | present | — |
| YOUTUBE_API_KEY | present | — |
| FINNHUB_API_KEY | present | — |
| TWELVE_DATA_API_KEY | present | — |
| ALPHA_VANTAGE_API_KEY | present | — |
| POLYGON_API_KEY | present | — |
| SERPER_API_KEY | present | — |
| TAVILY_API_KEY | present | — |
| EXA_API_KEY | present | — |
| NEWSAPI_API_KEY | present | — |
| GNEWS_API_KEY | present | — |
| GUARDIAN_API_KEY | present | — |
| NYT_API_KEY | present | — |
| SEC_USER_AGENT | present | — |
| CULTURE_INFO_API_KEY | missing | 실제 키는 CULTURE_INFO_KEY |
| KOBIS_API_KEY | missing | 실제 키는 KOFIC_API_KEY |
| YOUTUBE_DATA_API_KEY | missing | 실제 키는 YOUTUBE_API_KEY |

---

## 4. 발견된 키 이름 불일치 (3건)

| source_id | registry 기재 env_keys | 실제 .env 키 이름 | 수정 방향 |
|---|---|---|---|
| google_programmable_search | GOOGLE_CUSTOM_SEARCH_API_KEY, GOOGLE_CUSTOM_SEARCH_CX | GOOGLE_API_KEY, CSE_CX | alias 추가 또는 connectivity config 키 이름 변경 |
| culture_info | CULTURE_INFO_API_KEY | CULTURE_INFO_KEY | env_loader alias 추가 또는 registry 수정 |
| youtube (내부) | YOUTUBE_DATA_API_KEY (일부 문서) | YOUTUBE_API_KEY | connectivity config 통일 (YOUTUBE_API_KEY 사용) |

---

## 5. 권장 alias 추가 (env_loader._ALIASES)

```python
_ALIASES = {
    ...기존 4개...,
    "GOOGLE_CUSTOM_SEARCH_API_KEY": ["GOOGLE_API_KEY"],
    "GOOGLE_CUSTOM_SEARCH_CX": ["CSE_CX"],
    "CULTURE_INFO_API_KEY": ["CULTURE_INFO_KEY"],
}
```

---

## 6. WARNING 항목

| 키 | 경고 |
|---|---|
| KMA_API_KEY | 값 존재하나 API 서버 401. 키 재발급 또는 URL 인코딩 필요. |
| CLIENT_ID | AMBIGUOUS_ALIAS — NAVER_CLIENT_ID 로 명확히 전환 권장 (check_env_hygiene 경고) |
| CLIENT_SECRET | AMBIGUOUS_ALIAS — NAVER_CLIENT_SECRET 로 명확히 전환 권장 |
| CSE_CX | KEY_NOT_IN_EXAMPLE — .env.example에 추가 필요 |
| ECOS_API_KEY | KEY_NOT_IN_EXAMPLE — .env.example에 추가 필요 |
| GOOGLE_API_KEY | KEY_NOT_IN_EXAMPLE — .env.example에 추가 필요 |
