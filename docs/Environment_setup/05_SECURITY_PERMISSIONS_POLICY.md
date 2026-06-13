# 05. Security and Permissions Policy

> **생성일**: 2026-06-13
> **목적**: Claude Code 권한 정책, MCP 허용 범위, 에이전트별 tool allowlist, .env 보호, no bypass 정책.
> **이번 턴 제약**: 정책 문서만. 실제 settings.json 수정 없음.
> **근거**: `.claude/settings.json` 실측 + CLAUDE.md 운영 제약 + docs/Implementation_Instructions/README.md §운영 제약

---

## 1. 현재 권한 구성 (`.claude/settings.json` 실측)

### 1.1 허용(allow) 목록 현재 상태

```json
"allow": [
  "PowerShell(*)",          // 전체 PowerShell 허용 ← 범위가 넓음
  "Bash(*)",               // 전체 Bash 허용 ← 범위가 넓음
  // + 다수의 PowerShell cmdlet 별도 허용
  "WebSearch",
  "WebFetch(domain:github.com)",
  "WebFetch(domain:raw.githubusercontent.com)",
  "WebFetch(domain:api.github.com)",
  "WebFetch(domain:docs.anthropic.com)",
  "WebFetch(domain:docs.claude.com)",
  "WebFetch(domain:docs.astral.sh)",
  "WebFetch(domain:arxiv.org)",
  "WebFetch(domain:api.semanticscholar.org)",
  "WebFetch(domain:www.semanticscholar.org)",
  "mcp__semantic-scholar__search_paper",
  "Skill(update-config)"
]
```

**평가**: `PowerShell(*)`, `Bash(*)` 전역 허용은 편의상 필요하나 보안 취약점이다.
deny 목록이 이를 보완하고 있으나, 더 세밀한 제어가 이상적.

### 1.2 금지(deny) 목록 현재 상태

```json
"deny": [
  "Bash(git push)",
  "Bash(git push *)",
  "Bash(rm *)",
  "Bash(rm -rf *)",
  "Bash(del *)",
  "Bash(erase *)",
  "Bash(rmdir *)",
  "PowerShell(Remove-Item *)",
  "PowerShell(rm *)",
  "PowerShell(del *)",
  "PowerShell(rmdir *)",
  "PowerShell(erase *)",
  "Bash(git reset --hard)",
  "Bash(git reset --hard *)",
  "Bash(git clean -fdx)",
  "Bash(git clean -fdx *)"
]
```

**평가**: 핵심 파괴적 명령이 차단되어 있음. 양호.

---

## 2. 권한 강화 제안 (proposed diff)

### 2.1 WebFetch 허용 도메인 확장 제안

현재 누락된 유용한 도메인:

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# settings.json allow 섹션에 추가
+      "WebFetch(domain:modelcontextprotocol.io)",
+      "WebFetch(domain:pypi.org)",
+      "WebFetch(domain:docs.celeryq.dev)",
+      "WebFetch(domain:docs.langchain.com)",
+      "WebFetch(domain:python.langchain.com)",
+      "WebFetch(domain:blog.gdeltproject.org)",    // 이미 settings.local.json에 있음
```

### 2.2 hooks 기반 forbidden-command guard (04 문서 참조)

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# settings.json에 hooks 섹션 추가 (스키마 확인 후 적용)
+  "hooks": {
+    "PreToolUse": [
+      {
+        "matcher": "Bash|PowerShell",
+        "hooks": [
+          {
+            "type": "command",
+            "command": "PowerShell -Command \"$input = $env:CLAUDE_TOOL_INPUT; $forbidden = @('docker system prune', 'docker volume rm', 'DROP TABLE', 'TRUNCATE TABLE', 'kubectl delete'); foreach ($f in $forbidden) { if ($input -like \"*$f*\") { Write-Error \"FORBIDDEN: $f\"; exit 1 } }\""
+          }
+        ]
+      }
+    ]
+  }
```

---

## 3. 에이전트별 Tool Allowlist

에이전트 파일의 `tools:` 필드로 제어. 각 에이전트는 필요한 최소 도구만 허용.

| 에이전트 | 허용 도구 | 금지 도구 | 이유 |
|---------|----------|----------|------|
| orchestrator-architect | Read, Grep, Glob | Write, Edit, Bash | 설계 문서만, 코드 수정 없음 |
| source-ingestion-engineer | Read, Grep, Glob, Bash, Write, Edit | git push, rm | 코드 구현 필요 |
| data-quality-auditor | Read, Grep, Glob, Bash | Write, Edit | 읽기·분석 전용 |
| test-validation-agent | Read, Grep, Glob, Bash | Write, Edit | 테스트 실행 전용 |
| adversarial-reality-critic | Read, Grep, Glob | Write, Edit, Bash | 분석 전용 |
| commercialization-strategist | Read, Grep, Glob, WebSearch, WebFetch | Write, Edit, Bash | 외부 조사 허용 |
| legal-safety-compliance-reviewer | Read, Grep, Glob, WebSearch, WebFetch | Write, Edit, Bash | 약관 조사 허용 |
| product-ux-strategist | Read, Grep, Glob | Write, Edit, Bash | 읽기 전용 |
| docs-memory-curator | Read, Grep, Glob, Write, Edit | Bash | docs 수정 전용 |
| security-permission-guardian | Read, Grep, Glob, Bash(읽기) | Write, Edit | 보안 감사 전용 |
| mcp-tooling-researcher | Read, Grep, Glob, WebSearch, WebFetch | Write, Edit, Bash | 연구 전용 |
| business-intelligence-analyst | Read, Grep, Glob, WebSearch, WebFetch | Write, Edit, Bash | 분석 전용 |
| evaluation-benchmark-agent | Read, Grep, Glob, Bash | Write, Edit | 평가 전용 |
| operations-sre-agent | Read, Grep, Glob, Bash | Write, Edit | 운영 모니터링 |
| frontend-integration-agent | Read, Grep, Glob | Write, Edit, Bash | API 계약 읽기 전용 |

---

## 4. .env 키 보호 정책

### 4.1 현재 .env 키 목록 (존재 여부만 — 값 출력 절대 금지)

```
LANGSMITH_TRACING       (관측 활성화)
LANGSMITH_ENDPOINT      (LangSmith API endpoint)
LANGSMITH_API_KEY       (LangSmith 인증)
LANGSMITH_PROJECT       (프로젝트 이름)
OPENAI_API_KEY          (OpenAI LLM)
MILVUS_HOST             (Milvus 벡터 DB)
MILVUS_PORT             (Milvus 포트)
REDIS_URL               (Redis URL)
```

추가로 각 source별 키 (NEWSAPI_API_KEY, SERPER_API_KEY, TAVILY_API_KEY 등 다수 — 값 확인 금지)

### 4.2 .env 보호 규칙

```
1. 출력 금지: 어떤 로그/문서/응답에도 실제 키 값 포함 금지
2. 존재 확인: Test-Path .env 으로 파일 존재만 확인
3. 키 이름만: os.getenv("KEY_NAME") 형식으로만 참조
4. 길이 확인: len(os.getenv("KEY")) > 0 으로 설정 여부 확인
5. 마스킹: 에러 메시지에 키 값 포함되지 않도록 마스킹 처리
6. gitignore: .env는 .gitignore에 포함 (커밋 금지)
```

### 4.3 secret scan 정책

```
도구: ingestion/tools/scan_secrets.py
실행: python -m ingestion.tools.scan_secrets --paths .
성공: verdict=PASS, WARNING 0
실패: WARNING > 0 또는 실제 leak 감지 → 즉시 수정

False Positive 처리 규칙 (TRACE_FINAL §9 기준):
- openai_key URL slug (좁은 엔트로피 판별) → 오탐
- access_token = func(...) 코드참조 → 오탐 허용 (따옴표 리터럴은 WARNING)
- 테스트 fixture # pragma: allowlist secret → Layer1만 면제
- sk-* 전체 무시 금지
- Layer2 BLOCKED (.env 값 누출) → pragma로도 미억제
```

---

## 5. MCP 권한 정책

### 5.1 현재 MCP 상태

```
enableAllProjectMcpServers: false   ← 전역 비활성화 (안전)
허용된 MCP tool: mcp__semantic-scholar__search_paper (settings.json allow 목록)
등록된 MCP 서버: 없음 (mcp_config.json 미존재)
```

### 5.2 MCP 추가 시 필수 조건

```
1. Least Privilege: read-only 권한만
2. 도메인 제한: HTTP MCP는 특정 도메인만
3. Tool Poisoning 방어: MCP description 사전 검토
4. Secret 격리: .env 파일 접근 MCP 금지
5. deny 목록: 위험 도구는 deny 명시
6. 롤백 계획: 제거 후 기능 대체 방안 사전 확보
7. 테스트 먼저: staging 환경에서 검증 후 프로덕션 적용
```

---

## 6. 소스별 접근 보안 정책

### 6.1 API 키 보관

```
모든 API 키 → .env (os.getenv() 또는 pydantic-settings로만 읽기)
코드 하드코딩 금지
문서 기록 금지 (키 이름만 기록)
```

### 6.2 수집 제한 정책

```
CAPTCHA/Turnstile/로그인/페이월 우회: 절대 금지
proxy rotation: 금지
내부 RPC/비공개 API: 금지
robots.txt 무시: 금지
Google Trends Explore 429 우회: 금지 (max_retries_on_429=0)
GDELT 연속 호출: min_interval 60s 준수
```

### 6.3 저장 데이터 보안

```
ingestion/outputs/**  → .gitignore (커밋 금지)
outputs/state/rate_limit_cache.json → .gitignore (런타임 상태)
raw payload/본문 전문 → 저장소 제외 (저작권/용량)
```

---

## 7. no bypass 정책 (절대 제약)

CLAUDE.md와 Implementation_Instructions/README.md의 운영 제약을 반복 명시:

```
금지 명령:
- rm / del / erase / rmdir / Remove-Item (어떤 인자든)
- git reset --hard
- git clean -fdx
- git push (모든 변형)
- docker volume rm
- docker system prune -af

금지 행위:
- CAPTCHA/Turnstile/로그인/페이월 우회
- proxy rotation
- 내부 RPC 해킹
- Google Trends Explore 429 우회
- rate limit 무시 연속 재시도
- 실패를 PASS로 보고
- 투자 조언/매수·매도 추천 출력
- .env 키 값 출력
```

---

## 8. 보안 리스크 매트릭스

| 리스크 | 등급 | 현재 상태 | 완화 방법 |
|--------|------|----------|----------|
| .env 키 노출 | CRITICAL | 보호됨 (규칙 존재) | scan_secrets 자동화, deny hook |
| git push 의도치 않은 실행 | HIGH | deny 목록으로 차단 | 현재 양호 |
| MCP tool poisoning | HIGH | MCP 미사용 | MCP 도입 시 description 검토 |
| 파괴적 명령 실행 | HIGH | deny 목록으로 차단 | hooks guard 추가 권장 |
| 저작권 침해 (전문 재배포) | HIGH | 정책 존재하나 자동화 없음 | legal-safety-review-skill 추가 |
| rate limit 위반 | MEDIUM | rate_limit_policy.yaml 존재 | hook으로 reminder 추가 |
| 명예훼손성 AI 요약 | MEDIUM | 기능 미구현 | LLM 필터 (오케스트레이션 단계) |
| 중복 사건 증폭 | LOW | 중복 제거 로직 예정 | 오케스트레이션 단계 구현 |

---

## 9. Security Checklist (적용 전 확인)

```
[ ] .env 파일이 .gitignore에 포함되어 있는가
[ ] secret scan PASS 확인
[ ] deny 목록에 모든 파괴적 명령이 있는가
[ ] 새 에이전트의 tools 목록이 최소 권한인가
[ ] MCP 도입 시 least privilege 적용 여부
[ ] hooks guard가 forbidden command를 차단하는가
[ ] google_trends_explore가 PASS로 표기되지 않았는가
[ ] 약관 검토 없이 신규 소스가 추가되지 않았는가
```
