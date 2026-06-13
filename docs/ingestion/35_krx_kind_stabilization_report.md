# 35 — KRX KIND Stabilization Report

**대상**: krx_kind (한국거래소 KIND 공시)  
**중요도**: 공식 증거(official_evidence) tier1, 사건 인텔리전스 핵심 소스

---

## 1. 현황

| 항목 | 내용 |
|---|---|
| base_url | https://kind.krx.co.kr/disclosure/todaydisclosure.do |
| layer | official_evidence |
| evidence_level | tier1 |
| known_blockers | js_heavy, dynamic_search |
| playwright_probe_sites.yaml | `deferred: true` |
| deferred_reason | "SERVER_ERROR: kind.krx.co.kr returned error page on 2026-06-03" |

---

## 2. 접근 시도 이력

### 이전 라운드
- playwright probe 실행 → kind.krx.co.kr 서버 오류 반환
- 단순 HTTP GET으로는 공시 데이터 접근 불가 (JS 렌더링 필요)
- 공시 검색 인터페이스는 JS 동적 렌더링으로 구성됨

### 현재 라운드 (재시도 미실행)
- `deferred: true` 설정으로 이번 라운드 probe 미실행
- 서버 안정 여부 미확인

---

## 3. JS 렌더링 요구사항

KIND 공시 사이트는:
- 페이지 로드 후 XHR/Fetch로 공시 목록 동적 로딩
- JS 실행 없이는 빈 `tbody` 반환
- Playwright `wait_for_selector` + `wait_after_ms` 필요

**playwright spec (현재)**:
```yaml
krx_kind:
  selectors:
    list:
      - "table.list tbody tr td.col-1 a"
      - "table.list tbody tr"
      - ".tblList tbody tr td a"
  search_strategy: page_load_wait_js
  wait_after_ms: 2000
```

---

## 4. 단계 분리 계획 (다음 라운드)

1. **Phase A**: `kind.krx.co.kr` 기본 접근 확인 (서버 오류 여부)
2. **Phase B**: playwright wait_after_ms 3000~5000 + `networkidle` wait 시도
3. **Phase C**: 테이블 데이터 추출 검증
4. **Phase D**: 검색 기능 테스트 (JS form submit)

---

## 5. 결론

| 항목 | 결정 |
|---|---|
| 현재 상태 | DEFERRED_SERVER_ERROR |
| 다음 라운드 | playwright runner로 재접근 (서버 안정 확인 후) |
| 수집 목표 | 오늘공시 목록 (corp_name, report_nm, disclosed_at) |
| 우선순위 | P1 (tier1 공식 소스) |
| 대안 | 없음 (KIND 외 국내 공시 공개 API 없음) |

**다음 라운드 실행 명령**:
```
python -m ingestion.runners.run_playwright_probe --site krx_kind --max-items 10
```
