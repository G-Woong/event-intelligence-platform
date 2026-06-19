# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 하는 중인가:** 턴 마감 시스템이 "감사했다고 말만 해도 통과"하던 약점을, **증거를 적어야 통과하고 파일 내용이 바뀌면 반드시 다시 검토하게** 조였습니다.
- **이번 턴에 실제로 끝낸 것:** 직전 감사가 의심한 7개 위험을 **긍정편향 없이 재검증**했고, 진짜 문제(내용변경 미감지·자기보고 게이트·설정 재현성·죽은코드 탐지 약함)는 코드로 닫고, **거짓 전제였던 항목(자동 휴지통 매니페스트·논문 위험)은 근거를 들어 위험 아님으로 판정**했습니다. 팀 검토 4종이 찾아낸 실제 버그 1개도 고쳤습니다.
- **지금 막힌 것:** 자기보고의 근본 한계(LLM이 실제로 검토했는지는 어떤 자동장치도 증명 불가)는 완화만 가능 — 아래 ⚠️에 정직히 남김.

## 📋 자동 수집 사실 (machine_status.json)
- 변경: harness 훅·스킬·스크립트·문서(애플리케이션 코드 변경 0). 감사 필요 유형: adversarial / evidence / harness_runtime / risk_closure / security
- 열린 RISK: **16건** (HIGH 3 · MEDIUM 7 · LOW 6) — `docs/_RISK/RISK_REGISTER.md` (신규 R-HarnessReproducibility)
- 비밀 스캔: PASS (변경 8파일) · dead-code 후보: **132건**(ruff symbol, 삭제 안 함, 그중 59 프로덕션)
- 팀 감사: orchestrator-architect + security-permission-guardian + adversarial-reality-critic + docs-memory-curator (4종, REAL_BUG 1건 수정)

## ✅ 이번 턴에 달성한 것
- **R2(내용변경 미감지) 닫음:** signature에 중요 파일군 content-hash 합성(`compute_signature`). 동일 경로의 내용만 바뀌어도 mismatch → 재검토. hook과 `scripts/closeout_sig.py`가 동일 함수·동일 경로집합(`collect_changed_paths`, commit 대칭) 사용. **라이브 실증.**
- **R1(자기보고 게이트) 강화:** required 감사마다 `audit_evidence`(executed+verdict) 구조화 기록 요구. 자기보고 `code_review_completed=true`만으론 **불통과**(실증: 무evidence stamp=False, evidence stamp=True).
- **R6(설정 재현성) 완화:** `.claude/settings.json`이 gitignored임을 확인 → `scripts/harness_doctor.py`(훅 등록 점검)+README setup 섹션+`machine_status.settings_health` 자기점검.
- **R4(죽은코드) 강화:** `dead_code_scan.py`에 ruff(F401/F811/F841) 연동 → 거짓 0 → 132 후보(evidence/confidence 포함). vulture는 `requirements/dev.txt`에 추가(제안, 미설치).
- **REAL_BUG 수정:** 팀감사가 찾은 sig 입력 비대칭(commit 타이밍 게이트 파손)을 `collect_changed_paths` 공유로 해소. fail-open(비-OSError)·timeout(hash 크기상한)·보안(corpus가 키파일 미독) 보강.

## ❌ 달성하지 못한 것 & 왜
- **자기보고 완전 제거:** evidence 게이트도 에이전트가 가짜로 채우면 통과(위조 *비용*만 상승). 진짜 강화는 subagent 산출물 파일 요구이나 `03 §4`(영구 리포트 금지)와 상충 → 보류.
- **enforce=block:** soft 유지(미완은 다음 턴 재알림). block 경로 미실증.
- **dead-code 통폐합:** 후보 식별만(삭제 금지 준수). vulture 미설치로 진짜 uncalled function/class는 미탐.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- **LLM 추론 실제 수행 검증 불가:** 어떤 훅도 "에이전트가 정말 그 감사를 했는지"는 증명 못 함 → transcript 사후검증이 최종 방어선. `R-CloseoutTrust` 잔존.
- **settings.json 자동 재현 불가:** gitignored라 신규 clone에서 doctor를 수동 실행 안 하면 침묵. tracked 전환은 별도 결정 필요.

## ⚠️ 이번 턴 신규/갱신 RISK
- **R-HarnessReproducibility (신규, MEDIUM→LOW):** settings.json gitignored → 신규 clone 훅 미등록. 완화: doctor+문서+self-check.
- **R-CloseoutTrust (갱신, MEDIUM→LOW-MEDIUM):** content-hash+evidence 게이트 라이브 입증. 잔존: 자기보고 한계·enforce=block·closeout_sig 절차 누락.
- **R-DeadCodeAudit (갱신, LOW-MEDIUM→LOW):** ruff 132 후보. 잔존: vulture 미설치·팀 감사 통폐합 미수행.

## 🧭 거짓 전제 판정 (긍정편향 차단)
- **자동 DEAD-docs consumer / 무매니페스트 trash 전환(직전 감사 #2/#3):** `docs_code_sync.py`·`lifecycle_trash_v2.py`·`archive_sweep.py`는 **repo에 존재하지 않음**(grep/Glob 확인, docs-curator 확정). trash는 **이미 무매니페스트 설계**(`_ARCHIVE/_INDEX`는 1줄 tombstone, `_TRASH`엔 README placeholder만). → **NOT_RISK**.
- **논문 claim/evidence risk(직전 감사 #7):** 본 repo는 **이벤트 인텔리전스 웹앱**이지 월드모델 논문 프로젝트가 아님(논문/실험/ablation 산출물 0). → **OUT_OF_SCOPE**(미래 논문 트랙 생기면 `04 §RISK_SPEC` 연구 risk 카테고리 적용).

## 👉 다음에 할 일 (우선순위)
1. `vulture` venv 설치 → 진짜 uncalled function/class 탐 + 프로덕션 132 후보 1차 팀 감사 통폐합(R-DeadCodeAudit 종결 경로).
2. settings.json tracked 전환 여부 결정(R-HarnessReproducibility 종결) — doctor를 setup/CI에 강제.
3. 실제 코드 변경 턴에서 `/code-review` 라이브 호출 → audit_evidence에 실증거 적재 관찰(R5).
4. subagent 산출물 hash를 게이트 증거로 요구하는 `03 §4` 절충안(R-CloseoutTrust phase-3).

## 📁 근거 (이번 턴 핵심)
- `.claude/hooks/turn_state_snapshot.py`(content-hash sig·evidence 게이트·collect_changed_paths·settings_health)
- `scripts/closeout_sig.py`·`scripts/harness_doctor.py`(신규), `scripts/dead_code_scan.py`(ruff 연동)
- `.claude/skills/turn-closeout/SKILL.md`(stamp v2), `docs/_RISK/RISK_REGISTER.md`, `docs/_DECISIONS/2026-06.md`
