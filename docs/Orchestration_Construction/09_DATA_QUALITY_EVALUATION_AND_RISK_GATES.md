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
