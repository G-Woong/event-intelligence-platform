# 32 — Playwright Stability Audit

**검증 일시**: 2026-06-03  
**대상**: playwright_probe_sites.yaml 등록 7개 소스

---

## 1. 프레임워크 기능 검증

| 기능 | 구현 상태 | 위치 |
|---|---|---|
| 복수 selector fallback | IMPLEMENTED | playwright_probe.py — selectors.list 순회 |
| source별 wait 전략 | IMPLEMENTED | wait_for / wait_after_ms per site spec |
| 실패 시 screenshot 저장 | IMPLEMENTED | screenshot_logger.py |
| 실패 시 DOM snapshot 저장 | IMPLEMENTED | dom_snapshot 저장 경로 |
| 실패 원인 분류 | IMPLEMENTED | classify_content_blocker() — captcha/login/paywall |
| Playwright 실패 → selenium 후보 | IMPLEMENTED | strategy_selection.select_next_strategy → selenium_rendered_dom |

---

## 2. 소스별 검증 결과

### signal_bz — LIVE_SUCCESS
- **artifact**: raw_signal/signal_bz (304B, 5 keywords)
- **샘플**: "1출구조사 결과 경합과 우세", "2송파구 투표용지 부족 문제"...
- **selector 동작**: `.rank-tex` 매칭 확인
- **봇 차단**: 없음
- **안정성**: STABLE

### eu_press_corner — LIVE_PARTIAL
- **artifact**: raw_signal/eu_press_corner (174B, 1 item)
- **샘플**: "Daily news Jun 2, 2026 12 min read..."
- **문제**: selector `ecl-content-item` 1개만 매칭. URL 필드 비어있음.
- **권장 수정**: selector에 `.ecl-content-block__title a` 또는 `ecl-content-item article` 추가. wait_after_ms 3000 → 5000.

### google_trending_now — LIVE_SUCCESS
- **artifact**: raw_signal/google_trending_now (365B, 10 keywords)
- **샘플**: 배우, 투표, 젠슨 황, mc몽, 이재명...
- **selector 동작**: `.mZ3RIc` 또는 fallback selector 중 하나 동작
- **rate limit 위험**: min_interval 60분 설정됨. Step 1-3 정책(1800s) 추가 적용.
- **안정성**: STABLE with rate limit guard

### dcinside — LIVE_SUCCESS
- **artifact**: raw_signal/dcinside (459B, 3 items) + raw_payload (797KB HTML)
- **샘플**: "쇼츠나 챌린지로 화제성 제대로 챙긴 스타는?", "[디시人터뷰]..."
- **selector 동작**: `tr.ub-content .gall_tit a` 매칭
- **봇 차단**: Cloudflare 없음 (stock 갤러리 공개)
- **안정성**: STABLE

### fmkorea — BLOCKED (DEFERRED)
- **상태**: playwright_probe_sites.yaml `deferred: true`
- **이유**: Cloudflare Turnstile 감지. `/index.php?mid=stock` 접근 시 봇 차단.
- **공개 메인페이지**: httpx로 74KB HTML 수집 가능하나 stock 게시판 콘텐츠 접근 불가.
- **결론**: BLOCKED_BOT_PROTECTION. 우회 금지.

### krx_kind — DEFERRED
- **상태**: playwright_probe_sites.yaml `deferred: true`
- **이유**: `kind.krx.co.kr` 서버 오류 반환. JS 렌더링 필요.
- **재시도 계획**: 다음 라운드 playwright runner로 재접근. 오늘공시 테이블 selector: `table.list tbody tr td.col-1 a`
- **결론**: DEFERRED_SERVER_ERROR.

### google_trends_explore — NOT_TESTED (이번 라운드 probe 미실행)
- **spec 존재**: playwright_probe_sites.yaml 등록됨
- **min_interval**: 120분 (Step 1-3에서 1800s로 보강됨)
- **selector**: `.fe-related-queries-item` 외 2개 fallback
- **결론**: 별도 보고서(doc 33) 참조.

---

## 3. selector/wait 갱신 이력

`configs/playwright_probe_sites.yaml` 변경 사항 없음 (이번 라운드). 권장 변경 사항:

```yaml
# eu_press_corner selector 보강 (권장)
eu_press_corner:
  selectors:
    list:
      - "ecl-content-item .ecl-content-block__title a"   # 추가
      - ".ecl-content-item"
      - "ecl-content-item"
  wait_after_ms: 5000  # 2000 → 5000
```

---

## 4. 종합 평가

| source_id | playwright_status | 데이터 품질 | 안정성 |
|---|---|---|---|
| signal_bz | LIVE_SUCCESS | GOOD | STABLE |
| eu_press_corner | LIVE_PARTIAL | PARTIAL | 개선 필요 |
| google_trending_now | LIVE_SUCCESS | GOOD | STABLE (rate limit 주의) |
| dcinside | LIVE_SUCCESS | USABLE | STABLE |
| fmkorea | BLOCKED | BAD | 우회 불가 |
| krx_kind | DEFERRED | — | 다음 라운드 |
| google_trends_explore | 미실행 | — | doc 33 참조 |
