# 03. MCP and Tooling Survey — MCP/Tool 후보 조사표

> **생성일**: 2026-06-13
> **목적**: 이 프로젝트에 필요한 MCP/Tool 후보 전수 조사. 즉시 도입/보류/거절 판정.
> **중요 전제**: `enableAllProjectMcpServers: false` (현재 설정). MCP는 신중하게 최소 도입.
> **이번 턴 제약**: 조사 및 판정만. 실제 MCP 설치/config 수정 없음.

---

## MCP란? (배경 설명)

MCP(Model Context Protocol)는 Claude Code가 외부 도구(파일시스템, DB, 검색, 브라우저 등)와 통신하는 표준 프로토콜이다.
- **stdio MCP**: 로컬 프로세스와 stdin/stdout으로 통신. 설치 쉬우나 로컬 실행 환경 필요.
- **HTTP MCP**: 원격 서버와 HTTP로 통신. 추가 네트워크 신뢰가 필요하나 확장성 높음.

**보안 위험 (중요)**:
- **Tool Poisoning**: MCP 서버가 악의적 지시를 tool description에 숨겨 Claude를 조작할 수 있다.
- **Prompt Injection**: MCP가 읽은 외부 콘텐츠에 포함된 지시가 Claude의 동작을 변경할 수 있다.
- **Scope Creep**: 파일시스템/코드실행 MCP는 권한 범위가 너무 넓을 수 있다.

**이 프로젝트 원칙**: Python runner가 이미 대부분의 수집 기능을 제공하므로 MCP 필요성이 낮다. 추가 가치가 명확한 경우만 도입.

---

## MCP 후보 평가표

### 범주 1: 파일시스템 MCP

| 항목 | 내용 |
|------|------|
| **name** | filesystem MCP (예: @modelcontextprotocol/server-filesystem) |
| **category** | 파일시스템 접근 |
| **purpose** | 프로젝트 파일 읽기/쓰기 자동화 |
| **integration_type** | MCP (stdio) |
| **credentials** | 없음 |
| **security_risk** | **HIGH** — 파일 삭제/덮어쓰기 권한 포함 가능. CLAUDE.md의 rm/Remove-Item 금지 정책과 충돌 위험 |
| **data_risk** | HIGH — .env 파일 읽기 가능 |
| **operational_risk** | MEDIUM |
| **cost_risk** | 없음 |
| **immediate_adoption** | **NO** |
| **reason** | Read/Write/Edit tool이 이미 충분함. 추가 MCP 없이도 모든 파일 작업 가능. 보안 리스크 대비 이득 없음. |
| **rollback** | MCP config에서 제거 |

---

### 범주 2: Git/GitHub MCP

| 항목 | 내용 |
|------|------|
| **name** | GitHub MCP (공식: @modelcontextprotocol/server-github) |
| **category** | Git/GitHub 연동 |
| **purpose** | PR 생성, issue 조회, commit 조회 |
| **integration_type** | MCP (stdio) |
| **credentials** | GITHUB_TOKEN (Personal Access Token) |
| **security_risk** | **HIGH** — git push 권한 포함 시 CLAUDE.md 금지 정책 위반. 토큰 노출 위험. |
| **data_risk** | MEDIUM |
| **operational_risk** | HIGH — 의도치 않은 push/PR 생성 |
| **cost_risk** | 없음 |
| **immediate_adoption** | **DEFER** |
| **reason** | Bash(git ...) 명령으로 이미 git 작업 가능. GitHub API 직접 호출도 가능. push 권한 없이 read-only로 제한된 구성이 필요하나 현재 프로젝트에서 당장 필요 없음. |
| **verify** | VERIFY BEFORE APPLY — git push deny 정책과 충돌하지 않도록 readonly 토큰으로 제한 필수 |

---

### 범주 3: Postgres/SQLite MCP

| 항목 | 내용 |
|------|------|
| **name** | Postgres MCP (예: @modelcontextprotocol/server-postgres) |
| **category** | DB 연동 |
| **purpose** | event queue 저장소 조회, 수집 상태 조회 |
| **integration_type** | MCP (stdio) |
| **credentials** | DB connection string (.env의 DB_URL) |
| **security_risk** | **MEDIUM** — SQL injection 가능성, 민감 데이터 노출 |
| **data_risk** | HIGH — 수집된 모든 이벤트 데이터 접근 |
| **operational_risk** | MEDIUM |
| **cost_risk** | 없음 |
| **immediate_adoption** | **DEFER** |
| **reason** | Postgres는 plans/012 오케스트레이션 단계에서 도입 예정. 현재 DB 없음. 도입 시 read-only 쿼리만 허용하는 권한 제한 필요. |

---

### 범주 4: Redis MCP

| 항목 | 내용 |
|------|------|
| **name** | Redis MCP (커뮤니티 도구) |
| **category** | Redis 상태 조회 |
| **purpose** | rate_limit_cache 상태 조회, Celery task 모니터링 |
| **integration_type** | MCP (stdio) |
| **credentials** | REDIS_URL (.env) |
| **security_risk** | MEDIUM — Redis FLUSHALL 등 위험 명령 가능 |
| **immediate_adoption** | **DEFER** |
| **reason** | 현재 rate_limit_policy.yaml backend: memory. Redis 전환(plans/012) 후 필요 시 도입. 직접 Python 스크립트로도 충분. |

---

### 범주 5: Browser/Search MCP

| 항목 | 내용 |
|------|------|
| **name** | Playwright MCP / Puppeteer MCP |
| **category** | 브라우저 자동화 |
| **purpose** | Playwright probe 자동화 |
| **integration_type** | MCP (stdio) |
| **credentials** | 없음 |
| **security_risk** | **HIGH** — 브라우저 세션 탈취, 인증 정보 노출 가능 |
| **data_risk** | HIGH |
| **immediate_adoption** | **NO** |
| **reason** | 이미 `ingestion/probes/playwright_probe.py`가 구현 완료. `ingestion/runners/run_playwright_probe.py`로 CLI 실행 가능. MCP 추가 없이 충분. 보안 리스크가 이득보다 큼. |

---

### 범주 6: Web Fetch/RSS MCP

| 항목 | 내용 |
|------|------|
| **name** | Fetch MCP (공식: @modelcontextprotocol/server-fetch) |
| **category** | HTTP fetch |
| **purpose** | 웹 페이지 내용 직접 가져오기 |
| **integration_type** | MCP (stdio) |
| **credentials** | 없음 |
| **security_risk** | MEDIUM — 내부 네트워크 SSRF 가능성 |
| **immediate_adoption** | **DEFER** |
| **reason** | WebFetch tool이 이미 허용 도메인 제한으로 안전하게 사용 중. 별도 MCP 불필요. 필요 시 허용 도메인 추가로 대응 가능. |

---

### 범주 7: Vector DB MCP

| 항목 | 내용 |
|------|------|
| **name** | Milvus MCP / Pinecone MCP |
| **category** | 벡터 DB |
| **purpose** | 이벤트 임베딩 검색, 중복 감지 |
| **integration_type** | MCP (stdio 또는 HTTP) |
| **credentials** | Milvus 연결 정보 |
| **security_risk** | MEDIUM |
| **immediate_adoption** | **DEFER** |
| **reason** | 오케스트레이션(plans/012) 이후 단계. Milvus는 docker-compose.dev.yml에 포함 예정. 현재 벡터 검색 기능 미구현. |

---

### 범주 8: 코드 실행 MCP

| 항목 | 내용 |
|------|------|
| **name** | Code Execution MCP (예: jupyter/IPython kernel) |
| **category** | 로컬 코드 실행 |
| **purpose** | Python 코드 직접 실행 |
| **security_risk** | **CRITICAL** — 임의 코드 실행. sandbox 없음 |
| **immediate_adoption** | **NO** |
| **reason** | Bash tool 이미 사용 가능. 별도 코드 실행 MCP 불필요. 보안 위험이 치명적으로 큼. |

---

### 범주 9: 모니터링/로깅 MCP

| 항목 | 내용 |
|------|------|
| **name** | LangSmith MCP (커뮤니티) |
| **category** | LLM 관측 |
| **purpose** | LangGraph/LangSmith trace 조회 |
| **integration_type** | HTTP MCP |
| **credentials** | LANGSMITH_API_KEY (.env 존재) |
| **immediate_adoption** | **DEFER** |
| **reason** | LangGraph 오케스트레이션 구현 후 필요. 현재 LangGraph 미구현. LANGSMITH_API_KEY는 .env에 있으나 값 확인 불필요. |

---

### 범주 10: Semantic Scholar MCP (현재 사용 중)

| 항목 | 내용 |
|------|------|
| **name** | mcp__semantic-scholar (현재 settings.json allow 목록에 있음) |
| **category** | 학술 검색 |
| **purpose** | 논문 검색 (연구 지원) |
| **현재 상태** | 이미 허용 목록에 있음 (`mcp__semantic-scholar__search_paper`) |
| **immediate_adoption** | **ALREADY_ACTIVE** |
| **reason** | 연구 지원 목적. 보안 리스크 낮음. 현재 상태 유지. |

---

## 직접 Python Tool (MCP 대신 사용 권장)

이 프로젝트의 대부분 기능은 이미 Python runner로 구현되어 있다. MCP보다 직접 Python 도구 사용이 낫다.

| 기능 | Python 도구 | 이유 |
|------|------------|------|
| 소스 수집 | `ingestion/runners/run_collection_probe.py` | 구현 완료, rate-limit 통합 |
| body 추출 | `ingestion/tools/*_extractor.py` | 이미 cascade 구현 |
| secret scan | `ingestion/tools/scan_secrets.py` | 프로젝트 맞춤 규칙 |
| rate-limit 상태 | `ingestion/outputs/state/rate_limit_cache.json` | 직접 읽기 |
| feed 탐색 | `ingestion/tools/feed_discovery.py` | 구현 완료 |
| URL 정규화 | `ingestion/tools/url_resolver.py` | 구현 완료 |

---

## 즉시 도입/보류/거절 요약

| 판정 | 후보 | 이유 |
|------|------|------|
| **ALREADY_ACTIVE** | Semantic Scholar MCP | 이미 허용 목록 |
| **NO (거절)** | Filesystem MCP | 기존 도구 충분, 보안 위험 |
| **NO (거절)** | Browser MCP (Playwright) | Python runner 구현 완료, 보안 위험 |
| **NO (거절)** | Code Execution MCP | CRITICAL 보안 위험 |
| **DEFER** | GitHub MCP | push 금지 정책과 충돌, readonly 제한 후 재검토 |
| **DEFER** | Postgres MCP | DB 미도입 (plans/012 이후) |
| **DEFER** | Redis MCP | Redis 미도입 (plans/012 이후) |
| **DEFER** | Web Fetch MCP | WebFetch tool로 충분 |
| **DEFER** | Vector DB MCP | 오케스트레이션 이후 단계 |
| **DEFER** | LangSmith MCP | LangGraph 미구현 |

---

## MCP 도입 시 공통 보안 요구사항

모든 MCP 도입 시 반드시 준수:

```
1. Least Privilege: read-only 권한만 허용 (쓰기/삭제 금지)
2. Domain 제한: HTTP MCP는 허용 도메인 명시
3. Tool Poisoning 방어: MCP description의 의심스러운 지시 사전 검토
4. Secret 노출 방지: .env 파일 접근 MCP 금지
5. deny 목록 우선: settings.json deny 목록에 해당 도구 등록
6. 실험적 도구 표시: 프로덕션 전에 충분한 테스트
7. 롤백 계획: MCP 제거 후 기능 대체 방안 사전 확보
```

---

## MCP config proposed diff (보류 예시 — VERIFY BEFORE APPLY)

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# PROJECT DOES NOT CURRENTLY HAVE THIS FILE
# CREATE IN NEXT TURN ONLY after confirming MCP adoption decision
diff --git a/.claude/mcp_config.json b/.claude/mcp_config.json
new file mode 100644
--- /dev/null
+++ b/.claude/mcp_config.json
@@ -0,0 +1,15 @@
+{
+  "mcpServers": {
+    "semantic-scholar": {
+      "command": "npx",
+      "args": ["-y", "@modelcontextprotocol/server-semantic-scholar"],
+      "env": {}
+    }
+  }
+}
+
+// 보류 항목 (DEFER — 다음 단계에서 검토):
+// - github: readonly 토큰으로 제한 후 재검토
+// - postgres: plans/012 Celery/LangGraph 이후
+// - redis: plans/012 Redis 전환 이후
+// - milvus: 벡터 검색 기능 구현 이후
```

> **VERIFY**: MCP config 파일 경로와 형식은 Claude Code 버전에 따라 다를 수 있음. 공식 docs 확인 필요.
