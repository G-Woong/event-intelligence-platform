# 17 — AUTHORITY DISCOVERY & SLM BODY FALLBACK (중기 발견 엔진, 요구1·6)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 🔲 NOT_DONE (NET-NEW) — entity_resolver/authority_source_graph/sitemap_discovery/change_detector/slm_body_fallback 코드 부재.
> │ **구현순위:** #16 (00_ROADMAP_INDEX) · **그룹:** D (신규 NET-NEW)
> │ **검증 근거:** GroundTruth — grep 0건/ls 실패. 토대(content_hash·extractor·source_role)는 APPLIED.
> │ **잔여(미구현):** S4(Entity)·S7(Change Detection)·S10(Authority)·S11(SLM) 전부.
> │ **완료정의(DoD):** S4(entities upsert+앵커+candidate자동병합금지) / S7·S10(앵커→sitemap 정책통과분만·변화없음→skip비용0·candidate 자동활성금지·robots위반0) / S11(캐스케이드 실패시만 호출 1차0+회수율대시보드+graceful None). 전단계 1517 green.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: "닫힌 57소스 목록"은 P1 토대로 살아있으나, 중기 목표는 **소스를 사람이 등록하는 게 아니라 시스템이 발견·검증·승인 후 확장**하는 자기증식 발견 엔진(요구6)이다. 이 레이어는 **엔티티를 1급 영속객체로 승격(Entity Registry)** → **엔티티 앵커에서 권위 소스를 그래프로 발견(Authority Source Graph)** → **sitemap/feed로 신규 변화분만 수집(Sitemap Discovery + Change Detection)** → **본문 식별이 캐스케이드로 실패할 때만 SLM이 마지막 폴백(SLM Body Fallback)** 으로 이어진다. **불변:** 우회·전문저장·투자조언 0. LLM/SLM은 "무엇을·어디서"를 계획·식별할 뿐, fetch는 결정론·정책준수.

---

## 0. 흡수 출처 & 토대 사실 (정직)

| 흡수 출처 | 흡수 범위 |
|---|---|
| `SESSION_CONCEPT_ANALYSIS §11–16` | 개념 J(Entity 1급화)/K(Authority Graph)/L(Sitemap Discovery)/M(Change Detection)/N(SLM Fallback)/O(발견 비용 경계) |
| `IMPLEMENTATION_SPEC §3` | Entity Registry 스키마·해소 전략 |
| `IMPLEMENTATION_SPEC §7` | Authority Discovery 통합 흐름(앵커→표준경로→정책게이트→승인 큐) |
| `IMPLEMENTATION_SPEC §10` | SLM Body Fallback 의사코드·graceful None |
| `MASTER_OVERVIEW §2.1` | 통신서버 SLM(7B) 운용 개념(비개발자 서사) |

**토대(APPLIED — 코드 근거, 재사용 대상):**
- `agents/nodes/baselines.py:98-149` — 결정론 NER baseline(`extract_entities`)·`map_sectors`. **캐시 없음**(매 호출 재계산) → §S7-a 인사이트의 비용 지렛대 근거.
- `ingestion/fetch_strategies/article_body_extractor.py:1-99` — 본문 캐스케이드(`trafilatura → readability → DOM heuristic`, site selector 우선). `_MIN_BODY_CHARS = 200` → §S11 호출 트리거 임계.
- `ingestion/orchestration/source_role.py:33-36` — **7 roles** 고정 enum(ARTICLE_BODY/EXPANSION_SEARCH/OFFICIAL_RECORD/STRUCTURED_SIGNAL/COMMUNITY_EARLY_SIGNAL/ENRICHMENT_ONLY/PERIODIC_EVENT_QUEUE). §S10 role 다양성 게이트의 분류 단일 출처(신규 분류 0).
- `raw_events.content_hash`(SHA-256 UNIQUE) — §S7 norm_hash 폴백의 기존 자산.

**미존재(GroundTruth — grep 0건/ls 실패, NET-NEW 확정):** `entity_resolver` · `authority_source_graph` · `sitemap_discovery` · `change_detector` · `slm_body_fallback`. 이 문서는 **이들을 구현됨으로 적지 않는다.**

---

## 1. Entity Registry (S4 — 1급 영속객체)

엔티티를 카드 부속 문자열(`FinalEventCard.entities: list[str]`)이 아니라 **독립 영속 행**(`entities` 테이블)으로 승격한다. 스키마는 `5_REFERENCE/EVENT_SCHEMA.md` Part2 §Entity(entities 테이블)가 **단일 출처(포인터)** — 본 문서는 중복 정의하지 않는다.

### 1.1 해소 전략 (자동병합 금지)

```text
신규 surface("앤트로픽", "Anthropic PBC") 관측
  → ① 앵커 우선 매칭(external_ids: 공식 도메인 / wikidata QID — 결정론)
  → ② 별칭 정규화(aliases JSONB, baselines.extract_entities 재사용)
  → ③ 모호 시 candidate(status='candidate', 미검수) — 자동병합 절대 금지
```

- **baseline NER 재사용:** 신규 NER 로직을 만들지 않는다. `baselines.extract_entities`(decision: 결정론) 출력을 앵커 매칭 입력으로 쓴다.
- **앵커 매칭:** `external_ids`(공식 도메인·wikidata QID)가 1순위 신뢰 식별자. 앵커가 일치하면 결정론적 동일 판정.
- **candidate 보류:** 앵커 불일치·모호 surface는 `candidate`로 적재만, **자동병합(여러 surface→한 엔티티)은 금지** → 사람 검수 큐(§1.2-b).

### 1.2 활성화 vs 병합 분리 (orchestrator 인사이트 #6)

> **근거:** "활성화"와 "병합"은 위험도가 다르다. 하나로 묶으면 저위험 자동화가 고위험 오병합에 발목 잡히거나, 반대로 고위험을 자동화해 R-FalseMerge를 영속 Event로 전파한다.

| 동작 | 정의 | 위험 | 처리 |
|---|---|---|---|
| **(a) 활성화** | 한 candidate → active(상태 전이) | 저위험 | **결정론 자동승격** 허용 조건: `role 다양성 ≥ 2 권위`(source_role 7종 중 2종+ OFFICIAL/STRUCTURED 등) **AND** change-confirmed 앵커(§S7 변화 확정으로 앵커 검증) |
| **(b) 병합** | 여러 surface → 한 엔티티(merge) | 고위험 | **사람 검수 필수**(자동 금지). Union-Find transitive 오염 = R-FalseMerge 경로 |

> entities.status enum: `active / candidate / merged`(EVENT_SCHEMA Part2 §Entity 권위). 자동승격은 candidate→active만, candidate→merged·active→merged는 사람 게이트.

---

## 2. Authority Source Graph (S10)

엔티티의 **앵커 도메인**에서 출발해 그 도메인이 노출하는 **표준 경로**를 결정론적으로 탐침하고, 정책 게이트를 통과한 후보만 **사람 승인 큐**에 올린다. **자동 활성화 금지.**

### 2.1 발견 흐름

```text
엔티티 앵커 도메인(external_ids.domain, 예: anthropic.com)
  → 표준 경로 탐침(결정론, robots 준수):
       /sitemap.xml · /rss · /feed · /blog · /docs · /legal · /status · /changelog
  → 정책 게이트(기존 SourcePolicyProbe 재사용: robots longest-match · AI크롤러 차단 · paywall/login 마커)
  → 사람 승인 큐(official_sources 노드 후보, status='pending')
  → 사람 승인 시에만 status='active' → 수집 대상 편입
```

- **official_sources 노드 형태:** `{label, url, discovered_via, status}` — EVENT_SCHEMA Part2 §Entity `official_sources` JSONB가 권위.
- **정책 게이트 재사용:** `SourcePolicyProbe`(05 §1, 기존 IMPLEMENTED). 신규 정책 엔진을 만들지 않는다.
- **자동 활성 금지:** 발견≠활성. discovered → pending(사람 큐) → active. AI가 임의로 수집 활성화 못 함(05 §3 "ingestion 실행 경로는 결정적 유지" 원칙 연장).

---

## 3. Sitemap Discovery (S10 일부)

승인된 official_source에서 **신규 변화분만** 수집한다.

```text
sitemap.xml 파싱 → <lastmod> 기준 신규 URL만(이미 본 lastmod 이하 SKIP)
  → robots/rate 준수(우회 금지, rate-limit 하한 clamp)
  → 폴백 체인: sitemap 없음 → feed(/rss·/feed) → 둘 다 없음 → 등록 제외(수집 안 함)
```

- **lastmod 기반 증분:** 전체 재크롤 금지. `lastmod`가 마지막 관측 이후인 URL만 후보.
- **robots/rate 준수:** `rate_limit_policy.yaml`(05) 하한 절대 clamp. 우회·프록시 로테이션·내부 RPC 스크래핑 금지(불변).
- **폴백 결정론:** sitemap→feed→**등록 제외**. 등록 제외는 "포기"가 아니라 정직한 상태(없는 걸 있다고 만들지 않음).

---

## 4. Change Detection (S7 — 비용 지렛대 T1)

이미 본 URL을 다시 폴링할 때 **변화 없으면 수집·LLM 호출 0**으로 끊는다. T1 비용 지렛대.

### 4.1 폴백 체인

```text
ETag(서버 제공) → 일치 시 SKIP(304 의미)
  → 없으면 Last-Modified 헤더 비교
  → 없으면 norm_hash(정규화 본문 해시, content_hash 자산 계열) 비교
변화 없음 → SKIP verdict = 수집 0 · LLM 호출 0
차등 폴링: base_interval / (1 + heat·k), 단 rate-limit 하한 clamp(EVENT_SCHEMA heat 산식 §heat 연동)
```

### 4.2 고도화 — stage별 fingerprint 분해 (orchestrator 인사이트 #1)

> **근거:** Change Detection을 binary(CHANGED/UNCHANGED)로만 두면 "본문은 변했지만 엔티티·섹터는 불변"인 흔한 케이스에서 NER/sector를 **무조건 재계산**한다. `baselines.py:98-149`는 **캐시가 없어**(매 호출 재계산) 이 비용이 그대로 발생한다.

```text
binary verdict 대신 stage별 fingerprint 해시:
  fp_title       = hash(정규화 title)
  fp_entity_span = hash(extract_entities 출력)
  fp_sector      = hash(map_sectors 출력)
  fp_evidence    = hash(evidence_url 집합)
→ 본문 변경이라도 fp_entity_span·fp_sector 불변이면 NER/sector 비용 0(이전 결과 재사용)
```

- 효과: "본문만 미세 수정"(오타·문구) 케이스에서 NER·sector 재계산 0. baseline 캐시 부재 보완.
- 이 fingerprint는 §S7 차등 폴링과 결합돼 T1 비용 지렛대를 stage 단위로 정밀화.

---

## 5. SLM Body Fallback (S11 — 최후 폴백, 1차 아님)

`article_body_extractor` 캐스케이드(`trafilatura → readability → DOM heuristic`, site selector 우선)가 **전부 실패**(본문 `_MIN_BODY_CHARS = 200` 미만)할 때**만** 통신서버 7B SLM을 호출한다.

```text
extract_article_body(html, url)  # 결정론 캐스케이드(article_body_extractor.py)
  → 성공(≥200자) → 그대로 사용, SLM 호출 0
  → 전부 실패(<200자) → 통신서버 SLM(7B) 호출 = LAYER F 최후 폴백
       · 역할: 본문 영역 "식별"만(fetch는 이미 결정론으로 끝남 — 우회 없음)
       · 전문 저장 금지(raw_text 본문 미저장 불변 유지 — raw_events.raw_text "본문 저장 금지")
       · 실패 시 graceful None(예외 전파 금지, 카드 degrade)
```

- **1차 아님:** SLM은 **결정론 캐스케이드가 모두 실패한 후에만**. 1차 호출(우회·전수 SLM 추출)은 금지 = LLM/SLM은 크롤러가 아니다(ADR#14 LAYER F).
- **우회 없음:** fetch는 결정론 단계에서 이미 완료(정책·rate 준수). SLM은 가져온 HTML에서 본문 영역을 식별할 뿐, 새 네트워크 호출·우회 없음.
- **전문저장 금지:** SLM이 식별해도 전문은 저장하지 않는다(raw_events.raw_text 본문 저장 금지 불변 — EVENT_SCHEMA Part1).
- **graceful None:** SLM 미설정(`SLM_BODY_FALLBACK_URL=""`=off)·실패 시 None 반환, 카드는 본문 없이 degrade(BLOCKED 아님).

---

## 6. 발견 비용 경계 (adversarial 인사이트 #3 — R-DiscoveryCostStarvation)

> **근거:** Change Detection의 비용 절감은 **last_state가 있는 안정 소스 재폴링에만** 적용된다. Authority Discovery(자기증식)가 매일 신규 엔티티/소스를 발견하면 **신규 URL은 last_state 부재 → 항상 CHANGED → LLM triage**. cold-start 신규 소스는 Change Detection 미적용 구간이다. heat 백프레셔는 "순서"만 조절(heat 알려면 일단 봐야 함=닭-달걀), 총량을 줄이지 못해 발견 triage가 월 예산을 통째 소진 → 핵심(고heat Event 확장) 예산이 굶는다.

**경계(closure):**
1. **발견 입구 일일 쿼터** — `DISCOVERY_DAILY_APPROVAL_QUOTA`(EVENT_SCHEMA Config, 기본 0=발견 off). 신규 승인 후보 일일 상한.
2. **cold triage 저가 사전필터** — cold-start 신규 URL은 LLM triage 전에 **결정론/SLM 저가 사전필터**(role 다양성·앵커 일치 결정론 체크)로 거른 뒤에만 LLM 호출. 신규 발견당 초기 triage 상한.
3. budget 3축화(per-event + 월 + 신규 발견당 초기 triage 상한)는 06/19의 budget guard와 연동.

---

## 7. Entity Dossier (BI 인사이트 #3 — SEO 롱테일)

> **근거:** 엔티티가 1급 영속객체가 되면 `/entity/{id}` 영구 랜딩이 가능하다. 이는 **SEO 롱테일 영구 자산**(특정 기업·규제·인물 사건 이력 페이지)으로, ADR#15 트래픽×광고 모델의 검증된 트래픽 증폭 표면이다.

- `/entity/{id}` — 엔티티별 사건 이력 타임라인 + 연결 Event(primary_entity_ids 역참조) 영구 랜딩.
- **게이트:** **앵커 확정**(external_ids 검증된 active 엔티티) **AND N건 이상**(사건 N건+ 누적) 엔티티만 노출 — 빈약/미검수 candidate는 랜딩 생성 금지(저품질 SEO·오정보 방지).
- 불변: 전문 재배포 아님(요약+증거링크+타임라인=파생 콘텐츠, ADR#15 §3.4). 투자조언 0.

---

## 8. 위험 (RISK_REGISTER 권위)

| 위험 | 연결 | 본 레이어 완화 |
|---|---|---|
| **R-DiscoveryCostStarvation** | Authority Discovery cold triage 비용 | §6 일일 쿼터 + cold 사전필터 |
| **R-LLMCollectBoundary** | LLM/SLM 수집 관여 우회·rate·비용 | §2 정책게이트 + §5 LAYER F 최후폴백·우회 0 |
| **R-FalseMerge** | candidate 병합 transitive 오염 → 영속 Event | §1.2 활성화/병합 분리·병합 사람 게이트 |
| **R-EventModelMigration** | entities 테이블 추가 정합성 드리프트 | 신규 컬럼 nullable·additive·1517 green |

> 위험 권위는 `docs/_RISK/RISK_REGISTER.md`. 결정 논리는 `docs/_DECISIONS/2026-06.md` ADR#14. 본 표는 포인터.

---

## 9. UNKNOWN (구현 전 확정 불가 — 정직 표기)

1. SLM Body Fallback 통신서버 인프라/모델 size·비용 (00_INDEX §6 UNKNOWN-1).
2. candidate 자동승격 임계(role 다양성 ≥2의 "권위" 정의 — source_role 7종 중 어떤 조합).
3. Change Detection norm_hash 정규화 함수의 도메인별 노이즈 허용폭.
4. Entity Dossier "N건 이상" 게이트의 N 값(SEO 품질·오정보 트레이드오프).
5. 차등 폴링 `k` 계수 실측(EVENT_SCHEMA heat 산식 §heat와 공유 미정).

---

## 10. 상호참조

- **상위 지도/순위:** `docs/2_ROADMAP/00_ROADMAP_INDEX.md`(순위 #16, 그룹 D · §4 임계경로 S7/S10/S11)
- **자매 NET-NEW(5대 자산 스펙):** `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md`(S4·S7·S10·S11 의사코드·alembic·테스트 — NET-NEW, 00_INDEX 순위 #17)
- **발견 토대(IMPLEMENTED):** `docs/2_ROADMAP/05_DISCOVERY_AND_SOURCE_EXPANSION_LAYER.md`(SourcePolicyProbe·registry 57·정책게이트)
- **스키마(단일 출처):** `docs/5_REFERENCE/EVENT_SCHEMA.md` Part2 §Entity / §EvidenceNode / §heat / §Config
- **결정:** `docs/_DECISIONS/2026-06.md` ADR#14(LLM 수집 P/G/F 경계)
- **위험:** `docs/_RISK/RISK_REGISTER.md`(R-DiscoveryCostStarvation / R-LLMCollectBoundary / R-FalseMerge / R-EventModelMigration)
- **구현 사실(권위 정점):** `docs/_CANONICAL/*` — 본 문서는 ROADMAP(미래계획)이지 현재 사실이 아니다.

> **불변:** 미구현을 구현됨으로 적지 않는다. 우회·전문저장·투자조언·`.env` 불변. 모든 단계 비파괴·1517 green·robots 위반 0.
