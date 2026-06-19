# ENV_KEYS — 환경변수 키 단일 카탈로그 (단일 출처)

> **상태중립 참조 (2026-06-19 신설).** 기존 4벌 중복(`_CANONICAL/02`·`5_REFERENCE/08`·`COMPATIBILITY_NOTES`·`DEPLOYMENT`)의 env-key 표를 이 문서 1벌로 통합한다.
>
> **권위 계층:**
> 1. **키 *이름*·선언 구조·"empty = DEFAULT" 계약의 단일 출처 = 루트 `.env.example`** (실값 없는 안전 템플릿). 키를 추가/삭제/개명하면 `.env.example`을 먼저 고친다.
> 2. **기본값·용도·컨테이너 매핑의 문서 카탈로그 = 이 문서.**
> 3. 실제 `.env`(추적 제외)는 **절대 열람·커밋·로그 금지** — 길이/존재만 보고(CLAUDE.md §3).
>
> 코드는 키를 `os.getenv` / `pydantic-settings`(`backend/app/core/config.py`) 로만 읽으며, **빈 문자열 키는 제거되어 기본값을 사용**한다(env 파서 계약, ADR #12).

---

## 1. 인프라 · 런타임 키 (docker-compose.dev.yml / backend)

| 키 | 기본값(dev) | 용도 |
|---|---|---|
| `LANGSMITH_TRACING` | `false` | LangSmith 추적 opt-in (`true`로 켬) |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com` | LangSmith 엔드포인트 |
| `LANGSMITH_API_KEY` | (빈값) | LangSmith 발급 키 — 로깅 금지(길이만) |
| `LANGSMITH_PROJECT` | (빈값) | 프로젝트명 |
| `OPENAI_API_KEY` | (빈값) | OpenAI 키 — `LLM_PROVIDER=openai`일 때 필수 |
| `MILVUS_HOST` / `MILVUS_PORT` | `milvus-standalone` / `19530` | 벡터 스토어 연결(컨테이너 내부명) |
| `MILVUS_COLLECTION` | `event_embeddings` | Milvus 컬렉션명 |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker / 캐시 |
| `DATABASE_URL` | `postgresql+asyncpg://event_user:event_pass@postgres:5432/event_intel` | Postgres (asyncpg driver) |
| `LLM_PROVIDER` | `mock` | `mock` \| `openai` — 노드 LLM 디스패치 |
| `LLM_MODEL` / `LLM_TIMEOUT_SEC` / `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` | `gpt-4o-mini` / — | LLM 호출 파라미터 |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `mock` / `text-embedding-3-small` / `1536` | 임베딩 프로바이더 |
| `OPENSEARCH_HOST` / `OPENSEARCH_PORT` / `OPENSEARCH_EVENT_INDEX` | `opensearch` / `9200` / `event_cards` | 키워드 검색 |
| `APP_ENV` | `dev` | `dev`/`test` = admin 무인증 허용 / `production`/`staging` = `ADMIN_API_TOKEN` 필수(fail-closed) |
| `ADMIN_API_TOKEN` | (빈값) | admin/internal 엔드포인트 토큰. dev 빈값=bypass(시작 시 WARNING) |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | 브라우저용 백엔드 base URL(build-time inline) |
| `INTERNAL_API_BASE_URL` | `http://backend:8000` | Next.js 서버사이드→백엔드 (컨테이너 간) |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | 백엔드 CORS 허용 origin (콤마구분). prod는 실도메인 추가 필요 |

> ⚠️ **개명 주의:** 키는 `CORS_ALLOW_ORIGINS`다. 구 문서의 `CORS_ORIGINS`는 **오타/stale** — 코드·`.env.example` 기준은 `CORS_ALLOW_ORIGINS`.

기타 운영 스크립트 키(`RSS_*`, `RECONCILER_*`, `REINDEX_*`, `BACKEND_INTERNAL_URL`, `RUN_*_SMOKE`)는 `.env.example`의 해당 STEP 블록 참조.

## 2. 수집(Ingestion) 소스 API 키

전체 목록·발급처·무료 쿼터·alias/DEPRECATED 매핑은 **`.env.example`의 "Ingestion Layer" 섹션이 단일 출처**다(키가 많고 자주 추가되므로 여기서 중복 기재하지 않는다). 요약:

- **정식 키명 vs alias:** 일부 키는 alias 허용(`env_loader.py`의 `_ALIASES`가 해석). 예: `NAVER_CLIENT_ID`(정식) ← `CLIENT_ID`(deprecated), `BOK_ECOS_API_KEY` ← `ECOS_API_KEY`, `PRODUCT_HUNT_ACCESS_TOKEN` ← `PRODUCT_HUNT_API_KEY`, `CULTURE_INFO_API_KEY` ← `CULTURE_INFO_KEY`, `GOOGLE_CUSTOM_SEARCH_API_KEY/CX` ← `GOOGLE_API_KEY/CSE_CX`. **신규 작성은 정식 키명만 사용.**
- **빈 값 = 미설정**: 해당 소스는 비활성/스킵(BLOCKED 아님, WARNING). `implemented:false` Phase 4 후보 키는 미배포.
- **파일 경로형:** `GOOGLE_APPLICATION_CREDENTIALS`는 경로만 — `env_loader`는 존재만 확인, 내용 미열람.

---

## 참조
- 키 선언 템플릿: 루트 `.env.example`
- 파서 계약: `backend/app/core/config.py` + ADR #12 (`docs/_DECISIONS/2026-06.md`)
- env 위생 검사: `ingestion/tools/check_env_hygiene.py`
