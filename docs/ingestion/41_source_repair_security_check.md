# 41 — Source Repair Round: Security Pre-Check

**날짜**: 2026-06-03  
**단계**: Step 0 (read-only, 최우선)

---

## 보안 스캔 결과

### rg 패턴 스캔 (ingestion/outputs)

```
rg -i "EIA_API_KEY|api_key=|Authorization|Bearer|token|CLIENT_SECRET|PRODUCT_HUNT_ACCESS_TOKEN|OPENAI_API_KEY" ingestion/outputs
```

**결과**: 스캔 대상 경로에 실키값 패턴 없음.  
- `ingestion/outputs/` 내 저장 파일들은 `_sanitize_response()` 처리를 통해 키값이 `***REDACTED***`로 치환됨.
- `Bearer ` 문자열이 포함된 파일 존재 시 확인 필요하나, 현재 기존 artifact에서 발견되지 않음.

### check_env_hygiene 결과

```
[AMBIGUOUS_ALIAS] CLIENT_ID → NAVER_CLIENT_ID로 교체 권장
[AMBIGUOUS_ALIAS] CLIENT_SECRET → NAVER_CLIENT_SECRET으로 교체 권장
[KEY_NOT_IN_EXAMPLE] CLIENT_ID, CLIENT_SECRET, CSE_CX, ECOS_API_KEY, GOOGLE_API_KEY
  → .env에 있으나 .env.example에 미기재 (alias 키)
```

**분류**: PASS (실키 노출 없음, alias warning만 존재)

- `AMBIGUOUS_ALIAS`: 운영상 주의사항이나 보안 위반 아님. NAVER_CLIENT_ID를 직접 사용하도록 마이그레이션 권장.
- `KEY_NOT_IN_EXAMPLE`: alias 키이므로 .env.example에 canonical 키명 + 주석으로 alias 안내됨. GOOGLE_API_KEY, CSE_CX는 이번 라운드에서 .env.example에 주석 추가 완료.

### git status 스냅샷

- 수정 대상 파일들 모두 워킹 트리에 스테이징되지 않은 상태(변경 중)
- 하드코딩 키 없음
- `.env`는 `.gitignore`에 의해 추적 제외 확인

## 결론

**SECURITY_PASS** — 실키 미노출, 구조적 보안 결함 없음.  
alias warning 2건은 운영 권장사항이며 이번 라운드 대상 외.
