# RISK CLOSED (완전 종결 위험 — 흐름만)

> 종결조건(Closure)이 **충족되어 닫힌** risk 만 여기에 둔다. **상세 본문은 남기지 않는다** —
> "왜 위험이었고 어떻게 닫혔나"를 흐름 1~3줄로만 보존하고, 상세는 `docs/_ARCHIVE_SUPERSEDED/` 로 archive.
> 열린/부분종결 risk 는 `RISK_REGISTER.md`. 이 분리는 매 턴 `turn-closeout` 이 관리한다(`docs/Harness_Construction/04`).

형식(예시 — 실제 항목은 `###`로 시작):
```
R-<id> · <제목>  — CLOSED (날짜)
- 종결 근거: (코드 path / 테스트 / 정책)
- 흐름: (열림→완화→종결까지 1~3줄)
- 상세: docs/_ARCHIVE_SUPERSEDED/<원본> (있으면)
```

---

### R-SourceTypeFidelityGate · 비뉴스/약신호 cross-source 발행 fidelity gate  — CLOSED (2026-06-23 · ADR#33/#34/#35/#36/#37)
- 종결 근거: 경로 B(Event 타임라인/event_resolver)에 source-type 발행 정책 5겹 — ①**publish gate**(ADR#33 `resolve_routing` `member_source_types`+`ACTION_WITHHELD`: publishable(official/article) 0이면 WITHHELD — pure community/search/structured 단독 발행 차단, 투자조언 경계 S6 포함) ②**primary-authority**(ADR#34 `candidate_from_cluster`: 최고 authority source 가 Event 대표 — community/market 대표화 차단) ③**held-dedup+fail-closed**(ADR#35: 대표 record held 이중등장 제거 + source_type 미지/누락→WITHHELD 조용한 우회 차단) ④**강신호 core-policy**(ADR#36: 강신호 cluster 는 강신호 core(distinct−weak_only)에서만 primary/gate — weak_only publishable 로 발행/대표화 금지) ⑤**약신호 동질-publishable 정책+입력순서 불변 core**(ADR#37 `_homogeneous_publishable`: 약신호는 동일 publishable type(news+news)만 저신뢰 발행·혼합(official+news)/비-publishable WITHHELD — authority 상향 weak-primary 차단; `primary_root`=최대 강성분→동률 publishable 우선·`members` 키 정렬 → core/cluster_id 입력순서 불변). 테스트: 단위(resolver gate·core-policy·약신호 gate 6·입력순서 불변 3·drift 계약) + live-PG(약신호 WITHHELD/발행·강신호 core WITHHELD). evidence source_type 끝까지 보존. adversarial **2-pass JUSTIFIED**(1차 OVERCLAIM→P2-1 동질 gate·P2-2 publishable-우선 tie-break 수정→2차 JUSTIFIED).
- 흐름: type-blind resolver 가 비뉴스 cross-source(S5/S6/S7)를 발행 → ADR#33 publish gate 로 pure-비뉴스 차단(부분종결) → #34 authority 대표·#35 held-dedup/fail-closed·#36 강신호 core-policy 로 강신호 weak-primary 보수 해소(LOW 부분종결) → #37 약신호 동질-publishable gate(혼합 weak-primary 차단·동질은 저신뢰 표시) + 입력순서 불변 core/gate(fragility·cluster_id split 해소)로 잔여 2개(약신호 weak-primary·fragility) 종결 → adversarial JUSTIFIED.
- 잔여(비차단, 별개 RISK): held event 중복/승격 정책은 **R-FalseMerge**(open)로 추적. 실 cross-source 비뉴스 Event·실 fetch APPEND 미관측은 **R-RealSourceLoopUnproven**(open). news+news 약신호 단일 news primary 는 authority 상향 없음+delta 저신뢰 표시("…같은 사건으로 추정됩니다")로 수용.

### R-EventTimelineRenderHardening · Event 타임라인 렌더 보강(에러표현·내부식별자·delta_summary 가시성)  — CLOSED (2026-06-23)
- 종결 근거: ①(ADR#26) page/전역 `error.tsx` 일반화 — 비-404 raw 에러 미노출. ③(ADR#26) `Public*` 스키마(`api/events.py`)가 내부 식별자(source_refs·primary_entity_ids·snapshot_card_id) wire 구조적 제외. ②(ADR#30+#31) delta_summary 디버그 라벨→`build_delta_summary` 자연어 + `apply_routing` CREATE **genesis update**(`event_timeline_service.py`)로 CREATE-only Event 의 빈 상세 해소. 실 파이프라인 CREATE→`/events/timeline/{id}` 화면에 genesis 자연어("뉴스 보도가 동일 식별자로 확인된 사건입니다.")+evidence 링크 렌더 **1회 관측(Playwright)**. 테스트: 불변식 의존 21단언 의도적 갱신(backend 268 green, live-PG 21 포함) + frontend timeline.test.mjs 12 green.
- 흐름: ①③ 은 실데이터 비의존 메커니즘으로 ADR#26 종결 → ② delta_summary 는 ADR#30 에서 코드 자연어화했으나 adversarial P1-1 이 "실 Event 는 CREATE-only(update 0) 라 화면 미도달"을 지적(부분종결 환원) → ADR#31 이 CREATE clean-win 에 genesis update 1행 추가(불변식 "CREATE는 update 0" 의도적 개정, 마이그레이션 0)해 자연어가 update 행→public API→화면에 실제 도달함을 브라우저로 관측하여 ② 종결(단 관측은 **synthetic 강신호 record** — 실 네트워크 fetch genesis 렌더는 R-RealSourceLoopUnproven 로 추적) → ①②③ **render 메커니즘** 종결.
- 잔여(비차단): 실 네트워크 fetch APPEND 의 화면 자연어는 R-RealSourceLoopUnproven 으로 추적(본 종결은 render *메커니즘*; 실 fetch 커버리지는 별건). 화면 관측은 synthetic 강신호 record(distinct 1 → "보도가 동일 식별자로 확인" 문안).

### R-EventSinkDbTarget · 운영 결선/seed 가 의도치 않은 DB(dev/prod)에 Event 영속  — CLOSED (2026-06-23)
- 종결 근거: `backend/app/tools/db_target.py`(`assert_safe_write_target` — **2중 fail-closed**: ① APP_ENV **allowlist**(dev/test 만 무명시 허용 → staging/production·오타·미지 환경 모두 거부; denylist 의 fail-open 회귀 차단), ② **DATABASE_URL dbname prod 마커 교차검증**(APP_ENV=dev 오설정 + URL→prod 우회 차단 — APP_ENV 단일 신뢰 회피); `--allow-non-dev-db` 명시 opt-in 으로만 우회; `target_db_label` host:port/dbname 자격증명 제외). seed(`seed_event_timeline`)·runner(`run_event_orchestration._target_db_label`) 동일 출처 공유. 테스트 `backend/tests/test_seed_event_timeline.py`(dev/test 허용·staging/prod·오타 env 거부·dev+prod dbname 거부·override·자격증명 미노출 + CLI 실증).
- 흐름: D-1 sink 가 settings.DATABASE_URL 로 전용 엔진 생성 → 잘못된 환경에서 켜면 오영속 가능, 완화는 "대상 DB 출력(보임)"뿐이고 구조적 차단 부재 → D-2c 에서 APP_ENV allowlist + dbname prod-마커 교차검증 fail-closed 가드 추가로 "보임→차단" 승격·종결(adversarial: APP_ENV 단일 신뢰는 dbname 교차검증으로 보강).
- 잔여(LOW, 비차단): prod 마커 없는 DB명 + APP_ENV 오설정이 동시 발생하는 극단 케이스는 휴리스틱 밖 — 배포 환경변수 규율이 최종 방어선(R-Auth 동일 한계). 심층 prod 토폴로지 탐지는 범위 밖.

### R-HookOutputEncoding · Stop hook 한글 출력 깨짐(cp949 stdout)  — CLOSED (2026-06-19)
- 종결 근거: `turn_state_snapshot._nudge_message`(ASCII-safe 영문)+`json.dumps`(ensure_ascii=True), harness CLI 4종(`harness_doctor`/`dead_code_scan`/`docs_lifecycle_audit`/`closeout_sig`) stdout UTF-8 reconfigure. 테스트 `tests/test_harness_hooks.py`(`test_nudge_message_is_ascii`/`test_stop_hook_stdout_is_ascii`/doctor crash 회귀).
- 흐름: Stop feedback 한글이 cp949 stdout에서 mojibake(`����`)→운영성 실패 → nudge를 ASCII 영문화 + CLI 스크립트 UTF-8 reconfigure(doctor의 em-dash crash 포함) → stdout이 순수 ASCII로 디코드(깨짐 불가) 검증.

### R-CodeReviewLivePath · 일반 코드 변경 턴 `/code-review` 실호출·증거 적재  — CLOSED (2026-06-19)
- 종결 근거: harmless ingestion 변경(`ingestion/core/source_registry.py` 주석)→`audit_flagger` `code_review` flag 발생→**`/code-review` 스킬 라이브 실호출**→CRLF churn 1건(`scripts/harness_doctor.py`) 적발→수정. 결과를 `closeout_stamp.audit_evidence`(code_review) 적재.
- 흐름: flag/게이트만 관찰(미검증)→실제 코드턴에서 skill end-to-end 실행·finding·fix·evidence 적재 1회 관찰로 종결. 잔여 한계는 R-CloseoutTrust(evidence 자기보고)로 흡수.

### R-EnvLoadAsymmetry · 엔트리포인트 간 .env 로딩 비대칭  — CLOSED (2026-06-22)
- 종결 근거: `run_one_source.run_source()`(run_one_source/run_phase/run_all_phases 공통 funnel) + `run_production_orchestration.main()` 에 명시적 `load_env()`(idempotent setdefault) 배선. 테스트 `ingestion/tests/unit/test_entrypoint_env_bootstrap.py`(run_source가 load_env 호출 + 키 보유 시 opendart precheck None / 부재 시 NEEDS_API_KEY). 값 비노출(존재 여부만).
- 흐름: production 경로는 audit_api_key_readiness 부수효과로 정상이나 run_one_source/run_phase는 .env 미로드 → 키 보유 소스가 NEEDS_API 오판 → 진입부 load_env 배선 + 계약 테스트로 대칭화·종결(ingestion 1307 green).

### R-GdeltMainLoopResume · rate-limited 소스 메인루프 auto-resume 부재  — CLOSED (2026-06-22)
- 종결 근거: `production_state.decide_production_strategy(now=)` 가 `RESUMABLE_RATE_LIMIT_STATES`(EXTERNAL_RATE_LIMITED/COOLDOWN)의 cooldown(`_cooldown_elapsed`; memory→`cooldown_until` 파생) 만료 시 not_ready skip 면제→재probe. 429는 run_production_orchestration에서 rate_limited(실패 아님)로 분류 유지. 테스트 test_production_state/scheduler/orchestration_runner.
- 흐름: gdelt가 EXTERNAL_RATE_LIMITED에 영구 정체(메인 not_ready skip, 전용 closure 단일 의존) → 메인 플래너에 cooldown 만료→재probe 전이 추가(우회 0, 429=외부제한) → cooldown 경과 시 메인루프가 자동 재시도하며 종결.

### R-GdeltGovernorSplitBrain · gdelt host rate-limit governor 이중 상태(메인루프 vs closure)  — CLOSED (2026-06-22)
- 종결 근거: 신규 `ingestion/orchestration/host_rate_gate.py`(`HostRateGate` — host 키 단일 출처, file-backed `host_rate_gate.json`, decide/record 시 파일 재읽기로 cross-process 가시성, `record_call` 호출 직전 즉시 atomic 영속). gdelt host 3경로(`run_production_orchestration`·`run_final_source_closure`·`run_last_chance_source_resurrection`)가 동일 gate 공유. source-level governor(메인 900s / closure 10s) 의미 보존 + host floor만 추가(우회/병렬/tight-retry 0). 테스트 `ingestion/tests/unit/test_host_rate_gate.py`(8): 공유 가시성·spaced-probe ladder 보존·메인 cooldown 자동재개 보존·호출직전 last_call 기록(성공/실패 무관)·spacing 전 양경로 미호출·후 호출 가능·429=외부 provider rate limit. ingestion 1315 green.
- 흐름: 두 루프가 별도 governor 파일로 gdelt host cooldown을 각각 추적 → R-GdeltMainLoopResume 종결로 메인루프도 재probe하게 되어 동시가동 시 host 호출 교차 가능 → host 키 단일 출처 gate를 실제 호출 직전에 양 경로가 통과(record 즉시 영속)하도록 배선 → 한 루프의 호출을 다른 루프가 즉시 보고 spacing 내 호출을 막아 종결.

