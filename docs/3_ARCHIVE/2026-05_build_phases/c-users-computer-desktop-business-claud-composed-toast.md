# frontend 독립성 검토 (맥북 분리 작업 안전성)

## Context (왜 이 검토를 하는가)

`frontend/`(Next.js 앱)는 현재 진행 중인 개념이다. 사용자는 이것을 **맥북에서 독립적으로 변경한 뒤 나중에 다시 합쳐도 충돌/문제가 없는지** 확인하고 싶어 한다. 코드는 변경하지 않고 **연결 지점만 전수 조사**했다.

조사 범위: `frontend/src` 전체 + frontend 설정 파일 + 역방향(docker-compose, backend, 루트 빌드/스크립트)까지 양방향. Explore 에이전트 2개 병렬 조사.

---

## 결론: frontend는 코드/파일 레벨에서 완전히 분리되어 있음 → 독립 작업·재병합 안전

**파일시스템·import·타입 레벨에서 frontend 밖을 참조하는 것이 0건.** 따라서 `frontend/`만 떼어 맥북에서 변경 후 다시 합쳐도 **빌드/import/머지 충돌은 발생하지 않는다.**

### 분리되어 있음을 확인한 항목 (조치 불필요)

| 항목 | 결과 | 근거 |
|------|------|------|
| frontend 밖으로 나가는 import (`../../`) | **없음** | 내부 import는 전부 `@/*` 별칭(`tsconfig.json:24-28`) 또는 같은 디렉토리 |
| tsconfig paths 별칭이 frontend 밖을 가리킴 | **없음** | `"@/*": ["./src/*"]` 하나뿐 |
| 공유 타입/스키마 import | **없음** | API 타입 전부 `frontend/src/lib/api/types.ts`에 수기 자체 정의 (openapi 생성·심볼릭 링크·공유 패키지 없음) |
| 루트 package.json / 모노레포 workspace | **없음** | pnpm-workspace·npm workspaces·turbo·lerna·nx 전부 없음. frontend는 자체 package.json 가진 독립 npm 프로젝트 |
| backend가 frontend static 산출물 serve | **없음** | `backend/app/main.py`에 StaticFiles·mount·.next 참조 0건 |
| compose backend → frontend 의존 | **없음** | depends_on은 redis/milvus/postgres/opensearch만. 의존은 frontend → backend 단방향 |
| 공유 볼륨 | **없음** | frontend는 볼륨 마운트 안 함 |
| Dockerfile 빌드 컨텍스트 | **격리됨** | `context: ./frontend` — 루트/backend 파일 접근 불가 |

### 유일한 연결점 = 런타임 계약(HTTP/env). 머지 충돌과 무관, 단 합칠 때 값만 일치하면 됨

frontend ↔ backend는 **단방향 런타임 HTTP 계약**으로만 묶여 있다. 코드 결합이 아니므로 머지 충돌을 일으키지 않지만, 재병합 시 아래 "계약 값"이 어긋나면 **런타임에서** 깨질 수 있다:

1. **API 엔드포인트 8종 + admin** — `frontend/src/lib/api/client.ts`(`/health`, `/api/events`, `/api/events/{id}`, `/api/events/search`, `/api/themes`, `/api/themes/{id}/events`, `/api/sectors`, `/api/sectors/{id}/events`) + `server.ts`(`/api/admin/search/reindex`). backend 라우트 경로·응답 스키마가 바뀌면 어긋남. `types.ts`는 수기라 자동 동기화 안 됨.
2. **환경변수 3종** — `NEXT_PUBLIC_API_BASE_URL`, `INTERNAL_API_BASE_URL`, `ADMIN_API_TOKEN` (`config.ts:1-5`, `server.ts:4`). 주입 위치는 `docker-compose.dev.yml:228-233` + 루트 `.env.example`. `frontend/.env` 파일은 없음.
3. **포트 3000** — backend CORS 기본값 `http://localhost:3000`(`backend/app/core/config.py:37`), `backend/tests/test_cors.py`가 이 값 검증, compose healthcheck. frontend 포트를 바꾸면 CORS·test_cors가 깨짐.
4. **Next.js `output: "standalone"`** (`frontend/next.config.mjs`) + **`/api/health`**(`frontend/src/app/api/health/route.ts`) — docker 빌드·healthcheck가 의존. 없애면 frontend 컨테이너만 영향, backend 무관.

---

## 사용자 질문에 대한 답

- **"연결된 거 없지?"** → 코드/타입/파일 레벨 연결은 **없음(완전 분리)**. frontend 밖을 import하거나 backend 타입을 공유하는 코드 0건.
- **"완전 분리된 task니까 맥북에서 변경하고 추후 합쳐도 문제 없는지?"** → **머지 충돌 없이 안전.** 단, frontend 내부만 건드릴 것. 위 "런타임 계약"(특히 포트 3000·env 3종·API 경로/스키마)을 함께 바꾸면 backend와 값을 맞춰야 한다.

### 맥북 작업 시 권장 (충돌 0 보장)
- `frontend/` 내부 파일만 변경 → 무조건 안전.
- backend의 라우트/응답 스키마를 바꾸면 `frontend/src/lib/api/types.ts`·`client.ts`를 같이 맞출 것 (수기 동기화).
- `docker-compose.dev.yml`의 frontend 서비스 블록(`:221-243`)과 루트 `.env`/`.env.example`의 frontend 변수는 맥북·Windows 양쪽에서 동시에 건드리지 않으면 머지 충돌 없음.

---

## 조치 (구현 작업 아님)
이 작업은 **검토 보고**다. 코드 변경 없음. 위 결론을 사용자에게 전달하는 것으로 종료.
