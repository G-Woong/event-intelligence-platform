# 05 — DISCOVERY & SOURCE EXPANSION LAYER (L1)

> 결론: 병목은 "소스 발견"이 아니라 **품질·정책·배선**이다. connector를 100개 더 붙여도 P0(A→B)가 안 뚫리면 PG row는 0이다. 소스 수는 허영 지표다.

---

## 1. 현재 상태 (IMPLEMENTED, 코드 근거)

- `source_registry` 57소스 단일 선언. `SourceCapability`(능력 선언) → `StrategyGraph`(안전 전략 빌드, `UNSAFE_STRATEGIES` 11종 reject) → `EvidenceGate`(shape 린터) → `CommunityCorroborationGate`(dcinside 봉인).
- `SourcePolicyProbe`: robots longest-match, AI 크롤러 토큰 차단, paywall/login 마커.
- `SourceStrategyMemory`: 소스별 `successful_strategy`/`failed_strategies`/`llm_agent_hints` 누적, `preferred_strategy_for`/`is_known_dead_end`.
- `derive_production_state` total function(UNKNOWN=0), `SCHEDULABLE_STATES` 분리. rate governance(`rate_limit_policy.yaml`).

## 2. 한계 / 갭

| 갭 | 근거 | 영향 |
|---|---|---|
| **A→B bridge db_writer 미주입(P0)** | `bridge_to_raw_events.py` db_writer=None | seed가 PG에 미도달, mirror만 |
| EventQueue Redis 미배선 | `event_queue.py` `_redis_*` NotImplementedError | 멀티워커 공유 큐 부재 |
| 단발 LIVE_SUCCESS를 READY로 계상 | registry status 근거 | READY 46 과대평가 위험 |
| SourceCapability 4소스만 선언 | 53소스 미선언 | 라우팅 입력 불완전 |
| discovery↔ingestion 경계 미문서화 | — | 책임 혼선 |

## 3. 목표 / 구현방향

1. **P0: bridge에 db_writer 주입** — workers POST 경유로 raw_events PG 적재. mirror→DB 전환. (acceptance: ingestion seed 1건 PG row 확인)
2. **지속 검증** — 단발 probe를 `PROBED_ONLY` 중간 등급으로 두고, 2회+ 연속 성공 시 READY 확정.
3. **discovery 분리** — `source_policy_probe` 기반 신규 고신호 소스 후보 자동 평가(robots/ToS 사전판정 → 점수화 → registry 제안). ingestion 실행 경로는 결정적 유지.
4. **capability 확장** — schedulable 소스 전부 SourceCapability 선언.
5. **고신호 공식 소스 우선** — SEC EDGAR(무료/무키, 10 req/s, UA 필수), OpenDART, Guardian, federal_register. 직접 크롤링 소스는 차단·법무 리스크 후보.

## 4. 비용 / 위험

- 비용: 공식 API 위주는 거의 무료(SEC/OpenDART/GDELT/federal_register). 유료 검색·뉴스 API는 L2에서 통제.
- 위험: dcinside ToS UNVERIFIED(수집 닫고 publish 봉인 유지), gdelt scheduled 429(우회 금지·cooldown), POLICY_EXCLUDED 9 영구 제외, 단발 probe 과신.

## 5. LLM SourceSupervisor 역할 (미래)

- 코드 작성이 아니라 **결정적 레일 위의 제안자**: `reject_unsafe`로 우회 제안을 거른 뒤 allowed registry 안에서만, `llm_agent_hints`를 읽어 제안. discovery 후보 점수화에만 관여, ingestion 실행은 결정적.

## 6. 검증기준 (완전 달성)

(1) A→B bridge db_writer 주입 → seed 1건+ raw_events PG 적재, (2) schedulable 소스 capability+graph 100% 선언, (3) LIVE_SUCCESS 2회+ 지속검증으로 READY 확정, (4) 모든 우회 전략 빌드/제안 시 reject + secret scan 키 0건.
