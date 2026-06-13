# 83. Phase 1 정적 뉴스 6개 재프로브 보고서 (RISK 12-10)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

Phase 1 뉴스 6개(yna/hankyung/maekyung/aljazeera=RSS, zdnet_korea/etnews=HTML)는
`_PROBE_SPEC`에 존재해 Route 1로 라우팅되지만, 실측 검증과 CLI 진입점이 없어 docs/70의
CORE_READY 집계에서 미검증 상태였다.

## 2. 신규 CLI 러너

```powershell
python -m ingestion.runners.run_collection_probe --source <id> --max-items N [--query q] [--json] [--force]
```

- `load_env()` → health gate 사전 안내 → `run_collection_probe()` (gate 적용) → 보강 → 리포트.
- **보강 로직**: Route 1 결과의 raw_payload에서 —
  - xml 소스: 첫 `<item>`(또는 Atom `<entry>`)의 title/link → `sample_title`/`sample_url`,
    `<item>` 수 → `items_found`.
  - html 소스: `get_source_instance(sid).extract_candidate_urls(html)` → items/sample_url,
    `<title>` 태그 → sample_title.
  - 0건이어도 실패 처리하지 않음 → `next_action="update_selector"`.
- `--json` 출력에 attempts(전략명/성공/에러/소요시간) dump 포함.
- secret 미출력 — artifact 경로/상태만.
- exit code: LIVE_SUCCESS/LIVE_PARTIAL/RATE_LIMITED → 0, 그 외 1.

## 3. 재프로브 결과 (live, 소스당 1회, `--max-items 3`)

| source_id | status | items_found | sample_url | 판정 |
|-----------|--------|-------------|------------|------|
| yna | LIVE_SUCCESS | 120 (RSS item) | https://www.yna.co.kr/view/AKR20260612142100063 | **CORE_READY 편입** |
| hankyung | LIVE_SUCCESS | 50 (RSS item) | https://www.hankyung.com/article/202606123518i | **CORE_READY 편입** |
| maekyung | LIVE_SUCCESS | 50 (RSS item) | https://www.mk.co.kr/news/economy/12072950 | **CORE_READY 편입** |
| aljazeera | LIVE_SUCCESS | 25 (RSS item) | https://www.aljazeera.com/sports/2026/6/12/world-cup-2026-day-1-... | **CORE_READY 편입** |
| zdnet_korea | LIVE_SUCCESS | 10 (html 후보 URL) | https://zdnet.co.kr/view/?no=20260612142522 | **CORE_READY 편입** |
| etnews | LIVE_SUCCESS | 10 (html 후보 URL) | https://www.etnews.com/20260612000290 | **CORE_READY 편입** |

**6/6 LIVE_SUCCESS** — `source_registry.yaml` 해당 entry에
`status: LIVE_SUCCESS  # 2026-06-12 재프로브 실측` 주석과 함께 갱신 완료.
경고/차단/예외 소스 없음 (READY_WITH_CAUTION / MVP_EXCLUDED / REPAIRABLE_NEXT 해당 없음).

### WARNING (수집 비차단)

- yna sample_title이 콘솔에서 깨져 보였으나, raw_payload 확인 결과 **데이터는 정상 UTF-8**
  (`KAIST "농지 아닌 농업인력 부족이..."`). PowerShell 콘솔 코드페이지(cp949) 표시 문제일 뿐
  수집·저장 경로는 정상.

## 4. google_trends 1회 검증 (선택 항목)

`run_playwright_probe --site google_trends_explore` (local_file backend) 1회 실행:

- 결과: **RATE_LIMITED** (429 시그널 — 알려진 동작, docs/79)
- `ingestion/outputs/state/rate_limit_cache.json`에
  `next_retry: {"google_trends_explore:": {"at": "2026-06-12T09:59:47Z", "reason": "429_rate_limited"}}`
  **영속 확인** → 성공 기준(LIVE_SUCCESS 또는 RATE_LIMITED+영속) 충족.
- 즉시 재시도하지 않음 (정책 준수). next_retry 이후 자연 재시도 가능.

## 5. 결론

12-10 닫힘: CLI 러너 신규 + 6/6 LIVE_SUCCESS + registry 실측 갱신. Phase 1 뉴스 6개는
Celery 라운드(plans/012)에서 그대로 주기 수집 대상에 편입 가능.
