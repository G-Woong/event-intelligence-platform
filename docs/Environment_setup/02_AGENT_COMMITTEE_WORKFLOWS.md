# 02. Agent Committee Workflows 설계

> **생성일**: 2026-06-13
> **목적**: 5개 위원회 워크플로우 설계. 각 위원회는 중요 결정 전에 다중 에이전트가 협의하는 구조.
> **이번 턴 제약**: 설계 문서만. 실제 워크플로우 자동화 구현 없음.

---

## 위원회 구조 개요

위원회(committee)란 단일 에이전트가 결정하기 어려운 사항을 여러 전문 에이전트가 합의하는 구조다.
각 위원회는 trigger → 참여 에이전트 → 판정 규칙 → 결과 artifact 흐름을 따른다.

**판정 규칙 공통 원칙:**
- 모든 위원회는 만장일치 또는 과반수 PASS/FAIL을 요구한다.
- 단 1명의 HIGH-RISK 반대도 BLOCKED로 처리한다.
- 판정 결과는 한국어 리포트로 작성한다.

---

## 위원회 A: Source Addition Committee (소스 추가 검토)

### 목적
신규 source 추가 전 다각도 검토. rate-limit/약관/body extraction/schema/test 검증 포함.

### 참여 에이전트
| 에이전트 | 역할 | 거부권 |
|---------|------|--------|
| source-ingestion-engineer | 기술적 수집 가능성 검토 | YES |
| legal-safety-compliance-reviewer | 약관/저작권/재배포 리스크 | YES |
| data-quality-auditor | body 품질/schema 적합성 | YES |
| test-validation-agent | 테스트 커버리지 확인 | NO |
| security-permission-guardian | rate-limit/우회 금지 정책 | YES |

### Trigger
- 새로운 소스를 source_registry.yaml에 추가하려는 경우
- 기존 소스의 수집 방식(API→Playwright 등) 변경 시

### 필요 입력 (input)
```
source_id: <string>
source_url: <URL>
collection_method: api | playwright | rss | html
rate_limit_known: <string or "unknown">
terms_url: <URL or "unknown">
purpose: primary_seed | enrichment | both
```

### 단계별 흐름

```
Step 1. [security-permission-guardian]
  - robots.txt 확인
  - rate-limit 정책 검토 (rate_limit_policy.yaml 반영 필요한지)
  - no bypass 정책 위반 여부
  → 결과: APPROVED_FOR_REVIEW / BLOCKED_BYPASS_DETECTED

Step 2. [legal-safety-compliance-reviewer]
  - 약관 검토 (WebFetch로 약관 페이지 확인)
  - 재배포 금지 여부
  - 상업 라이선스 요구 여부
  → 결과: LEGAL_APPROVED / CONDITIONAL / LEGAL_BLOCKED

Step 3. [source-ingestion-engineer]
  - collection_method 기술 검증
  - 프로브 테스트 (run_collection_probe --dry-run)
  - body extraction 가능성 평가
  → 결과: TECH_FEASIBLE / TECH_CAUTION / TECH_BLOCKED

Step 4. [data-quality-auditor]
  - 샘플 데이터 품질 평가 (Step 3 결과 기반)
  - minimum_required_fields 충족 여부
  - EventSeedCandidate schema 적합성
  → 결과: QUALITY_PASS / QUALITY_CAUTION / QUALITY_FAIL

Step 5. [test-validation-agent]
  - 테스트 파일 존재 여부 확인
  - 테스트 실행 (소스 추가 후 pytest 확인)
  → 결과: TESTS_PASS / TESTS_FAIL

Step 6. [합산 판정]
  - 모든 BLOCKED/FAIL = 전체 BLOCKED
  - CONDITIONAL 있으면 CONDITIONAL_APPROVAL (운영 조건 명시 필수)
  - 전부 APPROVED/PASS = APPROVED
```

### 판정 기준

| 판정 | 조건 | 다음 액션 |
|------|------|----------|
| APPROVED | 모든 에이전트 PASS | source_registry.yaml 추가 진행 |
| CONDITIONAL_APPROVAL | CONDITIONAL ≥ 1, BLOCKED 0 | 조건 명시 후 제한적 추가 |
| DEFER | 기술적 불확실성 (추가 조사 필요) | 별도 라운드 |
| BLOCKED | BLOCKED ≥ 1 또는 LEGAL_BLOCKED | 추가 불가 |

### 예시 프롬프트
```
소스 추가 검토를 수행하라.
source_id: reddit_oauth
source_url: https://oauth.reddit.com/api/v1/
collection_method: api
rate_limit_known: "60 req/min (OAuth)"
terms_url: https://www.redditinc.com/policies/data-api-terms
purpose: community_signal
```

### proposed diff (workflow 기록용 artifact)

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# 위원회 결과 artifact 형식 (실제 workflow가 아닌 수동 기록용)
diff --git a/docs/ingestion/source_addition_decisions.md b/docs/ingestion/source_addition_decisions.md
new file mode 100644
--- /dev/null
+++ b/docs/ingestion/source_addition_decisions.md
@@ -0,0 +1,20 @@
+# Source Addition Committee Decisions
+
+| date | source_id | legal | tech | quality | test | final | conditions |
+|------|-----------|-------|------|---------|------|-------|------------|
+| (기록 시작) | | | | | | | |
```

---

## 위원회 B: Orchestration Design Committee (오케스트레이션 설계 검토)

### 목적
Celery/LangGraph/event queue 설계 검토. runner contract 연결, state machine, retry/cooldown 정책 포함.

### 참여 에이전트
| 에이전트 | 역할 | 거부권 |
|---------|------|--------|
| orchestrator-architect | 전체 설계 제안 | YES |
| operations-sre-agent | 운영 가능성 평가 | YES |
| source-ingestion-engineer | runner contract 검토 | YES |
| data-quality-auditor | 품질 파이프라인 검토 | NO |
| test-validation-agent | 테스트 가능성 확인 | NO |

### Trigger
- Celery/LangGraph 설계 초안 완성 시
- 기존 오케스트레이션 구조 변경 시
- 새 runner 추가로 orchestration 계약 변경 시

### 필요 입력
- orchestration 설계 문서 (초안)
- 현재 runner map (13개)
- rate_limit_policy.yaml
- docs/92 (수집 주기)

### 단계별 흐름

```
Step 1. [orchestrator-architect]
  - 설계 초안 발표
  - Celery task 구조, LangGraph state machine, routing 규칙 제시

Step 2. [operations-sre-agent]
  - 운영 가능성 검토 (Redis 가용성, worker 확장성, 장애 복구)
  - 모니터링/alerting 방안

Step 3. [source-ingestion-engineer]
  - runner contract 적합성 검토
  - 13개 runner 모두 커버되는지 확인
  - rate-limit 정책 준수 여부

Step 4. [data-quality-auditor]
  - 품질 체크포인트 위치 확인
  - 수집 → 파이프라인 연결 지점 검토

Step 5. [test-validation-agent]
  - 테스트 가능한 구조인지 확인
  - integration test 지점 제안

Step 6. [합산 판정]
  - orchestrator-architect/operations-sre-agent/source-ingestion-engineer 모두 APPROVED = 진행
  - 단 1개라도 BLOCKED = 설계 재검토
```

### 판정 기준

| 판정 | 조건 |
|------|------|
| DESIGN_APPROVED | 3개 핵심 에이전트 모두 APPROVED |
| DESIGN_REVISION_NEEDED | 1~2개 CAUTION (수정 후 재검토) |
| DESIGN_BLOCKED | 1개 이상 BLOCKED |

---

## 위원회 C: Business Reality Committee (비즈니스 현실 검토)

### 목적
"이 웹이 실제로 팔리는가?" 비즈니스 현실성 검토.
기능이 사용자의 돈/시간을 아껴주는가? 정보 과잉/신뢰성/차별화 문제 해결 여부.

### 참여 에이전트
| 에이전트 | 역할 | 거부권 |
|---------|------|--------|
| adversarial-reality-critic | 냉정한 반박 | YES |
| commercialization-strategist | 상용화 전략 제안 | NO |
| business-intelligence-analyst | 시장 인사이트 분석 | NO |
| product-ux-strategist | UX/신뢰 설계 | NO |

### Trigger
- 새 기능 기획 완료 시
- MVP 릴리즈 전
- 비즈니스 모델 변경 시
- 분기별 전략 리뷰

### 단계별 흐름

```
Step 1. [commercialization-strategist + business-intelligence-analyst + product-ux-strategist]
  - 각자 독립적으로 현재 기능 가치 평가
  - 타겟 고객 가설 제시
  - 차별화 포인트 목록 작성

Step 2. [adversarial-reality-critic]
  - Step 1 결과를 전부 반박 시도
  - "왜 이 제품이 실패할 것인가" 관점으로 공격
  - 각 주장에 VALID/QUESTIONABLE/FALSE 판정

Step 3. [commercialization-strategist]
  - 반박 수용 후 수정된 전략 제시
  - 수용 불가 반박에 대한 반론

Step 4. [합산 리포트]
  - 검증된 강점 목록
  - 해결이 필요한 약점 목록
  - GO/NO_GO/CONDITIONAL 판정
```

### 핵심 질문 (이 위원회에서 반드시 답해야 함)

```
1. 이 서비스는 현재 Google News / Naver / Feedly보다 나은가? 어떤 점에서?
2. 사건 증거 체인이 실제로 사용자 신뢰를 높이는가, 아니면 오버엔지니어링인가?
3. 38개 소스 수집이 실제로 사용자가 체감하는 가치로 이어지는가?
4. 한국 시장과 글로벌 시장 중 어디를 먼저 공략해야 하는가?
5. 유사 서비스(Recorded Future, Morning Brew, Perplexity) 대비 명확한 차별화는?
```

---

## 위원회 D: Release Gate Committee (릴리즈 게이트)

### 목적
배포 전 최종 게이트. pytest/secret scan/docs conflict/artifact manifest/env hygiene/git status 종합 확인.

### 참여 에이전트
| 에이전트 | 역할 | 거부권 |
|---------|------|--------|
| test-validation-agent | 테스트/scan/diff 검증 | YES |
| security-permission-guardian | 보안 정책 준수 | YES |
| docs-memory-curator | 문서 상태 확인 | YES |
| legal-safety-compliance-reviewer | 법무 최종 확인 | YES |
| operations-sre-agent | 운영 환경 준비 확인 | YES |

### Trigger
- `main` 브랜치 배포 전
- 새 소스 대거 추가 후
- 오케스트레이션 구현 완료 후

### Release Gate 체크리스트 (모두 PASS 필요)

```
[ ] pytest 0 fail
[ ] secret scan verdict=PASS, WARNING 0
[ ] git diff --check 0 error
[ ] artifact_manifest_final.md 최신 상태
[ ] docs/Environment_setup/README.md 진입점 유효
[ ] rate_limit_policy.yaml per-source 정책 존재
[ ] google_trends_explore = CONFIRMED_EXTERNAL_RATE_LIMIT (PASS로 표기 금지)
[ ] gdelt = min_interval 60s 유지
[ ] MCP 서버 (있을 경우) allowlist 최신 상태
[ ] .env 실제 키 값 어떤 문서에도 없음
[ ] CLAUDE.md 운영 제약 준수 확인
[ ] forbidden command (git push, rm 등) deny 목록 확인
```

### 판정

| 판정 | 조건 | 다음 액션 |
|------|------|----------|
| RELEASE_APPROVED | 모든 체크리스트 PASS | 배포 진행 |
| CONDITIONAL_RELEASE | 1~2개 CAUTION (blocking 아님) | 조건 명시 후 배포 |
| BLOCKED | 1개 이상 FAIL | 수정 후 재검토 |

---

## 위원회 E: Red-Team Critique Committee (레드팀 비판)

### 목적
잘못된 claim, 저작권 위험, source hallucination, tool overreach, false positive event, defamatory summaries, duplicate amplification, trend manipulation risk를 선제적으로 발견.

### 참여 에이전트
| 에이전트 | 역할 | 거부권 |
|---------|------|--------|
| adversarial-reality-critic | 기술/운영 취약점 공격 | YES |
| legal-safety-compliance-reviewer | 법무/저작권 리스크 | YES |
| security-permission-guardian | 보안 취약점 | YES |
| data-quality-auditor | 데이터 품질 오류 | YES |

### Trigger
- AI 요약 기능 추가 전
- 사건 클러스터링 기능 추가 전
- 외부 사용자에게 공개 전
- 분기별 또는 major 기능 릴리즈 전

### Red-Team 공격 벡터

```
1. Source Hallucination
   - "이 소스에서 수집했다"고 주장했지만 실제로는 없는 경우
   - 검증: artifact_manifest_final.md vs 실제 outputs/ 비교

2. False Positive Event
   - 실제 사건이 아닌 것을 사건으로 분류
   - 검증: event_candidate schema 검증 + 신뢰도 임계값

3. Defamatory Summaries
   - AI 요약이 허위 사실을 포함하거나 명예훼손성 표현 사용
   - 검증: LLM 출력 후 legal-safety 필터 통과 여부

4. Duplicate Amplification
   - 동일 사건을 여러 소스에서 중복 집계해 사건 중요도를 과장
   - 검증: 동일 URL/canonical URL 중복 제거 로직

5. Trend Manipulation Risk
   - 단일 고빈도 소스(google_trends_explore 등)가 트렌드를 왜곡
   - 검증: 소스 다양성 지수 (Shannon entropy of source distribution)

6. Copyright Infringement
   - body extraction 후 전문 재배포
   - 검증: full-text vs snippet 정책, guardian/nyt/newsapi 약관 준수

7. Tool Overreach
   - Claude Code 에이전트가 허용 범위 외 도구 사용
   - 검증: .claude/settings.json deny 목록 vs 실제 실행 명령

8. Rate Limit Violation
   - rate_limit_policy.yaml 무시 연속 호출
   - 검증: rate_limit_cache.json 상태 + audit JSONL
```

### 판정

| 판정 | 조건 |
|------|------|
| CLEAN | 0개 위협 발견 |
| CAUTION | 1~3개 MEDIUM 위협 |
| HIGH_RISK | 1개 이상 HIGH 위협 (blocking) |

---

## 위원회 운영 원칙

1. **비동기 협의**: 각 에이전트는 독립적으로 분석 후 리포트 제출. 다른 에이전트 결과에 영향받지 않는다.
2. **근거 필수**: 모든 판정에는 구체적 근거(파일 경로, 코드 라인, 약관 텍스트)가 있어야 한다.
3. **추정 명시**: 공식 확인 없이 추정한 내용은 반드시 "[추정]"으로 표기한다.
4. **google_trends_explore 표기 규칙**: `CONFIRMED_EXTERNAL_RATE_LIMIT`, `NOT_READY_EXTERNAL_RATE_LIMIT` 만 사용. `PASS` 또는 `APPROVED` 금지.
5. **결과 artifact**: 각 위원회 결과는 `docs/committee_decisions/` 또는 해당 docs 하위 파일로 기록.

---

## 위원회별 실행 주기

| 위원회 | 실행 시점 | 빈도 |
|--------|----------|------|
| A. Source Addition | 신규 소스 추가 시 | 필요 시 |
| B. Orchestration Design | 아키텍처 결정 전 | 1회 (오케스트레이션 시작 전) |
| C. Business Reality | MVP/분기 리뷰 | 분기별 |
| D. Release Gate | 배포 전 | 배포마다 |
| E. Red-Team Critique | major 기능 후 | 분기별 |
