# Deployment Guide — Event Intelligence

## 로컬 개발 (전체 스택)

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 파일에서 필요한 값 채우기 (최소 OPENAI_API_KEY)

# 2. 전체 스택 빌드 + 기동
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d

# 3. 상태 확인
docker compose -f docker-compose.dev.yml ps

# 4. 브라우저
# http://localhost:3000  — Frontend
# http://localhost:8000  — Backend API
```

## Frontend만 개발 모드로 실행

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

Backend가 localhost:8000에서 실행 중이어야 합니다.

## 개별 서비스 재빌드

```bash
# backend 변경 후
docker compose -f docker-compose.dev.yml build backend
docker compose -f docker-compose.dev.yml up -d backend

# frontend 변경 후
docker compose -f docker-compose.dev.yml build frontend
docker compose -f docker-compose.dev.yml up -d frontend
```

## Frontend 빌드 검증

```bash
cd frontend
npm run typecheck   # TypeScript 0 errors
npm run lint        # ESLint 0 errors
npm run build       # .next/standalone/server.js 생성 확인
npm run test        # node --test 3 pass
```

## compose config 유효성 확인

```bash
docker compose -f docker-compose.dev.yml config --quiet
```

## Smoke Test

### 자동 스크립트 (STEP 011)

```bash
bash tests/smoke/smoke.sh
# 6종 curl 검증 (backend health, frontend health, /events, /search, /admin, CORS preflight)
# 전체 통과 시 "OK" 출력
```

### 수동 확인

```bash
# Frontend
curl http://localhost:3000/api/health          # {"status":"ok"}
curl -I http://localhost:3000/events           # 200
curl -I "http://localhost:3000/search?q=test"  # 200
curl -I http://localhost:3000/admin            # 200

# CORS preflight
curl -si -X OPTIONS http://localhost:8000/api/events \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  | grep access-control-allow-origin
# → access-control-allow-origin: http://localhost:3000

# Backend
curl http://localhost:8000/health
curl http://localhost:8000/api/events
```

### 전체 파이프라인 smoke (Scenario A)

```bash
RUN_FULL_PIPELINE_SMOKE=1 LLM_PROVIDER=mock pytest tests/smoke/test_full_pipeline.py -v
# 전체 스택 실행 중일 때만 사용. LLM_PROVIDER=mock 강제 (OpenAI 호출 없음)
```

## 환경 변수 주요 항목

> 전체 키 카탈로그·기본값 단일출처: `5_REFERENCE/ENV_KEYS.md`. 아래는 배포 런북에 직접 관련된 프런트엔드/CORS 변수만.

| 변수 | 용도 |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | 브라우저 → backend URL. dev: `http://localhost:8000`. prod: public domain |
| `INTERNAL_API_BASE_URL` | SSR/Route Handler → backend 내부 URL. compose: `http://backend:8000` |
| `ADMIN_API_TOKEN` | admin endpoint 인증 토큰. 빈값 = dev (인증 생략, WARNING) |
| `CORS_ALLOW_ORIGINS` | backend CORS 허용 origin. 기본 `http://localhost:3000` |

## 포트 바인딩 (STEP 011)

데이터 서비스(postgres/redis/milvus/opensearch)는 `127.0.0.1`에만 바인딩됨 (개발 호스트 외부 노출 차단).
backend(8000), frontend(3000)은 브라우저 접근을 위해 `0.0.0.0` 유지.

## 주의사항

- `NEXT_PUBLIC_API_BASE_URL`은 **빌드 타임**에 inline됨 → Docker build ARG로 주입하거나 기본값 사용.
- `ADMIN_API_TOKEN`은 절대 `NEXT_PUBLIC_*`로 노출 금지. Route Handler proxy를 통해서만 사용.
- prod에서 `CORS_ALLOW_ORIGINS`에 실제 도메인 추가 필요.
- `npm audit fix --force` 절대 사용 금지 (Next.js 9.x downgrade 유발).
