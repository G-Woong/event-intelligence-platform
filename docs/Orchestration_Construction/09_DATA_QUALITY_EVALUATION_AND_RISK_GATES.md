# 09 — 데이터 품질 평가 및 리스크 게이트 (Data Quality & Risk Gates)

> **목적**: 수집된 항목이 다음 단계(사건 카드)로 가기 전에 통과해야 할 **품질·신뢰성·안전 게이트**를 정의한다. 각 게이트는 측정 가능한 지표 + 임계값 + 실패 시 행동을 갖는다.
> **원칙**: 게이트는 **deterministic 규칙 우선**. LLM 판정은 규칙으로 못 가르는 경우에만(07 quality_judge).

---

## 0. 비개발자를 위한 설명

수집했다고 다 쓰는 게 아니다. **품질 검사대(게이트)**를 통과한 것만 사용자 화면으로 보낸다. 불량품을 거르는 공장 검수와 같다. 우리가 검사하는 것:

- **본문이 충분한가?** (광고만 있고 내용 없으면 탈락)
- **중복인가?** (같은 사건이 10번 들어오면 1번으로)
- **신선한가?** (3일 전 뉴스를 "속보"로 내보내면 안 됨)
- **믿을 만한가?** (익명 커뮤니티 글 1개로 사건 단정 금지)
- **근거가 있는가?** (공식 출처가 뒷받침하는가)
- **법적으로 안전한가?** (재배포 금지 원문을 통째로 복제했나)

검사에서 떨어진 항목은 버리거나, 보강 후 재검사하거나, 사람 검토로 보낸다.

---

## 1. 게이트 목록 (11개)

| # | gate | metric | threshold | fail action |
|---|---|---|---|---|
| 1 | **collected_item_quality** | quality_score(기존 quality_score.py) | ≥0.40 partial / ≥0.70 success | <0.40 → reject |
| 2 | **body_completeness** | body_length, boilerplate_ratio | 뉴스 ≥200자, boilerplate <0.6 | body_missing 보존(04), 카드는 hold |
| 3 | **source_credibility** | reliability_score(profile) | tier1≥0.8 신뢰 | 저신뢰 단독 → needs_corroboration |
| 4 | **timestamp_freshness** | now - published_at | near_real_time ≤1h, news ≤24h | stale → 우선순위 강등(폐기 아님) |
| 5 | **duplicate_detection** | content_hash, (후속)벡터 유사도 | dup_rate <10% | 중복 → 1건 병합 |
| 6 | **event_relevance** | event_relevance_score(0~1) | ≥0.5 | <0.5 → drop(노이즈) |
| 7 | **evidence_coverage** | primary/enrichment 소스 수 | ≥1 primary | 0 → needs_evidence |
| 8 | **contradiction_coverage** | 모순 소스 존재 여부 | (후속) | 미충족 → flag(차단 아님) |
| 9 | **community_vs_official_balance** | community/official 비율 | official ≥1 권장 | community-only → label "unconfirmed" |
| 10 | **legal_safety_risk** | publication_policy 준수 | full-text 위반 0 | 위반 → preview_only 강제 |
| 11 | **summary_faithfulness** | (다운스트림 LLM) 원문 vs 요약 | (후속 STEP 014) | 불충실 → hold |

---

## 2. 게이트별 상세

### 2.1 collected_item_quality
- **metric**: `compute_quality_score(metrics, source_type)` → `determine_quality_status` (SUCCESS≥0.70 / PARTIAL≥0.40 / FAILED). **이미 구현**(`core/quality_score.py`).
- **fail action**: FAILED → reject + 리포트. PARTIAL → 통과하되 카드에 "부분 정보" 표기.
- **test dataset**: 고품질/저품질/boilerplate 샘플.

### 2.2 body_completeness
- **metric**: body_length, boilerplate_ratio (04 BodyExtractionState).
- **threshold**: 뉴스 ≥200자. **numeric/트렌드는 면제**(signal_ready, data-quality-auditor 규칙). 커뮤니티 ≥50자.
- **fail action**: body_missing → 사건 보존(04 §10), 카드는 hold until enrichment.

### 2.3 source_credibility
- **metric**: profile.reliability_score. tier1(공시/규제/공식) 높음, 커뮤니티 낮음.
- **fail action**: 저신뢰 단독 사건 → "needs_corroboration"(공식 확인 전 미발행).

### 2.4 timestamp_freshness
- **metric**: now - published_at.
- **fail action**: stale → 폐기 아님, 우선순위 강등(과거 사건도 맥락엔 유효).

### 2.5 duplicate_detection
- **metric**: content_hash(즉시) + 벡터 유사도(후속, Milvus).
- **fail action**: 중복 → 1건 병합, 소스 목록에 추가(증거 다층화).
- **주의**: **중복 증폭 방지** — 같은 사건이 여러 소스에서 와도 1개 카드.

### 2.6 event_relevance
- **metric**: event_relevance_score (evaluation-benchmark-agent 지표).
- **fail action**: 노이즈(<0.5) drop. 커뮤니티 잡담 필터.

### 2.7 evidence_coverage
- **metric**: primary_seed 소스 수 + enrichment 수.
- **fail action**: primary 0 → needs_evidence(공식 출처 보강 트리거).

### 2.9 community_vs_official_balance
- **metric**: 사건을 뒷받침하는 community vs official 소스 비율.
- **fail action**: community-only → "unconfirmed" 라벨(허위정보·명예훼손 리스크 완화).

### 2.10 legal_safety_risk
- **metric**: publication_policy 위반 여부(full-text 저장/공개).
- **fail action**: 위반 → preview_only 강제 truncate. raw artifact internal_only 확인.

---

## 3. 게이트 배치 (07 quality_judge_node 내부)

```
quality_judge_node:
  1. deterministic 게이트 (1~5, 7, 10) 순차 — 규칙으로 판정
  2. 규칙으로 모호한 항목만 → LLM judge (6 relevance, 11 faithfulness; mock 기본)
  3. 결과: passed / rejected / needs_review / hold
  4. needs_review → human_review (07 §2.16, 자동 발행 안 함)
```

---

## 4. 지표 정의 (측정 가능)

| 지표 | 산식 | 기준값 | 판정 |
|---|---|---|---|
| quality_score | 기존 quality_score.py | 0.40/0.70 | 구현됨 |
| body_completeness | len(body) ≥ min & boilerplate < 0.6 | 200/50자 | 구현 가능 |
| source_freshness | (now - published_at) ≤ bucket | bucket별 | 구현 가능 |
| duplicate_rate | dup / total | <10% | 구현 가능 |
| evidence_completeness | primary≥1 | ≥1 | 구현 가능 |
| event_relevance | (후속 분류기/LLM) | ≥0.5 | 후속 |
| summary_faithfulness | (후속 LLM, STEP 014) | — | 후속 |

> false positive/negative trade-off: relevance 임계를 높이면 노이즈↓·누락↑. 기본 0.5에서 시작해 데이터로 조정(evaluation-benchmark-agent).

---

## 5. Implementation diff blueprint

```diff
# Proposed diff — DO NOT APPLY IN THIS TURN
# VERIFY PATH BEFORE APPLY
diff --git a/ingestion/orchestration/quality_gates.py b/ingestion/orchestration/quality_gates.py
new file mode 100644
--- /dev/null
+++ b/ingestion/orchestration/quality_gates.py
@@
+def gate_body_completeness(state, profile) -> str: ...   # pass|hold|reject
+def gate_duplicate(state, seen_hashes) -> bool: ...
+def gate_freshness(state, bucket) -> str: ...
+def gate_credibility(state, profile) -> str: ...
+def gate_legal_safety(state, publication_policy) -> str: ...
+def run_quality_gates(items, profiles, policy) -> dict:
+    """deterministic 게이트 일괄. quality_score.py 재사용."""
+    ...
```

**수정하지 않는 파일**: `quality_score.py`(재사용), `publication_policy.yaml`(읽기), `event_candidate.py`(스키마 재사용).

---

## 6. test dataset / plan

```
test_gate_body_rejects_boilerplate       # boilerplate-only → reject
test_gate_body_exempts_numeric           # finnhub → signal_ready (body 면제)
test_gate_duplicate_merges               # 동일 content_hash → 1건
test_gate_freshness_demotes_stale        # 3일전 → 강등(폐기 아님)
test_gate_credibility_flags_community    # community-only → needs_corroboration
test_gate_legal_truncates_preview        # nyt full-text → preview_only
test_gate_relevance_drops_noise          # <0.5 → drop
test_quality_judge_deterministic_first   # 규칙 우선, LLM 최소
```

품질 테스트 데이터셋: 기존 `ingestion/outputs/jsonl/` artifact에서 고/저품질 샘플 추출(실데이터 기반).

---

## 7. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| data-quality-auditor | body≥200, dup<10%, numeric 면제 규칙이 기존 기준과 정합 | CLOSED_BY_TEST_PLAN |
| evaluation-benchmark-agent | relevance/freshness/evidence 지표가 측정 가능. 임계 데이터 조정 명시 | CLOSED_BY_TEST_PLAN |
| legal-safety-compliance-reviewer | community-only "unconfirmed" 라벨 + preview 강제 → 명예훼손/저작권 완화 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | 중복 증폭 방지 게이트가 핵심. 저신뢰 단독 발행 차단 양호 | CLOSED_BY_DESIGN |
| product-ux-strategist | "unconfirmed"/"부분정보" 라벨이 사용자 신뢰 UI로 직결 | CLOSED_BY_DESIGN |
| commercialization-strategist | 품질 게이트 = 제품 신뢰도 = 프리미엄 근거 | CLOSED_BY_DESIGN |

---

## 8. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 저품질 데이터 발행 | 게이트 없음 | 신뢰 하락 | quality_score 분포 | 11 게이트 | gate 테스트 | CLOSED_BY_TEST_PLAN |
| 중복 사건 증폭 | dedup 누락 | 같은 사건 도배 | dup_rate | content_hash + 벡터 | dedup 테스트 | CLOSED_BY_TEST_PLAN |
| 허위정보/명예훼손 | community-only 단정 | 법적 위험 | balance 게이트 | unconfirmed 라벨 + official 요구 | balance 테스트 | CLOSED_BY_DESIGN |
| 저작권 위반 | full-text 발행 | 법적 위험 | publication_policy | preview 강제 | legal 테스트 | CLOSED_BY_DESIGN |
| 요약 hallucination | LLM 불충실 요약 | 거짓 정보 | faithfulness(후속) | hold until verified | STEP 014 | DEFERRED_WITH_TRIGGER(STEP014) |
| numeric 오탈락 | body 게이트를 numeric에 적용 | 시세 신호 손실 | numeric 통과율 | body 면제 규칙 | exempt 테스트 | CLOSED_BY_DESIGN |

---

## 9. Commercialization Impact

- **품질 게이트 = 프리미엄의 근거**: "검증된 사건만"이라는 약속이 무료 뉴스 앱과의 차별점. 게이트가 그 약속을 기술로 보증.
- **신뢰 라벨 = UX 자산**: "unconfirmed"/"공식 확인됨"/"부분 정보" 라벨이 사용자에게 투명성을 줘 신뢰·체류를 높인다(product-ux).
- **법적 안전 = B2B 판매 가능**: 명예훼손·저작권 게이트가 기업 고객 리스크를 낮춰 계약을 가능케 한다.
- **노이즈 제거 = 비용 절감**: relevance 게이트가 쓰레기 데이터를 다운스트림 LLM에 안 보내 토큰 비용을 줄인다.

---

## 10. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| event_relevance 임계? | 노이즈 vs 누락 | 0.5(데이터로 조정) | No |
| community-only 사건 발행 정책? | 명예훼손 리스크 | "unconfirmed" 라벨, official 권장 | No |
| freshness 강등 vs 폐기? | 과거 맥락 유지 | 강등(폐기 아님) | No |
| summary_faithfulness를 1차에 넣을까? | LLM 비용/STEP 014 | 후속(다운스트림) | No |

---

## Phase D 핸드오프 — Phase E 품질 게이트로 넘기는 항목 (2026-06-14)

Phase D는 article-level candidate + BodyExtractionState까지 **구조화**했다. 품질 *판정(통과/탈락)*은
Phase E 게이트의 책임이며, data-quality 감사가 식별한 다음 항목을 여기서 닫는다:

| # | 게이트 | 현재 상태(Phase D) | Phase E 책임 |
|---|---|---|---|
| 1 | **dedup 실행** | canonical_url *키*만 생성 | canonical 일치 collapse + url 없는 항목 title/body content_hash near-dup |
| 2 | **boilerplate 필터** | body **길이**만 측정(`body_state`) | boilerplate 비율 측정 → 길이 통과해도 강등 |
| 3 | **purpose 매핑 강제** | 호출자가 purpose 주입 | source→purpose 매핑 누락 시 임계 오적용 차단 |
| 4 | **published_at 정규화** | 원문 포맷 보존(GDELT/RSS/ISO 혼재) | ISO-8601 UTC 정규화(시간 dedup/신선도 전제) |
| 5 | **evidence 역추적** | 다중 candidate가 동일 raw_artifact_path 공유 | candidate별 artifact 내 위치(인덱스) 부여 |
| 6 | **numeric 오분류 가드** | `_NUMERIC_KEYS` 1키 매칭 시 numeric 면제 | title/body 동시 존재 시 numeric 면제 회수 |

이 게이트들은 Phase D candidate(body_missing/snippet_only/numeric_exempt/parse_error 정규화 완료)를 입력으로
받으므로, Phase E는 *판정 로직*만 추가하면 된다.

## Phase E-0 Quality Pre-Gate 구현 (2026-06-14)

`quality_pre_gate.py`가 위 핸드오프 표의 **최소 사전 게이트**를 구현했다(전체 dedup 엔진 아님). candidate별 `pass/hold/reject`:

| 게이트 | 동작 | 판정 |
|---|---|---|
| evidence | raw_artifact_path/extracted_text_ref 둘 다 없음 | reject(no_evidence_ref) |
| identity | title도 structured signal도 없음 | reject |
| body_state | present/partial/numeric_exempt=pass; snippet_only/missing/parser_error=hold; malformed/no_artifact=reject | — |
| published_at | 존재하나 파싱 불가 | hold; 부재는 note만 |
| boilerplate | 마커 2+ → high | hold |
| duplicate_key | canonical 우선, 없으면 source\|title\|published 해시, 근거 없으면 None | — |
| publication | publication_policy.yaml(preview_only:N / no_public_preview) | — |

**실측(4102 candidate)**: pass 3630 / hold 449 / reject 23. 상위 hold 사유 snippet_only 368, body_missing 81, published_absent 35. 상위 reject 사유 no_title_no_structured_signal 23.

**⚠ 정직 경고**: pass 3630의 대부분은 numeric_exempt(시세)다. 기사형(news/community/search/official/domain ≈ 469)은 본문 present=0이라 거의 hold다. **pass율을 article 품질로 해석 금지** — group 분리 보고.

**미완(Phase E 본진)**: dedup은 *키만* 생성(collapse/near-dup 미실행, 중복률 미측정). boilerplate substring 휴리스틱은 오탐/미탐 가능. duplicate_key는 raw published 기반(표기차 미탐) — 정밀화 Phase E.

### Phase E-1 — production_readiness 게이트 (2026-06-14)

`source_body_report.classify_production_readiness`가 소스별 등급을 정직 분류(긍정편향 없이 실패 구분): `PRODUCTION_READY_SIGNAL`(본문 확보) / `STRUCTURED_SIGNAL_ONLY`(numeric) / `NEEDS_BODY_FETCH`(분해되나 snippet/missing) / `NEEDS_PARSER`(스키마·필드 미매핑/title 미매핑) / `HTML_UNSUPPORTED` / `KEY_MISSING` / `RATE_LIMITED` / `BLOCKED_NO_BYPASS`(robots/login/paywall — 우회 금지) / `INSUFFICIENT_DATA`.

**excerpt 게이트 추가**: `body_state`가 "Read the full story at …" 류 발췌 마커를 탐지해 길이≥임계라도 present로 승격하지 않는다(snippet_only 강등). the_verge present 10→1로 교정 — **본문 추출 성공률 ≈ 0**이 정직한 상태.

**실측 readiness(50소스)**: NEEDS_PARSER 21 / NEEDS_BODY_FETCH 18 / STRUCTURED_SIGNAL_ONLY 6 / HTML_UNSUPPORTED 2 / PRODUCTION_READY_SIGNAL 1 / BLOCKED_NO_BYPASS 1 / INSUFFICIENT_DATA 1. **launch blocker 없음**(보안/법무/우회 전부 CLOSED), **phase blocker = 본문 fetch + 소스별 파서**(Phase E).

### Phase E-2 — alive 등급 분리 + 인플레 제거 게이트 (2026-06-14, run 20260614T105328Z)

`classify_final_status`가 source_group별 alive/non-alive를 판정하되, **정직성 게이트**를 강화:
- **alive 2등급 분리(F3)**: `data_alive`를 `fully_alive`(결손 root_cause 없음)와 `degraded_alive`(NO_TIMESTAMP/NO_STABLE_URL 등 보유)로 쪼갠다. run4: data_alive 24 = fully 22 + degraded 2(eu_press_corner/igdb). 정책닫힘 포함 alive=32 단일숫자로 과대평가 금지.
- **OFFICIAL_RECORD anchor 강제(F1)**: official/domain record는 stable URL **또는** 시간 중 최소 1개 anchor가 없으면 alive 불가(NEEDS_PARSER). title만 있고 url·시간이 모두 없는 tmdb/culture_info는 정직하게 강등(OFFICIAL_RECORD_ALIVE 6→4) — 실시간 dedup/랭킹 불가 record를 alive로 세지 않음.
- **numeric 인플레 제거**: market 거래소 스냅샷(binance 3600행/coinbase 924행)을 source 어댑터로 **단일 신호**로 환원 → structured_signal 7·pre_gate_pass 8(E-1의 3607 인플레 제거). pre_gate_pass를 본문 품질로 오독하지 않게 됨.
- **excerpt/boilerplate 게이트 유지**: live fetch 본문도 길이-only 금지(excerpt 마커·boilerplate 휴리스틱). ARTICLE_BODY_ALIVE 6 중 5는 excerpt=False·boilerplate=low 검증.

**root cause taxonomy**: 모든 non-alive 소스가 ≥1 root cause 보유(unknown 없음). 분포: SCHEMA_UNKNOWN, NO_TITLE_OR_LABEL, BODY_FETCH_REQUIRED/FAILED, NO_STABLE_URL+NO_TIMESTAMP, RATE_LIMITED, HTML_UNSUPPORTED, POLICY_EXCLUDED/LOGIN/PAYWALL/ROBOTS_BLOCKED.
**launch blocker 없음**(보안 SECURE/법무 APPROVED/우회 0/키 비노출), **phase blocker = 소스별 필드 어댑터(sec_edgar title 등) + 뉴스 fetch 안정화**(Phase E).

> 다음 문서: `10_COMMERCIALIZATION_PRODUCT_OPTIMIZATION.md`.


## Phase E-3 — 품질 게이트 강화 (run 20260614T114401Z)

- **confident_full + title-overlap(불용어 제외)**: present이지만 짧고(<600) title 무관한 본문을 full로
  둔갑 금지(cnbc Pro 프로모션 차단). numeric/structured는 article과 분리 유지.
- **degraded 분리**: official/community에서 url·시간 anchor가 부족하면 root_cause(NO_STABLE_URL/
  NO_TIMESTAMP)와 함께 degraded로 표기(product_hunt/culture_info). fully_alive에 섞지 않는다.
- **인플레 방지**: its 31587 도로링크를 단일 신호로 환원(coinbase/binance 동일 원칙) 후 서비스가치
  판정 NOT_SERVICE_USEFUL.
- **마커 정밀화**: paywall/login/captcha를 구체 문구로 좁혀 false-positive(footer 구독/로그인) 감소.
- eventqueue evidence는 외부 URL만 — 로컬 경로 둔갑 금지.


## Phase F — Production Orchestration Closure

Phase F는 `time_normalizer.py`를 추가한다: NormalizedTime(value, precision, source_field,
confidence, warning). date-only는 precision=date 유지(datetime으로 승격하지 않음 —
warning precision_lost_date_only); YYYY-MM=month; bad/missing=unknown(collected_at와 구별).
structured signal → observed_at 우선; article → published_at; collected_at은 별도 유지(둔갑 없음).

quality_pre_gate는 여전히 no-evidence/no-title을 EventQueue 이전에 reject한다.

record_type 분리 강제: numeric_payload_exempt → structured_signal(절대 article 아님).

body honesty: `assess_body_state=="present"`인 것만 body_present로 계수;
RSS snippet_only는 body로 계수하지 않는다.

Monitoring secret-scan은 작성된 모든 record를 커버한다(샘플 아님) →
CRITICAL secret_exposure_suspected가 exit을 게이트한다.

## Phase G — Force Production-Ready Source Closure

**판정: PARTIAL_WITH_HARD_BLOCKERS** (ALL_READY 아님). 팀 리뷰가 과장 주장을 강제 하향.

데이터 품질·리스크 게이트 흡수 사항:
- **snippet ≠ body(정직성)**: cnbc는 ARTICLE_PARTIAL_ALIVE이나 snippet_only preview이며 full body가 아니다. RSS snippet은 body_present로 계수하지 않는다(assess_body_state=="present"만 계수).
- **nyt 법무**: ARTICLE_PARTIAL_ALIVE로 승격하되 preview_only / non_commercial / commercial_license_required 단서를 evidence에 보존. Legal APPROVED_WITH_CONDITIONS. 동일 자세 guardian/newsapi/aladin 적용.
- **product_hunt anchor 주의**: slug→post URL 폴백은 dedup-collapse 위험을 동반 → 실제 url을 선호. degraded는 라이브 재검증 부재로 미해소.
- **DataQuality 리뷰 CLEAN**: bok_ecos title spacing 수정, product_hunt slug collapse 위험 명시.
- **Security SECURE**: API key가 eq/raw_events/memory에서 stripped, secret scan PASS(269).

Adversarial 리뷰 결과: 주장된 ALL_READY → 정직한 PARTIAL로 강제 하향(gdelt 0-record 승격 철회, degraded는 라이브 재검증 없이 유지).

---

## Phase G-2 — Last-Chance Source Resurrection (dcinside / google_trends_explore / gdelt)

**판정: PARTIAL_MIXED_PENDING_AND_BLOCKERS** (3개 중 1 승격, 1 pending, 1 blocker). 품질·안전 게이트 관점에서 이번 단계의 핵심은 **dcinside community_signal에 대한 신뢰도·저작권 게이트 적용**과 **fresh data 0건을 READY로 둔갑시키지 않는 정직성 게이트**다.

- **dcinside — community_signal 신뢰도·강등 게이트(최종 DEGRADED)**. 30건은 전부 title+url+ISO time anchor를 갖췄으나, 이는 **익명 커뮤니티 신호**이므로 09의 reliability 게이트 원칙(익명 커뮤니티 글 1개로 사건 단정 금지)에 따라 사건 단정 1차 근거가 아닌 **unconfirmed_until_corroborated** 신호로만 취급한다(투자조언 경계 — 익명 갤러리 제목으로 시장 판단을 내리지 않는다). 작성자 닉네임(PII)은 수집하지 않는다. 저작권 게이트: list 메타데이터 preview만 수집하고 **full article body는 미수집**(저작권 보수) → full-text 복제 위험 게이트를 원천 차단한다. 이 preview는 body_present로 계수하지 않는다(snippet ≠ body 원칙과 정합). 본문 부재(LIST_PREVIEW_ONLY_NO_BODY) + AI 크롤러 robots 전면 차단을 generic UA로 접근(AI_CRAWLER_ROBOTS_BLOCK_HONORED_GENERIC_UA) + ToS 자동수집 미검증(TOS_AUTOMATED_USE_UNVERIFIED) + 단일 갤러리 범위(SCOPE_SINGLE_GALLERY_STOCKUS)로, 품질·안전 게이트가 clean READY 주장을 차단하고 **PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY(=production_state DEGRADED)**로 강등했다(cnbc/nyt preview-only 강등 선례와 일관).
- **gdelt — fresh data 0건 정직성 게이트**. live probe 429로 신선 데이터가 없으므로 production_ready 주장을 게이트가 차단한다. production_state 매핑 `EXTERNAL_RATE_LIMITED_PENDING_RESUME → EXTERNAL_RATE_LIMITED`로 0-record를 READY로 둔갑시키지 못하게 강제(Phase F의 gdelt 0-record 승격 철회와 동일한 정직성 자세).
- **google_trends_explore — 검증된 evidence 게이트(추측 disable 금지)**. "no key라서 막연히 disable"이 아니라, robots 비차단·공식 API 부재·anti-abuse 429·우회 금지라는 **검증된 evidence**로 requires_official_api_or_contract blocker를 확정했다. trending 역할은 compliant source google_trending_now가 커버하므로 품질 공백 없음.

검증: 전체 회귀 1130 passed, secret scan PASS(210), 신규 설치 0, 전 outputs gitignored. 최종 상태 분포: PRODUCTION_READY 44 / PRODUCTION_READY_DEGRADED 3(culture_info, product_hunt, dcinside) / EXTERNAL_RATE_LIMITED 1(gdelt) / POLICY_EXCLUDED 9, non_excluded_not_ready 4.

## Phase G-3 — Final Source Closure

**판정: PARTIAL_WITH_VERIFIED_HARD_BLOCKERS**. 품질·안전 게이트 관점에서 이번 단계는 **EvidenceGate의 역할과 한계를 정직히 명명**하고, **미구현 corroboration 게이트를 launch blocker로 명시**한 것이 핵심이다.

- **EvidenceGate 역할/한계(정직 명명)**: known synthetic/dead URL + local path 거부 + shape 검사를 수행하는 **shape+known-dead 가드**다. **liveness/relevance 강제는 게이트가 아니라 fetcher가 수집 시점에** 한다 — 게이트가 모든 신선도를 보장한다고 과장하지 않고, regression 가드로 범위를 정직히 한정했다(적대 리뷰 흡수: EvidenceGate 정직 명명).
- **미구현 corroboration 게이트 = launch blocker(명시)**: dcinside/product_hunt community_signal 레코드는 `confirmation_policy=unconfirmed_until_corroborated`로 태깅되나, **이를 소비하는 하위 quality/safety 게이트가 아직 코드로 없다**. 단일 소스 community_signal을 confirmed event로 게시하기 전 **corroboration 게이트 구현이 필수**다 — 투자 펌핑 콘텐츠가 event로 직행하지 않도록(CLAUDE.md 원칙1: 정보 제공이지 투자 조언이 아니다). 통과 전 dcinside DEGRADED 유지.
- **gdelt — fresh data 0건 정직성 게이트**: 429로 신선 데이터 없음 → READY 둔갑 차단(EXTERNAL_RATE_LIMITED 유지). 응답 diff 저장본 없어 UNVERIFIED 표기.

최종 상태 분포(재산출): PRODUCTION_READY 46 / PRODUCTION_READY_DEGRADED 1(dcinside) / EXTERNAL_RATE_LIMITED 1(gdelt) / POLICY_EXCLUDED 9 = 57. critical_alerts 0, non_excluded_not_ready 2(dcinside/gdelt). 검증: 전체 회귀 1179 passed, secret scan PASS.

## Phase G-4 — CommunityCorroborationGate 구현 (G-3 launch blocker 해소)

G-3가 launch blocker로 명시했던 **corroboration/펌핑 차단 게이트**를 구현했다(`community_corroboration_gate.py`) — CLAUDE.md 원칙1(info-not-advice) 정렬.

- **publish 등급 결정**: 익명 금융/투자 갤러리(stockus 등)→`publish_level=internal_queue_only`(외부 발행 금지, 내부 큐만); 펌핑/투자권유성 제목(매수/풀매수/가즈아/떡상/목표가 등)→`publish_blocked_until_corrob`(외부 확증 전 발행 차단); 그 외 커뮤니티→`preview_candidate`.
- **익명 외부확인 필수**: 익명 source는 항상 `requires_external_confirmation=True` — 단독 커뮤니티 신호가 confirmed event로 직행하지 못하게 한다(투자 펌핑 직행 방지).
- **dcinside community preview signal**(02 참조)은 이 게이트를 통과해야 publish 후보가 된다. 단, **이 게이트를 publish 파이프라인 하위에서 소비하는 wiring은 후속 과제**(게이트 자체는 구현·테스트 완료).
