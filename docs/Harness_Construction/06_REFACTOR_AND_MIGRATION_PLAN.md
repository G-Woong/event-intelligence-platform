# 06 — 구조 리팩토링 · 마이그레이션 실행 계획  · rev2

> rev2: R1~R10 + Q1 반영. **진짜 삭제(`rm`/`Remove-Item`) 끝까지 안 씀 — `Move-Item`/`git mv`만.** (deny·CLAUDE.md 준수 + 되돌림 가능)

---

## 1. 신규 디렉토리/파일 (생성)
```
PROJECT_STATUS.md                       (루트, tracked, 에이전트 전용)
README.md                               (루트, 작성 완료 — rev2 반영 갱신)
.harness/config.json                    (tracked, enforce=soft)
.harness/machine_status.json            (gitignored, 훅 전용)
.harness/last_test_result.json          (gitignored, test-validation-skill)
docs/_DECISIONS/                        (의사결정 지식자산)
docs/_RISK/RISK_REGISTER.md             (열림/부분종결)
docs/_RISK/RISK_CLOSED.md               (완전종결)
docs/_TRASH/                            (gitignored)
.claude/hooks/turn_state_snapshot.py    (Stop, JSON만 기록)
.claude/skills/turn-closeout/SKILL.md
```

## 2. 이관(Move) · 정정 — `git mv` / `Move-Item` / Edit
| 대상 | 동작 | 사유 |
|---|---|---|
| `_CANONICAL/05_RISK_REGISTER.md` 본문 | **통째 이동** → `docs/_RISK/RISK_REGISTER.md` (stub 금지) | R3 단일출처. `_CANONICAL/00` 의 링크·읽기순서를 새 경로로 Edit. |
| `docs-sync-skill/SKILL.md`, `docs-memory-curator.md` 단일출처 문구 | **Edit 정정** | R4: "단일출처=`*_FINAL.md`" → "권위 정점=`_CANONICAL/*`, FINAL 은 순서③". 동사 분리(교정/이동/판정). |
| `forbidden_command_guard.py` | **가드 규칙 추가** | R7: Move-Item/mv source 가 real `.env`/key 파일이면 deny. |
| (향후) 적용 완료/미사용 메모리 md | 점진 archive (팀 감사 통과분만) | R2 A.4. 일괄 X. |

## 3. 설정 변경
- `settings.json`: Stop 훅 1개 추가(timeout 15). **Move-Item allow 명시는 생략**(`PowerShell(*)` 가 이미 허용 — R7, 무의미). 
- `.gitignore`: `machine_status.json`, `last_test_result.json`, `docs/_TRASH/` 3줄.

## 4. 실행 순서 + 검증 (각 단계 = 검증 가능 목표)
```
0. docs/_DECISIONS 부트스트랩: rev2 설계결정 ADR 1블록 (왜>무엇)
   → 검증: docs/_DECISIONS/SESSION_*.md 존재 + 템플릿 9항목 포함
1. .harness/config.json + .gitignore
   → 검증: py -c "import json;json.load(open('.harness/config.json'))" OK
2. turn_state_snapshot.py (JSON만, status porcelain+HEAD delta, turn 카운터, fail-open, block 안 함)
   → 검증: echo '{}' | py ...turn_state_snapshot.py → exit 0 (빈 환경 안 죽음)
   → 검증: 더미 변경 후 → .harness/machine_status.json 생성, PROJECT_STATUS.md 는 안 건드림(R1)
   → 검증: timeout 15s 내 완료 실측(대형 diff)
3. settings.json Stop 훅 등록 + forbidden_command_guard Move-Item 가드
   → 검증: 한 턴 후 machine_status.json turn/시각 갱신. 가드: Move-Item .env 차단 단위 테스트
4. RISK 본문 통째 이동 + _CANONICAL/00 링크 갱신 (stub 금지)
   → 검증: risk id 보존, 죽은 링크 0, _CANONICAL/05 stub 없음, 단일출처 grep OK
5. docs-sync-skill·curator 단일출처 문구 정정
   → 검증: "단일출처=*_FINAL" 잔존 0, _CANONICAL 권위 일관
6. turn-closeout/SKILL.md (의미형 트리거 판정·감사 라우팅·_DECISIONS·narrative_turn_id 갱신)
   → 검증: /turn-closeout 호출 시 10단계 수행, PROJECT_STATUS 서술 생성, narrative_turn_id 갱신
7. PROJECT_STATUS.md 초판 (machine_status.json 렌더 + 서술) + README rev2 반영
   → 검증: 비개발자 읽기 테스트(전문용어 풀이), as_of 표기
8. 전체 스모크: test-validation-skill 1회 (pytest→last_test_result.json+as_of_commit, secret scan, diff)
   → 검증: PASS / 신규 risk docs/_RISK 등록
```

## 5. 단계별 팀 검토 (사용자 지시)
- **각 구조 변경 단계**(특히 2·3=권한/훅, 4·5=단일출처) 후 `03` 라우팅대로 팀 감사. 권한/보안 변경은 `security-permission-guardian`+`adversarial-reality-critic` 필수.
- 새 risk 발견 시 **즉시 멈추고 보고**(사용자 지시).

## 6. 안전·롤백
- 이동은 되돌림 가능(`Move-Item` 역이동). 단 `_TRASH` 는 로컬 복구 한정(R9, gitignored).
- 훅 fail-open. block 안 씀(soft). → 깨져도 턴 안 막음.
- 비가역(메모리 md archive) 직전 항상 `03` 팀 감사 게이트.

## 7. 다음 단계 착수 지시(요약)
> "rev2 설계도 `00~06` 골격으로 §4 순서대로 구현. 각 단계 검증 통과 후 다음. 파일 이동은 `Move-Item`/`git mv` 만. 권한/구조 변경 단계마다 팀 감사. 새 risk 시 멈추고 보고. 마지막에 `turn-closeout` 자기 실행으로 PROJECT_STATUS 초판."
