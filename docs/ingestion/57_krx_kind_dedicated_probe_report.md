# 57 — KRX KIND 전용 XHR/네트워크 Probe 보고

## 개요

KRX KIND (`kind.krx.co.kr`) 공시 페이지를 대상으로 Playwright 기반 전용 Probe를 구현하고, XHR/네트워크 캡처를 통해 실제 API endpoint 존재 여부를 탐색한 결과를 기록한다.

---

## 구현 내용

### playwright_browser_tool.py — `open_page(capture_network=True)` 추가

- `page.on("response", ...)` 리스너를 등록하여 POST/XHR/JSON 요청을 캡처
- **관찰만 수행, 우회 없음** — 요청 내용 기록 후 `network_log` 필드에 저장
- `capture_network=True` 파라미터로 선택적 활성화

### run_krx_kind_probe.py — 신규 러너

```
networkidle 대기 → 3초 추가 대기 → 테이블 selector 시도 → 공시 항목 파싱
```

파싱 대상 필드:

| 필드명 | 설명 |
|--------|------|
| `corp_name` | 공시 기업명 |
| `report_title` | 공시 제목 |
| `disclosed_at` | 공시 일시 |
| `detail_url` | 상세 페이지 URL |
| `market_type` | 시장 구분 (KOSPI/KOSDAQ 등) |

---

## 현재 사이트 상태

**`deferred: true`** (playwright_probe_sites.yaml) — `DEFERRED_SERVER_ERROR` 유지

### 원인 분석

- `kind.krx.co.kr` 접속 시 약 1.3KB 오류 페이지 반환
- EUC-KR 인코딩 오류로 title 포함 텍스트 일부 깨짐
- 정상 공시 테이블 렌더링 없음

### 원인 가설

1. 서버 오류 (5xx 계열)
2. JS 기반 테이블 미렌더 (SPA 로딩 실패)
3. 지역 IP 차단 (해외 IP 접속 제한)

---

## XHR 캡처 목적 및 판단 기준

### 발견 시

- 실제 API endpoint 확인 → `krx_kind_api` 소스 분리 검토
- REST API 형태면 `httpx` 직접 호출로 전환 가능

### 미발견 시

- `network_log` 근거로 차단 단계 문서화
- 어느 레이어에서 막혔는지 명시 (DNS / TCP / HTTP / JS 레벨)

---

## 성공/실패 조건

| 조건 | 분류 | 상태 |
|------|------|------|
| 공시 1건 이상 + 필드 3개 이상 파싱 성공 | LIVE_SUCCESS | 미달성 |
| 서버 오류 페이지 반환 + network_log 근거 있음 | DEFERRED_SERVER_ERROR | 현재 상태 |

---

## 다음 단계 (우선순위 순)

1. **공식 데이터포털 API** (`open.krx.co.kr`) — OpenAPI 키 발급 후 REST 직접 호출
2. **모바일 UA 재시도** — 모바일 User-Agent로 접근하여 서버 오류 재현 여부 확인
3. **별도 라운드 분리** — 위 두 방법 모두 실패 시 KRX 라운드로 분리하여 처리
