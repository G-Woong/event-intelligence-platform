# 04 — RISK 수집·등록 (Req 4)

> 진행 중 발생한 에러·dead code·아이디어/상용화/논문 관점 risk를 **별도 폴더에 모아** 매 턴 감사로 갱신.
> Req 1·2의 영향을 받음: 동기화 + 적용 완료 시 흐름만 남기고 통폐합/이동.

---

## 1. 위치·구조 (별도 폴더)  · rev2 — R3 단일출처 위반 해소

기존 `docs/_CANONICAL/05_RISK_REGISTER.md`(이미 존재)를 **본문 통째 이동**(포인터+본문 이중화 금지):

```
docs/_RISK/
  RISK_REGISTER.md   ← 열린/부분종결 risk (severity·종결조건). 권위 단일 출처.
  RISK_CLOSED.md     ← 완전 종결 risk: "진행 흐름" 1~3줄 + 종결 근거만 (상세 본문은 archive)
  _INDEX.md          ← (선택) id·severity·상태 한 줄 요약 표
```

- **왜 본문 통째 이동(R3):** `_CANONICAL/00 §2` 권위 정점이 `_CANONICAL/*` 이고 00 의 읽기표·"비개발자 00→03→05→07" 등 **다수 포인터가 05 를 직접 가리킨다.** 본문은 `_RISK/` 로 옮기고 **`_CANONICAL/00` 의 링크·읽기순서를 새 경로(`docs/_RISK/RISK_REGISTER.md`)로 갱신**한다. `_CANONICAL/05` 에 **stub(포인터)을 남기지 않는다** — 본문 한 곳 + 인덱스가 그 한 곳을 가리키는 단일출처 불변식 유지. (포인터+본문 이중화는 `R-StaleDocs` 가 경고하는 드리프트를 재생산하므로 금지.)
- **3상태 규칙(부분 종결 처리):** 기존 R-Integration·R-MockCard·R-Auth 처럼 `HIGH→MED→LOW` 부분 종결 이력을 한 항목에 누적한 risk 가 있다. open/closed 이분법으로 못 가르므로:
  - **열림(open):** Closure 미충족 → `RISK_REGISTER.md`.
  - **부분종결(partial):** severity 하향됐으나 Closure 미충족 → `RISK_REGISTER.md` **유지**, 종결 이력은 **1줄 요약 + archive 링크**로 압축(본문 비대화 방지).
  - **완전종결(closed):** Closure 충족 → `RISK_CLOSED.md` 로 흐름 1~3줄만, 상세 본문은 `_ARCHIVE_SUPERSEDED`.
- **gitignore 안 함**(자산 — 하네스 구축 기초).

---

## 2. risk 항목 형식 (기존 05 형식 계승 — 검증됨)

```markdown
### R-<짧은id> · <제목>  — Severity: HIGH|MEDIUM|LOW (상태/일자)
- Area: (영역)
- Description: 무엇이 위험한가
- Evidence: 근거 path 또는 산출물
- Current mitigation: 현재 완화책
- Remaining gap: 남은 격차
- Closure: 종결조건(이게 충족돼야 닫힌다)
```
> RISK ≠ TODO. **종결조건 충족 시에만 닫힌다**(기존 05 규칙 유지).

---

## 3. risk 출처 (매 턴 감사로 수집)

| 출처 | 누가 탐지 |
|---|---|
| 진행 중 에러/테스트 실패 | 훅(`turn_state.json`의 test fail) + 스킬 |
| dead code / 미사용 심볼 | 스킬(grep) + `02 A.4` 판정과 연동 |
| 팀 감사 REAL 이슈 (`03`) | 메인 에이전트(감사 종합) |
| 상용화/논문/아이디어 관점 | 해당 도메인 에이전트(commercialization-strategist 등) 트리거 시 |
| 보안/법무 | security-permission-guardian / legal-safety-compliance-reviewer |

---

## 4. Req 1·2와의 연동 (동기화 + 통폐합)

- **Req 1 연동:** 매 턴 `PROJECT_STATUS.md` MACHINE 블록에 `열린 RISK 카운트(severity별) + 신규/종결`을 훅이 자동 집계. 신규 식별 risk 요약은 서술부 `⚠️` 섹션에.
- **Req 2 연동(코드기반 동기화 = 핵심):** 매 턴 감사에서 **risk의 종결조건이 코드/산출물로 충족됐는지 grep 검증**.
  - 충족 → `RISK_REGISTER.md`에서 제거하고 `RISK_CLOSED.md`에 **흐름 1~3줄 + 종결 근거**만 이관(통폐합). 상세 본문은 `_ARCHIVE_SUPERSEDED`로.
  - 즉 **"적용 완료된 risk가 열린 목록에 찌꺼기로 남는 것"을 매 턴 차단** (user 요구 직격).
- **이동은 `03` 팀 감사(특히 risk 종결 트리거) 통과 후 확정** — 단독으로 risk를 닫지 않는다(긍정편향 방지).

---

## 5. 매 턴 감사 절차 (스킬이 수행)
```
1) turn_state.json 의 test/secret/변경영역 읽기
2) RISK_REGISTER.md 의 각 열린 risk Closure 조건을 코드 grep로 검증
3) 충족된 risk → CLOSED 이관 후보 표시 (확정은 팀 감사)
4) 이번 턴 신규 risk 식별(에러·dead code·감사 결과) → 등록
5) 카운트를 PROJECT_STATUS.md MACHINE 에 반영(훅과 일치 확인)
```
