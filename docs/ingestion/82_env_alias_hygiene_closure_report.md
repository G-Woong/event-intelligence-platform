# 82. Env Alias Hygiene Closure 보고서 (RISK 12-9)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

`check_env_hygiene.py`의 AMBIGUOUS_ALIAS 탐지가 CLIENT_ID/CLIENT_SECRET 2개 하드코딩에
그쳐, `env_loader._ALIASES`에 등록된 나머지 legacy 이름(ECOS_API_KEY, GOOGLE_API_KEY,
CSE_CX, CULTURE_INFO_KEY, PRODUCT_HUNT_API_KEY)은 탐지되지 않았다. 또한 canonical/legacy
둘 다 설정됐는데 값이 다른 위험 상황과 빈 값(KEY=)을 잡지 못했다.

## 2. 변경 사항

### `ingestion/tools/check_env_hygiene.py`

- `_legacy_alias_map()`: `env_loader._ALIASES` **전체**에서 legacy→canonical 매핑 도출
  (하드코딩 제거). _ALIASES에 alias가 추가되면 hygiene 도구가 자동 추적.
- `AMBIGUOUS_ALIAS`: 모든 legacy alias 라인에 경고 + **"기능에는 영향 없음"** 명시
  (env_loader가 자동 해석하므로 동작은 정상 — 위생 문제일 뿐).
- 신규 `ALIAS_VALUE_MISMATCH`: canonical·legacy 둘 다 존재하고 값이 다름 — **메모리 내
  비교만 수행, 리포트에는 키 NAME만** (값 비노출, 테스트로 가드). 런타임에는 canonical이
  우선하므로 legacy 라인 제거/동기화 안내.
- 신규 `EMPTY_VALUE`: `KEY=` (값 없음) 플래그.

### `.env.example`

- legacy alias 라인마다 `# DEPRECATED — use <canonical>` 주석.
- CULTURE_INFO 키 정정: `_ALIASES` 기준 canonical은 `CULTURE_INFO_API_KEY`이며 기존
  example 주석이 반대로 적혀 있었음 → canonical 라인 추가 + legacy 라인 DEPRECATED 표기.
- **`.env` 자체는 수정하지 않음** (사용자 액션으로 유지).

## 3. 실측 결과 (현재 .env)

```
[AMBIGUOUS_ALIAS] GOOGLE_API_KEY → use GOOGLE_CUSTOM_SEARCH_API_KEY
[AMBIGUOUS_ALIAS] CSE_CX → use GOOGLE_CUSTOM_SEARCH_CX
[AMBIGUOUS_ALIAS] ECOS_API_KEY → use BOK_ECOS_API_KEY
[AMBIGUOUS_ALIAS] CULTURE_INFO_KEY → use CULTURE_INFO_API_KEY
[AMBIGUOUS_ALIAS] CLIENT_ID → use NAVER_CLIENT_ID
[AMBIGUOUS_ALIAS] CLIENT_SECRET → use NAVER_CLIENT_SECRET
```

- legacy alias 6개 사용 중 — **기능에는 영향 없음** (alias 해석 정상 동작).
- `ALIAS_VALUE_MISMATCH` 0건 — 값 충돌 없음.
- 값은 어떤 출력에도 포함되지 않음.

## 4. 마이그레이션 가이드 (사용자 액션 — 선택)

기능 영향이 없으므로 강제는 아니나, 위생을 위해 `.env`에서:

1. legacy 키 라인의 키 이름을 canonical로 교체 (값은 그대로):
   `CLIENT_ID=...` → `NAVER_CLIENT_ID=...` 등 위 6개.
2. canonical 라인이 이미 있으면 legacy 라인 삭제.
3. 검증: `python -m ingestion.tools.check_env_hygiene` → AMBIGUOUS_ALIAS 0건 확인.

`_ALIASES` 해석 로직은 하위 호환을 위해 유지된다 — legacy 키가 남아 있어도 수집은 정상.

## 5. 검증

`ingestion/tests/unit/test_env_alias_precedence.py` — **8 passed**:
canonical 우선, legacy 단독 동작, env_status alias 해석, _ALIASES 전체 커버(map +
전 alias 플래그), MISMATCH 시 값 미포함(boolean 비교), 값 동일 시 무경고, EMPTY_VALUE.
