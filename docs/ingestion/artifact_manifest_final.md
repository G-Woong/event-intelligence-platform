# Artifact Manifest (final)

- 최종 갱신: 2026-06-13 (UTC)
- 목적: `ingestion/outputs/**`는 `.gitignore`로 **커밋하지 않는다**. 그러나 문서가 evidence로 artifact 경로를 참조하므로,
  각 artifact의 **재생성 명령 + 크기/SHA256/timestamp + 관련 runner + checklist**를 기록해 재현 가능성을 보존한다.
- 원칙: 본 매니페스트는 **경로·명령·hash/size만** 기록한다. raw payload/본문 전문/기사 전문/secret 값은 복사하지 않는다.

## 1. 왜 outputs를 커밋하지 않는가

- `raw_payload/`(787 files)·`rendered_dom/`(132)·`screenshots/`(64)·`extracted_text/`(52)·`raw_signal/`(38)은
  **용량·저작권(기사 원문)·민감성·변동성**이 크다. git 추적 시 저장소가 비대해지고 외부 콘텐츠 재배포 리스크가 생긴다.
- 따라서 `.gitignore`로 제외하고(검증: `git check-ignore ingestion/outputs/...`), 재현은 아래 runner 재실행으로 한다.
- `outputs/state/rate_limit_cache.json`(local_file backend cooldown 영속)도 런타임 상태이므로 커밋하지 않는다.

## 2. 핵심 감사 JSONL (재생성 가능 evidence)

모든 명령의 prefix: `.\.venv\Scripts\python.exe -m` (Windows venv, repo root에서 실행). 출력은 `ingestion/outputs/jsonl/<prefix>_<ts>.jsonl` + `reports/<prefix>_<ts>.md`.

| artifact (latest) | size | sha256(16) | runner (재생성 명령) | checklist |
|---|---|---|---|---|
| primary_seed_live_audit_20260613_092855.jsonl | 368B | F975FCE13F42855B | `ingestion.runners.run_primary_seed_live_audit` | 1차 seed audit (docs/88) |
| enrichment_live_audit_20260613_095628.jsonl | 63960B | 725B99540F9C2298 | `ingestion.runners.run_enrichment_live_audit` | 2차 enrichment audit (docs/89) |
| conditional_sources_e2e_audit_20260613_081243.jsonl | 14593B | 3D18CACA3B609CC3 | `ingestion.runners.run_conditional_sources_e2e_audit` | #1~#5 (gdelt/ap_news/newsapi/trends) |
| playwright_selector_sources_e2e_audit_20260613_085151.jsonl | 48618B | 09E50959E3FFBDA1 | `ingestion.runners.run_playwright_selector_sources_audit` | #6a~#8 |
| api_partial_sources_e2e_audit_20260613_092502.jsonl | 9356B | BF205D462E0FA599 | `ingestion.runners.run_api_partial_sources_audit` | #9~#13 |
| external_rate_limit_recheck_20260613_095438.jsonl | 2336B | A05AC46D3824CB82 | `ingestion.runners.run_external_rate_limit_recheck` | #2 gdelt PASS / #5 trends RATE_LIMITED_CONFIRMED |
| trend_fallback_enrichment_audit_20260613_102354.jsonl | 7997B | E414BD37B0B85FCE | `ingestion.runners.run_trend_fallback_enrichment_audit --region KR` | #5 fallback chain (related 19/collected 5/body 1) |
| runner_orchestration_readiness_20260613_102603.jsonl | 6702B | 64AD5551416C79A6 | `ingestion.runners.run_runner_orchestration_readiness` | 오케스트레이션 readiness 13/13 (docs/10 PHASE7) |

> size/sha256은 위 timestamp 파일 기준 스냅샷이다. runner 재실행 시 새 `<ts>` 파일이 생성되며 hash는 입력 데이터에 따라 달라진다(재현은 "동일 구조·동일 계약" 기준).

## 3. 대표 본문/DOM/screenshot evidence (커밋 제외, 경로만 기록)

| evidence | 경로(대표) | size | 생성 경로 | checklist |
|---|---|---|---|---|
| GDELT 본문 | `extracted_text/gdelt/20260531_193033_phase3_gdelt_01e0cdf9_httpx_mobile_ua.txt` | 520B | conditional/external_recheck runner의 extract_body cascade | #2 |
| Trends Explore 429 DOM | `rendered_dom/google_trends_explore/` (최신 캡처, 정품 429/robot 페이지) | 변동 | external_recheck / trend_fallback explore_status_row의 Playwright probe | #5 |
| fallback 본문 | `extracted_text/<source>/` (serper 결과 article 1건 trafilatura extracted) | 변동 | run_trend_fallback_enrichment_audit Stage C | #5 |
| selector 본문 | `extracted_text/dcinside/` (Route2 본문 2건) | 변동 | run_playwright_selector_sources_audit | #8 |

대표 디렉토리 규모(커밋 제외): `raw_payload/` 787 · `rendered_dom/` 132 · `screenshots/` 64 · `extracted_text/` 52 · `raw_signal/` 38.

## 4. 재현 절차 요약

1. repo root에서 venv 활성(`.\.venv\Scripts\python.exe`).
2. 위 §2 runner를 재실행 → `outputs/jsonl/`·`reports/`·관련 `raw_*`/`rendered_dom`/`extracted_text` artifact 재생성.
3. rate-limit 영속 검증이 필요하면 `INGESTION_RATE_LIMIT_BACKEND=local_file` 설정(각 audit runner는 `force_local_file_backend`로 자동 처리).
4. google_trends_explore는 optional이며 429면 fallback chain으로 대체된다(우회 금지). 자세한 정책은 `rate_limit_evidence.md §5`.

연결: `IMPLEMENTATION_TRACE_FINAL.md §8(Artifact map)` → 본 매니페스트, `docs/ingestion/70_source_status_master.md`.
