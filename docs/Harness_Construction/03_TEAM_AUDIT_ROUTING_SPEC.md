# 03 — 팀 다각도 감사 라우팅 (Req 3)  · rev2

> 아이디어→코드 착지, 코드 메모리화, 대규모 리팩토링, risk 종결 등에서 **객관적·긍정편향 없는 다각도 감사** 발동.
> **훅은 에이전트를 못 띄운다 ⇒ 트리거는 훅/스킬이 감지, 호출은 메인 에이전트(스킬)가.**
> rev2 변경(R2/B3): 트리거를 **파일경로형(훅 판정)** 과 **의미형(스킬 판정)** 으로 분리. 신규소스 트리거 추가. LOC 화이트리스트.

---

## 1. 누가 띄우나 (하네스 사실 — 공식 확인)
- Agent 호출은 **메인 에이전트만**. 훅·서브에이전트는 못 띄움.
- Stop 훅은 턴 완료 시 1회 발화하나 거기서 에이전트를 못 부른다 → **훅은 flag 만 기록**, `turn-closeout` 스킬이 읽어 **메인 에이전트가 병렬 호출**.
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 활성.

---

## 2. 트리거 — 2종 분리 (rev2 핵심)

### 2a. 파일경로형 (훅이 `git status --porcelain` + `--numstat` 으로 결정론 판정)
> 입력은 **"마지막 스냅샷 이후 delta + untracked + staged"** (R2: `diff --name-only HEAD` 누적/commit직후 오작동 회피). 훅은 이름·LOC만 본다.

| 트리거 | 감지 규칙 |
|---|---|
| 코드 착지/대규모 변경 | `ingestion/** backend/** agents/** workers/**` 의 `.py` 추가 LOC ≥ `audit_loc_threshold`(40) **또는** 변경 파일 수 ≥ `audit_files_threshold`(5) |
| 신규 소스 추가 | `ingestion/sources/**` 또는 source registry 파일 신규/변경 (← rev2 추가, 라우팅 §3 마지막 행과 1:1) |
| 권한/보안 표면 | `.claude/settings*.json`, `.env*`, `.claude/hooks/**` 변경 |

**LOC 화이트리스트(과발동 차단):** `requirements*.lock*`, `*.lock`, `ingestion/outputs/**`, 생성물/대량포맷팅, 테스트 픽스처는 LOC 집계 제외.

### 2b. 의미형 (스킬이 **본문 diff/상태 전이** 로 판정 — 훅 불가)
> R2/B3: 아래 3개는 파일명만으론 판정 불가하므로 **`turn-closeout` 절차에서** 판정한다(훅 의사코드에 넣지 않음).

| 트리거 | 판정 방법(스킬) |
|---|---|
| docs 인사이트의 코드 구현 | `_DECISIONS/*.md` 상태 `진행중→완료` 전이 + 대응 코드 변경 동시 |
| risk 종결 리팩토링 | `docs/_RISK/*` 에서 risk severity→CLOSED 전이 + 코드 변경 동반 |
| docs archive/trash 이동 **직전** | 미래 행위 → 훅(사후) 불가. **스킬 내부 게이트**로 이동 직전 항상 감사 |

> 사소한 변경(오타·테스트만·1~2줄)엔 어느 트리거도 안 걸림 → CLAUDE.md "사소한 작업은 판단" 준수.

---

## 3. 라우팅 표 (트리거 → 호출 에이전트)
> **모든 감사에 `adversarial-reality-critic` 필수** = 긍정편향 차단 게이트(사용자 "긍정편향 없는" 요구의 구현).

| 트리거 | 필수 호출 | 도메인 추가(해당 시) |
|---|---|---|
| 코드 착지 / 대규모 리팩토링 | adversarial-reality-critic + test-validation-agent | ingestion→source-ingestion-engineer, 오케스트레이션→orchestrator-architect, 품질→data-quality-auditor |
| risk 종결 | adversarial-reality-critic + test-validation-agent | risk 영역 도메인 1종 |
| docs archive/trash 이동 | adversarial-reality-critic + docs-memory-curator | — |
| 권한/보안 변경 | security-permission-guardian(BLOCKED 권한) + adversarial-reality-critic | — |
| **신규 소스/수집방식** | legal-safety-compliance-reviewer + adversarial-reality-critic | source-ingestion-engineer |

- **개수:** 최소 2(필수쌍) ~ 최대 4. 모호 시 영역 1종 추가. 위 표로 결정론 라우팅.
- **호출 병렬**(독립). 종합은 메인 에이전트가 → `PROJECT_STATUS`(달성/risk) + `docs/_RISK` 반영.
- **디바운스(S-4):** 같은 턴 동일 트리거 재발동 시 `turn_state.json` 의 `audited_this_turn` 플래그로 1회만.

---

## 4. 감사 결과 처리
- 합의 REAL 이슈 → `docs/_RISK/RISK_REGISTER.md` 신규 등록 + `PROJECT_STATUS` 반영.
- archive/trash 이동은 **감사 통과 시에만 실제 `Move-Item`**(반대 의견 있으면 ACTIVE 유지 + risk 등록).
- 감사 자체는 **별도 영구 리포트 파일 안 만듦**(파일 누적 방지). 결론만 1·2·4 산출물에 흡수.
- 중요한 설계 판단이면 `docs/_DECISIONS` 에 ADR 블록(`02 B`)으로도 남김(왜/대안/트레이드오프).

---

## 5. 스킬화 여부
- **파일경로형 트리거 = 훅**(결정론, 매 턴). **의미형 트리거 + 라우팅 실행 = `turn-closeout` 스킬**. 신규 스킬은 `turn-closeout` 1개로 충분.
- `test-validation` 은 **스킬(`test-validation-skill`, Bash로 pytest)** 로 캐시 갱신, **에이전트(`test-validation-agent`)** 는 판정/리뷰 — 역할 분리(S-4).
