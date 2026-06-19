# 05 — 배선: 훅 · 스킬 · settings  · rev2

> Windows 11 / PowerShell 5.1 / `py` 런처 / stdlib-only / fail-open.
> rev2 변경: R1(훅은 JSON만), R2(status porcelain + HEAD delta), R5(turn 카운터·narrative_turn_id), R6(soft, block 안 함), R7(Move-Item 가드), R8(캐시 as_of), R10(timeout 15 통일).

---

## 1. 신규 훅: `.claude/hooks/turn_state_snapshot.py` (Stop)

**역할:** 사실 스냅샷 + 파일경로형 trigger 감지 + freshness 판정. **PROJECT_STATUS.md·narrative_marker.json 안 건드림(R1).** `.harness/machine_status.json` **만** 쓰고 `.harness/narrative_marker.json` 은 **읽기만** 한다. **fail-open**(오류 시 exit 0). **block 안 함(soft 기본, R6).**

> **⚠ 필수: 모든 Stop 훅은 `stop_hook_active` 가드를 가져야 한다(rev3 근본수정, ADR #5).** Claude Code 에서 Stop 훅이 출력(additionalContext)을 내면 **턴 종료가 차단되고 에이전트가 재호출**된다. continuation 중에도 또 출력하면 무한 루프(block cap 9회 강제종료)다. → payload 의 `stop_hook_active==true` 면 **출력 없이 즉시 return**. 이 가드는 신규 훅뿐 아니라 기존 `secret_scan_reminder`·`docs_conflict_grep_check` 에도 적용됨.
> **구현 검증 완료(rev2 팀검토 반영):** ① porcelain 은 `git status --porcelain -z`(NUL 구분) + UTF-8 명시 디코드 → 한글/공백/따옴표 경로 안전. ② turn 은 **session별 map**(`turns`)으로 단조성 유지(멀티 worktree/세션 안전). ③ severity 는 word-boundary 정규식 + 체인 마지막값(현재값). ④ prev_head 가 rebase 로 사라지면 `delta_incomplete=true` 플래그. 단위검증: 빈입력 exit0 / severity 오탐0 / marker 분리 fresh 전이 / turns map.

**입력 payload(공식 확인 필드):** `session_id, transcript_path, cwd, permission_mode, hook_event_name, effort`. **turn 번호·stop_hook_active 는 payload 에 없음** → 직접 파생.

**의사코드:**
```python
# stdlib only. fail-open.
payload = json.loads(stdin or "{}"); cwd = payload.get("cwd") or os.getcwd()
sid = payload.get("session_id", "nosession")
cfg = read_json(".harness/config.json", DEFAULTS)
prev = read_json(".harness/machine_status.json", {})

# (R1/R5) turn id: session별 map 으로 단조 유지(멀티 worktree/세션 안전, 200 cap FIFO).
turns = dict(prev.get("turns", {})); prev_turn = turns.get(sid)
turn = (prev_turn or 0) + 1; turns[sid] = turn

# (R2) delta = uncommitted(status porcelain, untracked 포함) + HEAD 이동분
porcelain = git("status --porcelain", cwd)          # untracked/staged/modified 모두
head = git("rev-parse HEAD", cwd)
moved = git(f"diff --name-only {prev['head']} {head}") if prev.get("head") and prev["head"]!=head else ""
names = parse_paths(porcelain) | set(moved.splitlines())
numstat = git("diff --numstat HEAD", cwd)           # LOC(추적분); untracked 는 라인수 별도 집계 가능
buckets = classify(names, whitelist=cfg["loc_whitelist"])   # code/docs/config/outputs, LOC 화이트리스트 제외

# (파일경로형 트리거만 — 의미형은 스킬이; R2/B3)
audit_required = (buckets["code_py_loc"]>=cfg["audit_loc_threshold"]
                  or len(buckets["code_files"])>=cfg["audit_files_threshold"]
                  or touched(names, ".claude/settings", ".env", ".claude/hooks")
                  or new_source(names))   # ingestion/sources/** 신규

# 사실(가벼운 것만; pytest 실행 안 함 — 캐시 읽기 + as_of 비교, R8)
tc = read_json(".harness/last_test_result.json", None)
test_stale = bool(tc) and tc.get("as_of_commit") != head
risk = parse_risk_register("docs/_RISK/RISK_REGISTER.md")   # 정규식 카운트

# (R5) freshness: 에이전트 전용 marker 파일을 읽기만 해서 비교 (mtime 금지)
marker = read_json(".harness/narrative_marker.json", {})
narrative_fresh = (prev_turn is not None and marker.get("session_id")==sid
                   and marker.get("narrative_turn_id")==prev_turn)

write_json(".harness/machine_status.json", {   # ← 훅 전용 writer
  "session_id": sid, "turn": turn, "turns": turns, "head": head,
  "delta_incomplete": delta_incomplete, "buckets_count": ..., "code_files": ...,
  "audit_required": audit_required, "tests": tc, "test_stale": test_stale,
  "risk": risk, "narrative_fresh": narrative_fresh, "enforce": cfg["enforce"],
})  # narrative_marker.json 은 절대 안 씀(에이전트 전용)
# (R6) soft: nudge 만. block/ decision 안 씀. additionalContext 와 block 동시 금지(공식 미정의).
if names and not narrative_fresh:
    emit_additional_context("[turn-closeout 권장] 변경 있음·서술 미갱신. /turn-closeout 실행 권장.")
return 0
```

> **검증(빈 환경 fail-open):** `echo '{}' | py .claude/hooks/turn_state_snapshot.py` → exit 0, 예외 없음.
> **timeout:** settings 에서 **15s 통일**(R10). git 호출 각 timeout 8s. 대형 레포 실측을 `06 §4` 검증에 포함.
> **pytest 안 돌림 이유:** Stop 훅 timeout + 매 턴 전체 테스트 비용 과다. 결과는 `test-validation-skill` 이 `last_test_result.json`(+`as_of_commit`)에 캐시, 훅은 읽고 STALE 비교만.

---

## 2. 신규 스킬: `.claude/skills/turn-closeout/SKILL.md`

```yaml
---
name: turn-closeout
description: 매 턴 종료 직전 실행. PROJECT_STATUS 서술, docs 코드기반 동기화 후보 점검, risk 감사, 의미형 트리거 판정, 유의미 변경 시 팀 감사 라우팅, 의사결정 ADR 기록.
when_to_use: 매 턴 응답을 마치기 직전. 코드/문서/설정 변경이 있던 모든 턴.
user-invocable: true
allowed-tools: Read, Grep, Glob, Write, Edit, Bash, Agent
---
```
**procedure:**
```
1. Read .harness/machine_status.json (훅이 만든 사실/파일경로형 trigger)
2. [의미형 트리거 판정] _DECISIONS 완료전이 / risk CLOSED 전이 / archive 게이트 (03 §2b)
3. [Req4] RISK_REGISTER 각 Closure 를 grep 검증 → 신규/종결 후보
4. [Req2a] "이미 적용/미사용" docs 후보를 grep 근거로 식별 (이동은 6단계 감사 후)
5. [Req3] audit_required==true 또는 의미형 트리거 시:
      - 03 라우팅 표대로 에이전트 병렬 호출 (adversarial-reality-critic 항상)
      - 결과 종합 → REAL 이슈 risk 등록, archive/trash 후보 승인/기각
6. [확정 이동] 승인 항목만 Move-Item 으로 _ARCHIVE/_TRASH + _INDEX 1줄
7. [Req2b] 설계 판단/아이디어 착지/폐기 있었으면 docs/_DECISIONS/SESSION_*.md 에 ADR 블록(왜>무엇)
8. [Req1] PROJECT_STATUS.md 서술(비개발자 톤) 덮어쓰기 ← 에이전트 전용 파일
9. .harness/narrative_marker.json 에 {session_id, narrative_turn_id: machine_status.turn} 기록 ← 에이전트 전용 파일(freshness 신호, R5). machine_status.json 은 절대 안 씀.
10. (필요 시) test-validation-skill 로 .harness/last_test_result.json(+as_of_commit) 갱신
```
**safety:** `rm`/`Remove-Item` 금지(이동은 `Move-Item`/`git mv`), `git push` 금지, `.env` 값 출력 금지, google_trends_explore PASS 오표기 금지.

---

## 3. settings.json 변경
- **Stop 훅 1개 추가**(기존 2개 뒤), timeout **15**:
```json
{ "type":"command","command":"py",
  "args":["${CLAUDE_PROJECT_DIR}/.claude/hooks/turn_state_snapshot.py"], "timeout":15 }
```
- **Move-Item 정책(R7):** `PowerShell(*)` 가 이미 전부 allow → **Move-Item 명시 추가는 기능상 무의미**(문서 가치만). "최소권한" 표기 안 함. 대신 **`forbidden_command_guard.py` 에 가드 규칙 추가**: command-position 의 `Move-Item`/`mv` source 가 real `.env` 또는 `*-key.json`/`*service-account*` 를 가리키면 **deny**. → **best-effort 가드**(리터럴 직접 이동만 차단; 변수 경유·Copy-Item·Rename-Item 은 정규식으로 못 막음 — 적대 검토 B3). **1차 비밀 방어는 gitignore + os.getenv + 산출물 격리(R-Secret)**, 이 가드는 defense-in-depth 한 겹.

> **팀 검토 검증 결과(반영):** ① 다중 Stop 훅 additionalContext 는 **공식 문서상 모두 전달(유실 없음, 10k자 한도)** — nudge silent-loss 우려(B3 critic) 해소. 이 레포는 이미 secret/docs 2개 훅으로 동일 패턴 사용 중. ② turn-closeout 매 턴 강제 안 함(soft)은 **사용자 명시 수용(Q1: 사실 보장+의미 best-effort)** — 설계 의도. ③ 단일 writer 는 규율로 보장(스킬에 경로 게이트는 없음) — 시간 분리(훅=Stop시점, 스킬=턴중) + 다른 파일이라 실무 충돌 LOW.
- 나머지 deny/PreToolUse 그대로(rm 차단 유지).

---

## 4. `.harness/config.json` (tracked, 토글)
```json
{ "enforce": "soft",
  "audit_loc_threshold": 40, "audit_files_threshold": 5,
  "archive_retention_turns": 30,
  "loc_whitelist": ["*.lock","requirements*.lock*","ingestion/outputs/**"],
  "status_path": "PROJECT_STATUS.md" }
```
> `enforce` 기본 **soft**(R6, 사용자 Q1 채택). `"block"` 은 미문서 가드 의존이라 **현재 미지원/보류**(실증 전 금지).

## 5. `.gitignore` 추가
```
# Harness runtime
.harness/machine_status.json
.harness/last_test_result.json
docs/_TRASH/
```
> `.harness/config.json`·`PROJECT_STATUS.md` 는 tracked(설정·이력 자산).

## 6. 재사용성
- 이식 단위: 훅 1 + 스킬 1 + `config.json` + settings 1줄 + guard 가드규칙. 경로/임계값은 config 외부화.
- 라우팅 표(`03`)만 그 레포 에이전트 이름으로 교체(에이전트 이름은 하드코딩 — "config만 복사" 아님, 정직 표기).
