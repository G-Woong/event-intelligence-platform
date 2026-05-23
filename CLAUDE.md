# CLAUDE.md — repo-sunny-barto

## 목적
전세계 실시간 사건/이벤트 인텔리전스 웹앱. 다양한 소스에서 사건/이벤트를 수집·정규화·랭킹하고, 사용자에게 신뢰가능한 실시간 인텔리전스를 제공한다.

## 원칙

### 1. 정보 제공이지 투자 조언이 아니다
- 본 시스템은 **사건/이벤트 정보 전달**이 목적이다.
- **투자 권유·매수/매도 추천·금융 조언을 출력하지 않는다.**
- 시장 가격/움직임을 언급할 때도 가치 판단(좋다/사라/팔라)을 덧붙이지 않는다.
- 모델 출력에서 "이 주식을 사라" 같은 표현이 나오면 즉시 톤 다운하고 정보로 환원하라.

### 2. PLAN → IMPLEMENT → VERIFY
- 모든 비자명한 작업은 **PLAN**부터: 무엇을, 왜, 어디를 수정하는지 한국어로 짧게.
- **IMPLEMENT**: 작은 단위(atomic)로 변경. 무관한 리팩토링/추가 기능 금지.
- **VERIFY**: 코드 변경 후 즉시 검증 명령 실행 — 단위 테스트, lint, 또는 최소 import smoke 테스트.
- 검증 없이 "완료"라고 보고하지 말 것.

### 3. 보안
- `.env`의 실제 키 값을 **출력·로그·외부 전송 금지**. 길이/존재 여부만 보고.
- 키를 코드/설정파일/문서에 하드코딩 금지.
- 외부 API 키는 모두 `.env`에서 읽고, 노출되는 에러 메시지에 키가 섞이지 않도록 마스킹.

### 4. Destructive command 금지
다음 명령은 **사용자 명시 요청 전까지 절대 실행 금지**:
- `rm`, `del`, `erase`, `rmdir`, `Remove-Item` 계열 (어떤 인자든)
- `git reset --hard`, `git clean -fdx`
- `git push` (모든 변형)
- `docker volume rm`, `docker system prune -af`

대안: 파일 정리가 필요하면 사용자에게 요청.

## 역할 분담

### Claude (claude/ worktree, 메인 오케스트레이션)
- PLAN 수립, 작업 분해, 통합, 리뷰, 최종 판단.
- atomic task를 codex/ 측에 위임 가능.
- 한국어 보고. 모르는 항목은 `UNKNOWN`, 막힌 항목은 `BLOCKED`로 명시.

### Codex (codex/ worktree, atomic task 수행)
- 단일 책임 단위 코드 구현, 테스트 작성, 대안 코드 작성.
- 본인 worktree 안에서만 작업. 메인 worktree 파일을 직접 수정하지 않음.
- 결과는 diff/패치 단위로 보고.

## 작업 순서

### 환경 우선
앱 구현 전에 다음을 먼저 확정한다:
1. Claude Code 프로젝트 설정 (`.claude/settings.json`)
2. uv 기반 Python 3.11 가상환경
3. Docker Desktop + Compose 동작 확인
4. requirements 분리 정책
5. docker-compose.dev.yml (Milvus, Redis, app)
6. 그 후에 앱 scaffold

### scaffold 이후
- FastAPI (API)
- LangGraph (이벤트 추론 그래프)
- Celery + Redis (비동기 수집/랭킹)
- Milvus (벡터 검색)
- LangSmith (관측)

## 보고 규칙
- 보고는 항상 **한국어**.
- 형식: ① 무엇을 했는가, ② 무엇을 검증했는가, ③ WARNING/BLOCKED/UNKNOWN.
- 추측을 사실처럼 적지 말 것. 모르면 `UNKNOWN`.
- 외부 호출/장기 작업 시작 시에는 1줄 사전 알림.

## 환경
- OS: Windows 11, PowerShell 5.1.
- Python: 3.11 (`py -3.11`). 기본 3.13.5도 존재하나 본 프로젝트는 3.11 고정.
- 패키지 매니저: **uv**. `conda` 사용 금지.
- 런타임 격리: Docker Desktop (compose v2).

## .env 정책
- claude/, codex/ 양쪽에 동일한 키 세트가 존재.
- 키 목록: `LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `OPENAI_API_KEY`, `MILVUS_HOST`, `MILVUS_PORT`, `REDIS_URL`.
- 값이 비어있으면 BLOCKED가 아니라 WARNING으로 표시하고 사용자에게 알린다.
- 키는 코드 안에서 `os.getenv` 또는 `pydantic-settings`로만 읽는다.

## 코드 스타일 핵심
- 불필요한 주석 금지. 식별자명으로 의미가 드러나면 주석 없음.
- 과도한 추상화 금지. 3번 반복되면 그때 함수화.
- 광범위한 `try/except` 금지. 경계(외부 API, 사용자 입력)에서만 방어.
- 새 파일/모듈을 만들기 전에 기존 유틸 재사용 가능성을 먼저 확인.

## 모르는 것
- 명세에 없는 부분은 추측해서 채우지 말고 `UNKNOWN`으로 보고하고 사용자 결정을 요청.
- Claude Code 설정에서 schema 미등재 키는 `docs/COMPATIBILITY_NOTES.md`에 기록.
