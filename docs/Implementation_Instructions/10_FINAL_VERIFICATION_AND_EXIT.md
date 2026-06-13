# 10. 최종 검증·감사·종료 — 전 소스 동작 확인 루프의 출구

> 실행 시점: 01~09 전부 완료(각 문서의 종결 기준 충족) 후. 이 문서를 통과해야만 턴이 끝난다.

## 1. 최종 감사 절차 (순서 고정)

### 1-1. 체크리스트 감사 (증거 검증)

`_progress/closing_checklist.md`의 15개 항목을 한 줄씩 검사한다:
- `PASS` 항목: 증거 3종(명령/출력/경로)이 실재하는지 — artifact 경로는 `Test-Path`로, 테스트명은 `pytest <파일> -q` 재실행으로 확인. **증거가 비거나 재현 불가면 IN_LOOP로 강등하고 해당 문서의 루프로 복귀한다.**
- `BLOCKED_TERMINAL`/`DEFERRED` 항목: 사유·재개 조건이 적혀 있는지. 없으면 미완성.
- `PENDING`/`IN_LOOP` 잔존 시: **종료 불가.** 00 §3.3의 한도(4 iteration) 내라면 루프 재진입, 한도 소진이면 분류 확정 후 재감사.

### 1-2. 회귀 3종 일괄

```powershell
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q
# 기대: 기준선 509 + 신규(01:5, 02:5, 03:~3, 04:3, 05:3, 06:4, 07:~5, 08:≥12, 09:~6) 전부 통과, 실패 0
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths ingestion\outputs docs\ingestion docs\Implementation_Instructions plans
# 기대: verdict=PASS (06 network log 마스킹, 테스트 더미 키 포함 확인)
.\.venv\Scripts\python.exe -m ingestion.tools.check_env_hygiene --env-path .env
# 기대: 기존 WARNING 6건(레거시 alias)에서 증감 없음
```

### 1-3. 전 소스 통합 live 재감사 (이 라운드의 결산 실측)

직전 라운드와 동일 도구로 전수 재실행해 **수치로 개선을 입증**한다. gate가 cooldown 중인 소스는 audit_action(cooldown_skip)으로 자동 기록되므로 강제하지 않는다:

```powershell
$env:PYTHONIOENCODING="utf-8"
# 1차 (trends_explore 포함 — 05에서 활성화됨; gate가 알아서 보호)
.\.venv\Scripts\python.exe -m ingestion.runners.run_primary_seed_live_audit --include-trends-explore
# 2차 (1차 결과로 hot seed 자동 도출)
.\.venv\Scripts\python.exe -m ingestion.runners.run_enrichment_live_audit --from-primary ingestion\outputs\jsonl\primary_seed_live_audit_<새 ts>.jsonl
```

**합격 기준 (직전 라운드 대비 — docs/88·89 수치가 기준선):**

| 지표 | 직전 | 이번 목표 |
|------|------|----------|
| 1차 LIVE_SUCCESS | 38/40 | **40/40** (ap_news·gdelt 복구; 단 gdelt가 외부 사정 429면 cooldown_skip+기록으로 인정) |
| seed_ready yes | 23 | **≥30** (partial 9 중 selector 4종 + federal_register/igdb/culture_info 승격, hacker_news no→yes) |
| seed_ready no (signal 제외) | 8 | **0** — 시장 수치는 전부 `signal_ready` 라벨 |
| 2차 enrichment 실패 | newsapi 2 + gdelt 2 | **0** (또는 외부 사정 시 cooldown 증거 첨부) |
| Route 1/2 429 시 cooldown 기록 | gap | **100%** (state 파일 발췌로 입증) |

미달 지표는 해당 문서 루프로 복귀 — **이 표가 "1차·2차 소스 전부 제대로 동작해야 턴 종료"의 정량 정의다.**

### 1-4. 문서 동기화

- docs/70: 소스 status 표를 이번 실측으로 전면 갱신 (ap_news/gdelt/newsapi/selector 4종/hacker_news 등 행별 next_action 닫힘 표기)
- docs/71: RISK-T04·S02·S03·S04·S05·Q05 → 닫힘(해결 diff 참조 경로), 신규 발견 리스크 등재
- docs/72: Route 2 위임 아키텍처, structure explorer, 본문 캐스케이드, 09 §3 프레임워크 결정 추가
- docs/73: runner 신설 2종(`run_structure_explorer`, `check_dependency_readiness`) 사용법 + 이 디렉토리 링크
- docs/86·92: trends_explore role/주기, eia 카탈로그 주석 (05·08에서 지시한 갱신 누락 확인)

### 1-5. git 상태 정리 (커밋 준비까지만)

`git status`로 이 라운드의 변경 파일 목록을 확인하고 보고서에 첨부한다. **commit/push는 사용자 명시 요청 전까지 하지 않는다** (CLAUDE.md).

## 2. 최종 보고 형식 (한국어, 이 틀 그대로)

```
① 무엇을 했는가 — 문서 01~09별 1줄 (적용 diff 요약)
② 무엇을 검증했는가 — §1-2 수치, §1-3 표 (직전 대비 개선 수치), 체크리스트 15항 최종 상태
③ WARNING / BLOCKED / UNKNOWN / DEFERRED — 항목·사유·재개 조건
마지막 문장: "15개 항목 중 PASS n / BLOCKED_TERMINAL n / DEFERRED n — (한 줄 결론)"
```

## 3. 이 라운드가 끝나면 (참고 — 작업 금지)

남는 다음 단계는 plans/012 Celery 오케스트레이션이다. 이 라운드의 산출물 중 plans/012가 직접 소비하는 것: ① Route 1/2 모두에서 신뢰 가능한 429→cooldown 영속 ② 전 소스 seed/signal 분류 확정 ③ self-healing 토대(explorer). 이 연결성을 최종 보고의 결론에 1문장으로 언급하라.
