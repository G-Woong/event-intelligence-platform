# GDELT Live Body Probe (R-Gdelt429 evidence)

- run: 2026-06-22T02:46:25Z (UTC)
- verdict: **GDELT_PROVIDER_THROTTLED_PENDING_RESUME**
- attempts: 3 · success_queries: 0 · url_candidates: 0 · body_success: 0
- contract: spaced probe(≥interval+jitter), maxrecords≤50, no parallel, 429→cooldown, no bypass
- body policy: char_len + preview(≤200) only (no full-text stored)

| query | gdelt_status | rows | eng | domain | country | article_date | body_status | chars | saved_eq | failure |
|---|---|---|---|---|---|---|---|---|---|---|
| economy | PROVIDER_429 | 0 | 0 | - | - | - | - | 0 | False | PROVIDER_429;cooldown_until=2026-06-22T03:00:29Z |
| election | PROVIDER_429 | 0 | 0 | - | - | - | - | 0 | False | PROVIDER_429;cooldown_until=2026-06-22T03:00:52Z |
| climate | PROVIDER_429 | 0 | 0 | - | - | - | - | 0 | False | PROVIDER_429;cooldown_until=2026-06-22T03:01:16Z |

## Failure taxonomy (rows)
GDELT_SUCCESS / GDELT_SUCCESS_EMPTY / PROVIDER_429 / BODY_HTTP_403 / BODY_HTTP_404 / BODY_TIMEOUT / BODY_UNSUPPORTED_CONTENT_TYPE / BODY_TOO_SHORT / BODY_EMPTY_AFTER_PARSE / NON_ENGLISH_SKIPPED / DUPLICATE_URL

## Security
GDELT는 키 불필요. API 키/토큰 값 없음. 본문 전문 미저장(preview≤200).