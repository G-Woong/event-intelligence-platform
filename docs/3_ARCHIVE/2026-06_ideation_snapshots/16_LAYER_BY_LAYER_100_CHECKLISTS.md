# 16 — LAYER-BY-LAYER 100 IMPLEMENTATION-GRADE CHECKLISTS

> L0~L14, 각 layer 100항목 = **총 1500**. Type ∈ TODO / RISK / IMPLEMENTED / COMMERCIAL / AGENT_HINT / POLICY / PARTIAL.
> IMPLEMENTED는 실제 코드 열람 근거. 각 layer 끝에 **완전 달성 기준**. 출처/사실은 03·04·05~14 참조.

> ⚠️ **STALE CODE-STATE (2026-06-18, Pre-Harness Cleanup Sprint)**: 일부 RISK/PARTIAL 항목의 상태값이
> 이후 커밋으로 무효화됐다(예: L0#1 "A→B 미배선(P0)" → bridge 배선·라이브 입증; EventQueue redis
> NotImplementedable → 구현됨; 6 mock 노드 → 5 baseline 대체). 본 체크리스트는 **backlog 참조**로 유지하되,
> 현재 구현 상태는 `docs/_CANONICAL/01·09`를 권위로 삼는다. ARCHIVE_ONLY(10 Group E).

---

## L0. Product thesis / commercial positioning — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | RISK | A→B 미배선(P0)이 모든 수익화의 선행조건 | 57소스가 실 raw_events에 안 들어가면 제품 가치 0 | bridge db_writer를 PG writer로 배선 | EventQueue→raw_events 실 INSERT e2e 확인 |
| 2 | COMMERCIAL | 검색엔진 아닌 event intelligence로 포지셔닝 | "발견-검증-구독"이 차별점 | 랜딩/피치에서 alert/stream 언어 사용 | 메시징에 "search" 대신 "detect/verify" 비율 측정 |
| 3 | COMMERCIAL | 1차 수익은 광고 아닌 B2B alert/report/API | 트래픽 부재+전재 금지 | B2B 산출물 3종 우선 설계 | 광고 매출 가정 사업계획서에서 제거 |
| 4 | IMPLEMENTED | 57소스 deterministic 수집엔진(Phase A~G-4) | 자산 존재 확인됨 | 추가 구현 아닌 연결에 집중 | INGESTION_FINAL 분포표와 일치 |
| 5 | IMPLEMENTED | EvidenceGate + CommunityCorroborationGate | 신뢰 라벨링 핵심 | 게이트 출력을 trust_label로 노출 | 게이트 결과가 카드에 매핑됨 |
| 6 | IMPLEMENTED | SourceStrategyMemory(llm_agent_hints) | 소스별 전략 학습 자산 | premium agent 계층 재사용 | hints 필드 존재 확인 |
| 7 | COMMERCIAL | 차별점1: 다중 소스 교차 검증 | 단일소스 뉴스앱 대비 우위 | 공식/보도/반응 3층 카드 | 3층 라벨 동시 노출 사건 비율 |
| 8 | COMMERCIAL | 차별점2: 증거 체인(URL+summary+metadata) | 저작권 안전+신뢰 | evidence_links 카드 노출 | 카드당 1차 출처 링크 ≥1 |
| 9 | COMMERCIAL | 차별점3: 사건 중심 재구성(검색 아님) | 능동 감지 | event queue 신선도 노출 | near_real_time 갱신 가시화 |
| 10 | RISK | "57소스 다 켜면 가치↑" 착각 | 연결 전엔 소스 수 무의미 | vertical별 필요 소스만 활성 | MVP는 단일 vertical 소스셋 |
| 11 | RISK | google_trends_explore를 세일즈 약속에 넣기 | CONFIRMED_EXTERNAL_RATE_LIMIT | 마케팅에서 trends 우위 주장 금지 | 피치덱에 trends 실시간 약속 0건 |
| 12 | RISK | x(트위터)를 실시간 OSINT로 약속 | MVP_EXCLUDED(유료 API) | 안보 OSINT vertical 후순위 | x 의존 기능 MVP 제외 |
| 13 | COMMERCIAL | 추천 1차 vertical: AI/tech 제품 incident | 소스 두께+낮은 법적 리스크 | techcrunch/verge/zdnet/hn 셋 우선 | 해당 vertical 카드 일일 생성량 측정 |
| 14 | TODO | 1차 고객군: AI/SaaS 제품팀·DevRel·PM | 구체적 ICP 정의 | 경쟁사/제품 incident 모니터 니즈 검증 | 인터뷰 ≥5건 |
| 15 | COMMERCIAL | Phase2 확장 vertical: 금융/공시 | WTP 최고(5) | sec_edgar/opendart 연결 | Phase2 트리거 조건 문서화 |
| 16 | RISK | 금융 vertical의 투자조언 경계 | 규제 리스크 | 가격 언급 시 가치판단 금지 | 출력 톤 검사 통과 |
| 17 | COMMERCIAL | 가격 모델: hybrid(base+usage) | 시장트렌드 61% hybrid | seat 기반 탈피 | 가격표에 usage 미터 포함 |
| 18 | COMMERCIAL | usage 미터 후보: alert수/API콜/레코드 | AI가 seat-가치 깸 | 과금 단위 정의 | 미터 정의서 작성 |
| 19 | TODO | 경쟁 포지셔닝 맵 작성 | Dataminr/AlphaSense 대비 위치 | 가격×깊이 2축 매핑 | 경쟁맵 1장 |
| 20 | COMMERCIAL | 경쟁 대비 가격 underdog 포지션 | enterprise custom 대비 진입가 | SMB/팀 단위 진입가 | 경쟁 최저가 대비 명시 |
| 21 | RISK | robots/ToS/CAPTCHA 우회 금지 불변 | 정책 위반=사업 중단 | 우회 의존 기능 배제 | 우회 코드 0건 유지 |
| 22 | COMMERCIAL | 전재 금지=evidence 중심이 오히려 강점 | 저작권 안전→B2B 판매성↑ | 요약+링크 모델 고수 | 원문 전재 0건 |
| 23 | IMPLEMENTED | CORE_READY 44소스(live 실측) | 즉시 연결 가능 자산 | vertical 매핑 우선 | 44 목록과 일치 |
| 24 | RISK | EventQueue=JSONL, JSON mirror만 | 실 PG 미배선 | db_writer 배선 필요 | PG row count 증가 확인 |
| 25 | COMMERCIAL | retention 레버 = 신선한 event queue | 재방문 동기 | 큐 신선도 SLA 정의 | 일일 신규 사건 ≥N |
| 26 | TODO | premium 1순위: 키워드/섹터 alert | 즉시 알림 가치 | push 파이프라인 설계 | alert 구독 기능 정의 |
| 27 | COMMERCIAL | premium 2순위: evidence 심층+모순분석 | 차별 심층 가치 | 다중소스 모순 표면화 | 모순 사건 카드 예시 |
| 28 | COMMERCIAL | B2B API: event queue 직접 구독 | 큐 안정 후 판매 | API 계약+rate plan | API 가격 티어 정의 |
| 29 | COMMERCIAL | B2B 리포트: 정기 사건 요약 | 인적 분석 대체 | 일/주 요약 자동화 | 리포트 템플릿 1종 |
| 30 | RISK | LLM 추론이 최대 비용 | 마진 잠식 | mock 기본+게이트 선별 | LLM 호출/사건 비율 상한 |
| 31 | COMMERCIAL | 비용 상한(quota guard)으로 마진 설계 | 최악 비용 못박기 | 일일 quota→가격 역산 | 가격이 quota 비용 커버 |
| 32 | RISK | 유료검색(serper/tavily) 정기폴링 비용폭발 | 적자 위험 | on-demand only | 정기 폴링 0건 |
| 33 | IMPLEMENTED | rate-limit/격리/quota guard 존재 | 안정성 자산 | 가격 모델에 비용 상한 반영 | guard 동작 확인 |
| 34 | COMMERCIAL | 무료티어: 기본 피드+검색 | 획득 깔때기 | freemium 경계 정의 | 무료/유료 기능 분리표 |
| 35 | TODO | ICP별 획득 채널 정의 | GTM 효율 | DevRel은 커뮤니티/HN | 채널별 CAC 가설 |
| 36 | RISK | "모든 사람이 고객" 착각 회피 | 막연한 타겟 실패 | 단일 ICP 집중 | ICP 1개로 시작 |
| 37 | COMMERCIAL | NewsData.io 무료티어 상업이용 가능 | 저비용 소스 보강 | 보조 소스로 평가 | 라이선스 조항 확인 |
| 38 | AGENT_HINT | SourceStrategyMemory를 premium research에 재사용 | 고급 계층 자산화 | Layer3 agent 입력 | hints→agent 연결 설계 |
| 39 | COMMERCIAL | Layer3 고급 에이전트=premium/B2B | MVP 이후 부가가치 | 매출 검증 후 추가 | MVP 비용서 제외 |
| 40 | RISK | dashboard 선구축은 출시 지연 | 과잉 기능 | 후순위(D-11) | MVP 범위서 제외 |
| 41 | RISK | LangGraph/Celery 1차 필수 아님 | deterministic로 충분 | MVP는 결정론 사이클 | MVP 동작에 Celery 불요 |
| 42 | COMMERCIAL | 3층 구조(공식/보도/반응)가 경쟁 차별 | 단일소스 못 줌 | 카드 3층 UI | 3층 동시 사건 비율 |
| 43 | TODO | WTP 검증 인터뷰 우선 | 가격 가설 검증 | 5개 vertical 고객 접촉 | 인터뷰 결과 문서 |
| 44 | COMMERCIAL | dcinside 커뮤니티는 반응레이어 한정 | 발견원 사용시 명예훼손 | unconfirmed 라벨 강제 | 커뮤니티 단독 발행 0건 |
| 45 | RISK | 커뮤니티 단독 발견=오정보 리스크 | 평판 훼손 | official 확인 전 unconfirmed | balance 게이트 통과 |
| 46 | COMMERCIAL | 공식 소스(sec/opendart) "official_confirmed" 라벨 | 신뢰 프리미엄 | trust_label 매핑 | 공식 라벨 정확도 |
| 47 | TODO | 가격 티어 3-4개 설계 | 시장표준 3-4티어 | Free/Pro/Team/Enterprise | 티어표 작성 |
| 48 | COMMERCIAL | seat+usage add-on 구조 | Dataminr seat+add-on 참조 | base seat+alert add-on | 하이브리드 가격 정의 |
| 49 | RISK | 근거 없는 시장규모 추정 금지 | 신뢰성 훼손 | bottom-up ICP 추정만 | TAM에 출처 명시 |
| 50 | TODO | 경쟁사별 약점 매핑 | 차별 포인트 도출 | Dataminr 고가/AlphaSense 검색중심 | 경쟁 약점표 |
| 51 | COMMERCIAL | Dataminr 대비: 가격 접근성 | 550+ 보안팀=엔터프라이즈 | SMB 진입 가능 가격 | 진입가 비교 |
| 52 | COMMERCIAL | AlphaSense 대비: 능동 감지 | 그들은 검색 중심 | alert 능동성 강조 | 감지 latency 측정 |
| 53 | COMMERCIAL | Recorded Future 대비: 범용 incident | 그들은 사이버TI 특화 | 제품/시장 incident 범용성 | 커버 vertical 폭 |
| 54 | COMMERCIAL | Liveuamap 대비: 검증+증거체인 | 그들은 지도 시각화 | evidence 라벨 우위 | 검증 라벨 유무 |
| 55 | TODO | 6개월 GTM 로드맵 수립 | 실행 가능성 | L14에 상세화 | 분기별 목표 |
| 56 | RISK | 브리지 전 세일즈는 공허 | 데모 불가 | P0 후 영업 개시 | 동작 데모 선결 |
| 57 | COMMERCIAL | 첫 데모=단일 vertical 라이브 큐 | 가치 즉시 증명 | AI incident 큐 라이브 | 데모 큐 신선도 |
| 58 | AGENT_HINT | evidence 모순분석을 agent로 자동화 | premium 심층 | 다중소스 충돌 탐지 | 모순 탐지 정확도 |
| 59 | COMMERCIAL | 저작권 안전이 엔터프라이즈 조달 통과 | legal 검토 우위 | 전재 0 정책 문서화 | 조달 체크리스트 통과 |
| 60 | RISK | gdelt EXTERNAL_RATE_LIMITED 1 의존 주의 | 안보 vertical 약화 | 15분 주기 한계 인지 | SLA에 반영 |
| 61 | COMMERCIAL | POLICY_EXCLUDED 9 기능 약속 금지 | 미수집 소스 | 세일즈 범위서 제외 | 제외 소스 약속 0 |
| 62 | TODO | landing 메시지 A/B 후보 | 포지셔닝 검증 | "먼저 안다" vs "믿을 수 있다" | 전환율 비교 |
| 63 | COMMERCIAL | "남보다 먼저+믿을 수 있게" 핵심 카피 | 가치 명제 | 헤드라인 채택 | 메시지 합의 |
| 64 | IMPLEMENTED | SourceCapability·StrategyGraph 존재 | 소스 관리 자산 | 운영 안정성 근거 | 구조 확인 |
| 65 | RISK | dcinside COMMUNITY_PREVIEW 1 한정 | 커뮤니티 커버 얕음 | 반응레이어 보조만 | 단독 의존 금지 |
| 66 | COMMERCIAL | API 과금=레코드/콜 usage | seat 무력화 대응 | usage 미터링 구현 | 미터 정확도 |
| 67 | TODO | 파일럿 고객 3곳 확보 목표 | 초기 검증 | AI vertical 타겟 | LOI ≥3 |
| 68 | COMMERCIAL | 파일럿=무료/저가, 케이스스터디 확보 | 레퍼런스 자산 | 파일럿 계약 템플릿 | 케이스스터디 1건 |
| 69 | RISK | 과잉 vertical 동시 활성 출시 지연 | 초점 분산 | 단일 vertical 출시 | MVP=1 vertical |
| 70 | COMMERCIAL | report=인적 분석 대체 가치 | B2B WTP 명확 | 자동 요약 리포트 | 리포트 구독 전환 |
| 71 | AGENT_HINT | llm_agent_hints로 소스별 수집 최적화 | 비용/품질 | hints 활용 검증 | hints 적용 효과 |
| 72 | COMMERCIAL | 무료→Pro 전환 트리거: alert 한도 | upsell 경로 | alert 수 게이팅 | 전환율 측정 |
| 73 | RISK | 큐 비면 retention 붕괴 | 재방문↓ | 큐 신선도 모니터 | 일일 신규 사건 SLA |
| 74 | TODO | 채널: HN/ProductHunt 런칭 | 저비용 획득 | AI/tech 커뮤니티 적합 | 런칭 후 가입수 |
| 75 | COMMERCIAL | DevRel/PM ICP의 채널=기술 커뮤니티 | 정밀 타겟 | HN/Reddit(읽기)/뉴스레터 | 채널 CAC |
| 76 | COMMERCIAL | 금융 vertical 채널=리서치/IR 직군 | Phase2 | LinkedIn/리서치 커뮤니티 | Phase2 채널 가설 |
| 77 | RISK | 정책/규제 vertical 느린 세일즈 사이클 | 현금흐름 | 공공 조달 장기화 인지 | 사이클 길이 가정 |
| 78 | COMMERCIAL | federal_register/eu_press=규제 vertical 코어 | 법적 리스크 낮음(5) | 규제 알림 상품 | 규제 vertical 카드 |
| 79 | TODO | pricing 검증 실험 설계 | 가격 민감도 | Van Westendorp 가설 | 가격 인터뷰 결과 |
| 80 | COMMERCIAL | enterprise는 custom 가격(시장표준) | 대형 딜 | 엔터프라이즈 별도 트랙 | custom 견적 프로세스 |
| 81 | RISK | 막연한 TAM 추정 회피 | 실패 조건 | ICP수×ARPU bottom-up | TAM 산식 명시 |
| 82 | COMMERCIAL | 1차 SOM=AI/tech 제품팀 수 추정 | 현실적 시장 | bottom-up 산정 | SOM 근거 문서 |
| 83 | AGENT_HINT | research assistant=Layer3 premium | 매출 검증 후 | deep agent 분리 | MVP 제외 확인 |
| 84 | COMMERCIAL | 저작권 안전→media/PR vertical 가능 | 추가 시장 | Talkwalker/Meltwater 인접 | brand risk 상품 후보 |
| 85 | RISK | media vertical 법적 리스크 3 | 명예훼손 | 사실 라벨 강제 | unconfirmed 처리 |
| 86 | TODO | 차별점 3개 이상 명문화 | 성공 기준 | 교차검증/증거체인/사건중심 | 차별표 작성 |
| 87 | COMMERCIAL | 수익화 경로 2개 이상 명문화 | 성공 기준 | alert 구독+API/리포트 | 경로 2+ 문서 |
| 88 | COMMERCIAL | NewsData.io 등 무료소스로 비용 방어 | 마진 | 무료티어 소스 우선 | 무료소스 비율 |
| 89 | RISK | LLM 비용이 alert 단가 초과 위험 | 역마진 | 게이트로 입력 절감 | 사건당 LLM 비용 상한 |
| 90 | COMMERCIAL | alert 정확도가 churn 핵심 | 거짓 alert=이탈 | evidence 게이트 강화 | false alert rate |
| 91 | TODO | onboarding=관심 키워드/섹터 설정 | activation | 첫 alert까지 시간 단축 | TTV 측정 |
| 92 | COMMERCIAL | 첫 가치 경험=의미있는 첫 alert | activation 핵심 | seed 키워드 추천 | 첫 alert 도달률 |
| 93 | RISK | 57소스 중 POLICY_EXCLUDED 9 영구 제외 | 소스 풀 과대평가 금지 | READY46 기준 계획 | 가용소스=46 기준 |
| 94 | COMMERCIAL | 신뢰 라벨이 가격 정당화 근거 | "왜 유료냐" 답 | official_confirmed 가치 | 라벨 신뢰도 검증 |
| 95 | AGENT_HINT | SourceStrategyMemory→자동 소스 확장 | 운영 효율 | 신규 소스 학습 | 확장 자동화 |
| 96 | TODO | 6개월 후 매출/파일럿 KPI 설정 | 검증 기준 | MRR/파일럿/전환 | KPI 대시보드 |
| 97 | COMMERCIAL | 정보제공 포지션이 규제 리스크↓ | 판매성↑ | 투자조언 0 유지 | 톤 검사 |
| 98 | RISK | "이 정보로 돈 번다" 마케팅 금지 | 정책+규제 | 정보 가치만 소구 | 카피 검수 |
| 99 | COMMERCIAL | 경쟁 차별 종합=가격+검증+능동감지+범용 | 포지셔닝 핵심 | 4축 차별 메시지 | 차별 메시지 합의 |
| 100 | TODO | adversarial-reality-critic 가설 검토 의뢰 | 리스크 사전 차단 | 핵심 가설 목록 전달 | 검토 회신 수령 |

**완전 달성 기준:** P0 브리지 해소 후 단일 vertical(AI/tech incident)에서 evidence-linked alert가 실 raw_events 기반으로 생성되고, 1차 ICP 인터뷰 5건+파일럿 LOI 3건으로 WTP가 검증되며, 광고 비의존 hybrid 가격표와 차별점 3개·수익화 경로 2개가 문서로 확정된다.

## L1. Source discovery and seed ingestion — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | source_registry.yaml 57소스 단일 선언 | 발견 대상 SSOT | id/type/layer/base_url/implemented | 57 entry 로드, schema 검증 통과 |
| 2 | IMPLEMENTED | SourceCapability 선언적 능력 모델 | if-스파게티 제거, 라우팅 입력 | source_capability.py 4소스 | capability_for() 반환, frozen dataclass |
| 3 | IMPLEMENTED | StrategyGraph capability→전략 노드 | 발견 후 안전 수집 경로 결정 | build_strategy_graph | unsafe 노드 ValueError reject |
| 4 | IMPLEMENTED | UNSAFE_STRATEGIES 11종 빌드 reject | 우회 코드 진입 차단 | frozenset + reject_unsafe | proxy/captcha/robots_ignore 거부 |
| 5 | IMPLEMENTED | SourcePolicyProbe robots 실측 파싱 | 발견 단계 정책 사전판정 | longest-match | path allow/disallow 판정 |
| 6 | IMPLEMENTED | AI 크롤러 토큰 도메인 차단 감지 | ToS 존중, 발견 게이팅 | _AI_CRAWLER_TOKENS 8종 | claudebot 등 Disallow:/ 감지 |
| 7 | IMPLEMENTED | EvidenceGate shape 린터 | seed의 evidence 형태 강제 | evaluate_evidence | 외부URL+stable_id+time+payload 검사 |
| 8 | IMPLEMENTED | 합성/local URL 둔갑 차단 | 가짜 seed 회귀 방지 | _SYNTHETIC_URL_PATTERNS | producthunt slug reject |
| 9 | IMPLEMENTED | CommunityCorroborationGate | 익명 seed publish 등급화 | community_corroboration_gate.py | 금융갤러리→internal_queue_only |
| 10 | IMPLEMENTED | 펌핑/투자권유 제목 차단 | §1 info-not-advice | _SOLICITATION_MARKERS | solicitation→publish_blocked |
| 11 | IMPLEMENTED | SourceStrategyMemory 누적 | 발견 전략 학습 재사용 | source_strategy_memory.py YAML | successful_strategy 직렬화/로드 |
| 12 | IMPLEMENTED | preferred_strategy_for | 무의미 전략 반복 회피 | 함수 | success→preferred 선택 |
| 13 | IMPLEMENTED | is_known_dead_end | dead-end seed skip | 함수 | terminal+no-success→True |
| 14 | IMPLEMENTED | derive_production_state total fn | UNKNOWN=0 운영 상태 | production_state.py | 14 enum 중 1개 항상 반환 |
| 15 | IMPLEMENTED | SCHEDULABLE_STATES 분리 | 발견 소스 due 후보 선별 | frozenset | READY/DEGRADED/PREVIEW만 schedulable |
| 16 | IMPLEMENTED | rate_limit_policy.yaml per_source | 발견시 rate governance | configs | gdelt 60s/900s, trends 7200s/0retry |
| 17 | IMPLEMENTED | google_trends_explore max_retries=0 | 외부 429 재시도 봉인 | rate_limit_policy.yaml | cooldown 3600s 강제 |
| 18 | IMPLEMENTED | gdelt host_rate_limit_lock 노드 | 발견 호출 간격 강제 | _gdelt_graph | rate_limit_check + fallback edge |
| 19 | IMPLEMENTED | RawEventBridge content_hash dedup | seed 재실행 collapse | _content_hash | sha256 64char, 중복 skip |
| 20 | IMPLEMENTED | bridge url NOT NULL hold | url 없는 seed 적재 거부 | BRIDGE_STATUS_HELD | missing_external_url→held |
| 21 | IMPLEMENTED | preview_only raw_text="" | 전문 재배포 금지 | to_raw_event_create | raw_text 빈 문자열 |
| 22 | IMPLEMENTED | EventQueue Redis→JSONL fallback | seed 큐잉 동작 | pipeline/event_queue.py | REDIS_URL 없으면 JSONL enqueue |
| 23 | IMPLEMENTED | discovery_collector 파이프라인 | document_discovery seed 수집 | pipeline/discovery_collector.py | scaffold 통과 |
| 24 | IMPLEMENTED | search_enrichment_collector | search layer seed 보강 | pipeline | scaffold 통과 |
| 25 | IMPLEMENTED | query_generator seed 쿼리 | 발견 쿼리 생성 | pipeline/query_generator.py | 쿼리 빌드 |
| 26 | IMPLEMENTED | source_policy_probe paywall/login 마커 | seed 접근성 판정 | source_policy_probe.py | requires_login/paywall 플래그 |
| 27 | IMPLEMENTED | SEC EDGAR UA(이름+이메일) | efts.sec.gov 정책 준수 | sources/sec_edgar.py | 10req/s, UA 필수 |
| 28 | IMPLEMENTED | dcinside robots-allowed 갤러리만 | 허용 path만 발견 | allowed_galleries:[stockus] | robots allow 갤러리 list fetch |
| 29 | IMPLEMENTED | AP news canonical 정규화 | discovery proxy 식별성 유지 | DISCOVERY_PROXY_NOTE | news.google→apnews.com 정규화 |
| 30 | IMPLEMENTED | Playwright probe site specs | browser seed 선택자 선언 | playwright_probe_sites.yaml | selector/wait/status 선언 |
| 31 | IMPLEMENTED | Cloudflare deferred 마킹 | 우회 불가 seed 보류 | fmkorea deferred:true | Turnstile→deferred_reason |
| 32 | IMPLEMENTED | collection_probe 후보 추출 | seed 수집 가능성 측정 | fetch_strategies/collection_probe.py | 후보 N건 보고 |
| 33 | IMPLEMENTED | article_body_extractor | seed 본문 추출 | fetch_strategies | body 추출 시도 |
| 34 | IMPLEMENTED | trafilatura/readability 추출기 | 다단 본문 추출 fallback | tools/trafilatura_extractor.py | 추출 결과 반환 |
| 35 | IMPLEMENTED | failure_classifier | seed 실패 원인 분류 | fetch_strategies | 실패→root_cause 매핑 |
| 36 | IMPLEMENTED | normalize_record_times | seed 시간 precision 보존 | time_normalizer.py | precision 라벨 유지 |
| 37 | IMPLEMENTED | quality_pre_gate | seed 적재 전 품질 | quality_pre_gate.py | pre-gate decision 부여 |
| 38 | IMPLEMENTED | gate_records 집계(≥1 ready) | source 자격 판정 | gate_records | ready_count>0→allowed |
| 39 | IMPLEMENTED | production_audit | 운영 분포 감사 | production_audit.py | 분포/갭 보고 |
| 40 | IMPLEMENTED | production_scheduler due 산출 | schedulable seed 스케줄 | production_scheduler.py | next_due_at 산출 |
| 41 | TODO | A→B bridge db_writer 미주입 | **P0: PG에 seed 미도달** | db_writer 콜러블 주입(workers POST) | raw_events PG row ≥1, mirror→DB |
| 42 | TODO | EventQueue Redis client 미배선 | 멀티워커 seed 큐 미동작 | "Round 2" Redis 구현 | REDIS_URL 시 stream enqueue/dequeue |
| 43 | TODO | A의 EventQueue→B의 raw_events 트리거 | 두 서브시스템 미연결 | workers consumer가 mirror/queue 소비 | end-to-end seed 1건 PG 도달 |
| 44 | TODO | LIVE_SUCCESS 단발→지속 검증 부재 | READY 46 과대계상 위험 | 반복 probe + last_success_at | 2회+ 연속 성공 시 READY 확정 |
| 45 | TODO | SourceCapability 4소스만 선언 | 53소스 capability 미선언 | READY 소스로 확장 | schedulable 소스 capability 100% |
| 46 | TODO | StrategyGraph 빌더 4개 한정 | news/search 그래프 부재 | news 본문 그래프 빌더 추가 | news 소스 graph build 성공 |
| 47 | TODO | google_programmable_search 400 | CX/key 미확정 | reactivate_when_CX_confirmed | 200 + items 확인 후 재활성 |
| 48 | TODO | search P1 4종 미배선 | serper/tavily/exa/newsapi LIVE만 | integrate_into_pipeline | pipeline 경유 seed 산출 |
| 49 | TODO | krx_kind 서버 에러 보류 | 공식 공시 seed 결손 | mobile UA/대체 endpoint | 200 + list rows |
| 50 | TODO | reddit MVP_DEFERRED | rate_limit 변동성 | OAuth 전환 검토 | OAuth 토큰 후 안정 수집 |
| 51 | RISK | dcinside 익명 PII/펌핑 | 법적·§1 위반 위험 | internal_queue_only 유지 | 금융갤러리 자동 publish 0건 |
| 52 | RISK | gdelt 5s에도 429 발생 | 외부 IP rate limit | min 60s/cooldown 900s 보수화 | 429 발생률 하락 |
| 53 | RISK | google_trends 비공식 API | ToS·rate-limit 회색지대 | max_retries=0 유지 | READY 둔갑 금지 |
| 54 | RISK | 단발 probe를 READY로 표기 | 운영 신뢰도 과신 | PROBED_ONLY 중간 등급 | 지속검증 전 READY 미확정 |
| 55 | RISK | mirror JSONL이 DB 착시 | 적재됐다고 오인 | target="mirror" 명시 노출 | 보고서에 mirror vs db 구분 |
| 56 | RISK | Playwright selector 사이트 리빌드 취약 | CSS-in-JS 등 | selector 다중 fallback | 깨짐 시 LIVE_PARTIAL 강등 |
| 57 | RISK | requires_api_key 키 부재 | NEEDS_OPERATOR_REVIEW 다수 | .env 키 존재만 확인 | 키 존재→READY 승격 게이트 |
| 58 | RISK | AP news Google News proxy 의존 | 발견 경로 단일점 | canonical 정규화 유지 | url_resolver 1-hop 성공률 |
| 59 | RISK | content_hash 충돌 시 seed 누락 | dedup 과차단 | canonical>url>id 우선순위 | 동일 seed만 collapse |
| 60 | RISK | reuters/x/blind MVP_EXCLUDED | 고신호 seed 결손 | 공식 라이선스 전까지 제외 | 우회 시도 0 |
| 61 | COMMERCIAL | SEC EDGAR 무료·무키 고신호 | 저비용 공식 seed | UA 준수 운영 | 8-K 등 filing seed 지속 |
| 62 | COMMERCIAL | OpenDART 보유 키 활용 | 한국 공시 차별화 seed | opendart.py list.json | 공시 seed 수집 |
| 63 | COMMERCIAL | GDELT 무료 글로벌 이벤트 | rate-limited지만 무비용 | spaced_single_probe | governance 내 seed 확보 |
| 64 | COMMERCIAL | search 무료 tier 합산 | serper/tavily/exa/gnews 무료분 | 무료 quota 라운드로빈 | 일 무료한도 내 seed 보강 |
| 65 | COMMERCIAL | 도메인 API 다수 LIVE | KOFIC/TMDB/IGDB 등 수직 seed | domain_signal layer 통합 | 수직 이벤트 seed 차별화 |
| 66 | COMMERCIAL | preview_only가 재배포 리스크 차단 | 라이선스 안전 상업화 | raw_text="" 정책 고수 | 전문 저장 0건 |
| 67 | COMMERCIAL | 정책안전 라우팅=신뢰 자산 | B2B 컴플라이언스 셀링포인트 | UNSAFE reject 가시화 | 우회 0 감사 통과 |
| 68 | AGENT_HINT | llm_agent_hints 누적 채널 | 미래 SourceSupervisor 입력 | 필드 존재 | hint 직렬화, 비면 생략 |
| 69 | AGENT_HINT | reject_unsafe LLM 제안 필터 | supervisor 우회 제안 차단 | strategy_graph.py 진입점 | 제안→(safe,rejected) 분리 |
| 70 | AGENT_HINT | supervisor는 discovery에만 | 결정적 ingestion 보호 | 후보 점수화 한정 | 실행 경로 LLM 미개입 |
| 71 | AGENT_HINT | never_disable_on_single_429 | 단발 429 과잉 비활성 방지 | hint 축적 | 1회 429→비활성 안 함 |
| 72 | AGENT_HINT | preferred_strategy 자동 선택 | 학습 전략 재사용 | preferred_strategy_for | runner가 best 사용 |
| 73 | AGENT_HINT | dead_end skip 힌트 | 무의미 재시도 절약 | is_known_dead_end | dead-end 소스 skip |
| 74 | AGENT_HINT | policy_sensitivity HIGH fallback 강제 | 민감 소스 preview 강등 | build_strategy_graph 검사 | HIGH+detail→fallback 필수 |
| 75 | AGENT_HINT | capability 미선언시 graph 거부 | 무모델 소스 안전 차단 | no_strategy_graph_for | 미선언 소스 실행 거부 |
| 76 | TODO | discovery vs ingestion 모듈 경계 미문서화 | 책임 혼선 | 분리 명문화 | 경계 문서 + import 방향 단일 |
| 77 | TODO | 새 고신호 소스 발굴 루프 부재 | 정적 57 고정 | policy_probe 기반 후보 평가 | 후보→probe→registry 제안 |
| 78 | TODO | source_registry status 필드 비일관 | 일부만 status 보유 | 전 소스 status 표준화 | 57소스 status enum 일관 |
| 79 | TODO | bridge held seed 재처리 경로 없음 | url 없는 seed 영구 hold | held→재해결 큐 | held 재시도 후 written |
| 80 | TODO | EventQueue dequeue ack/재처리 미검증 | 큐 신뢰성 미보증 | pending→ack 테스트 | 소비 실패 시 재큐 |
| 81 | RISK | workers raw_events 경로 별도 | A/B 스키마 드리프트 | bridge가 RawEventCreate 계약 추적 | backend 스키마 변경 감지 |
| 82 | RISK | feedparser RSS 외부 의존 | B 수집 단일 라이브러리 | rss_collector.py | 파싱 실패 격리 |
| 83 | RISK | ADMIN_API_TOKEN env 의존 | B 적재 인증 결손시 실패 | 토큰 존재만 확인 | 토큰 부재→명시 BLOCKED |
| 84 | COMMERCIAL | A의 라우팅 자산을 B에 이식 | 중복 수집 로직 제거 | bridge로 A→B 단일화 | B가 A seed 소비 |
| 85 | COMMERCIAL | dedup collapse=비용 절감 | 재실행 중복 저장 회피 | content_hash on_conflict | 중복 row 0 |
| 86 | AGENT_HINT | safety_policy="no_bypass" 기본 | 메모리 안전 디폴트 | 필드 | 모든 entry no_bypass |
| 87 | AGENT_HINT | cooldown_policy 메모리 기록 | rate 학습 입력 | cooldown_policy 필드 | gdelt cooldown 기록 |
| 88 | AGENT_HINT | parser_notes 전략 메모 | 본문 selector 학습 | parser_notes | dcinside .write_div 기록 |
| 89 | AGENT_HINT | body_fetch_strategy 메모리 | 본문 전략 재사용 | body_fetch_strategy | 성공 본문 전략 저장 |
| 90 | AGENT_HINT | browser_strategy 메모리 | playwright 전략 학습 | browser_strategy | 성공 browser 전략 저장 |
| 91 | TODO | capability rate_limit_policy_id 연결 검증 | 모순 노드 방지 | rate check | policy_id 없는데 check→ValueError |
| 92 | TODO | EvidenceGate live URL 미검증(network 0) | shape만 통과 가능 | fetcher가 1차 live 검증 | 수집시 dead url skip |
| 93 | TODO | require_body news 강제 미일관 | news seed 본문 누락 허용 | news는 require_body=True | news ready=본문 보유시만 |
| 94 | RISK | 57 중 POLICY_EXCLUDED 9 영구 | seed 커버리지 한계 인지 | dead-end 유지 | excluded 재시도 0 |
| 95 | RISK | community_signal preview만 | 본문 부재 seed 가치 제한 | preview tier 명시 | preview→corroboration 강제 |
| 96 | COMMERCIAL | 무키 소스(coinbase/binance) ready | 키 없이 즉시 seed | NO_KEY_REQUIRED | live test 후 통합 |
| 97 | COMMERCIAL | tier1 공식 소스 집중 | 신뢰도 높은 seed 우선 | evidence_level tier1 가중 | tier1 우선 스케줄 |
| 98 | AGENT_HINT | root_cause_before/after 추적 | 전략 개선 학습 신호 | 메모리 필드 | 개선 전후 원인 기록 |
| 99 | AGENT_HINT | evidence 필드 사실 기록 | 검증 근거 보존 | evidence | live 결과 문자열 보존 |
| 100 | AGENT_HINT | secret 미저장 원칙 | 메모리 안전성 | 메모리에 키 금지 | scan PASS, 키 0건 |

**완전 달성 기준:** A→B bridge db_writer 주입으로 seed 1건+ raw_events 적재(41/43), schedulable 소스 capability+graph 100% 선언(45/46), LIVE_SUCCESS 2회+ 지속검증으로 READY 확정(44), 우회 전략 reject + secret scan 키 0건(4/100).

## L2. Search expansion and external web exploration — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | TODO | 검색확장 layer 부재 — search/ 모듈 신설 | event enrichment 경로 없음 | ingestion과 분리된 패키지 scaffold | import smoke 통과, 인터페이스 stub |
| 2 | TODO | provider-agnostic SearchProvider 추상 | 단일 provider 락인 방지 | query(q,opts)->NormalizedHits ABC | 2+ 구현체 동일 인터페이스 |
| 3 | RISK | Bing Web Search 폐지(2025-08) 의존 금지 | dead provider 전량 실패 | Bing 직접 호출 0건 | grep bing active 호출 없음 |
| 4 | RISK | Brave 무료티어 폐지(2026-02) 비용 인지 | 무료 가정 시 예산 초과 | Brave 유료 fallback tier | 비용 추정에 Brave 단가 명시 |
| 5 | COMMERCIAL | NewsData.io 무료 200/day 상업가능 | 무료+상업 동시 드묾 | 기본 뉴스 보강 provider | 라이선스 상업가능 근거 보존 |
| 6 | COMMERCIAL | NewsAPI.org 무료=localhost, 운영 $449/mo | 운영 배포 시 무료 불가 | 프로토타입 외 의존 금지 | 운영 코드 무료 가정 없음 |
| 7 | TODO | GDELT DOC2.0 광역 event 탐지 connector | 무료 글로벌 1차 그물 | rate-limit 준수 client + 백오프 | GDELT 쿼리 1건 정상 파싱 |
| 8 | RISK | GDELT 단독 의존도 단일 장애점 | provider 다양성 원칙 | 최소 2 provider corroboration | event 1건당 ≥2 소스 교차확인 |
| 9 | TODO | Google CSE connector(무료 쿼터 소량) | 정밀 검색 보조 | 일 쿼터 카운터 + 초과 차단 | 무료쿼터 초과 호출 0건 |
| 10 | COMMERCIAL | SerpAPI는 SERP 대행 — 단가 높음 | routine 호출 시 비용 폭증 | 최종 검증/감사 경로에만 | SerpAPI 호출이 per-event 상한 내 |
| 11 | TODO | query formulation: entity+action+timewindow | 무관 문서 확장 방지 | candidate에서 구조화 쿼리 생성기 | 추출 쿼리가 entity/시간창 포함 |
| 12 | TODO | 다국어/지역 쿼리 변형 생성 | 글로벌 event 누락 방지 | 언어/지역 변형 매핑 | 비영어 event에 현지어 쿼리 |
| 13 | TODO | citation expansion: 1차 hit→primary | 2차 보도 중복 제거 | outbound link + canonical | 동일 사건 primary 1건 수렴 |
| 14 | TODO | source diversity 강제 | 단일 매체 편향 방지 | diversity scorer + 쿼터 | 단일 매체 점유율 상한 이하 |
| 15 | RISK | 검색API ToS 우회·스크래핑 금지 | 법무/계정 정지 | 공식 API만 사용 | 비공식 스크래핑 0건 |
| 16 | RISK | robots/저작권 준수(본문 저장 범위) | 저작권 침해 | 메타+발췌+링크 저장 | 전문 저장 위반 0건 |
| 17 | TODO | per-event 호출 상한(budget guard) | 무한 확장·비용 폭증 | event당 max API call 카운터 | 상한 초과 시 호출 중단 |
| 18 | TODO | 무료쿼터 우선소진 → 유료 fallback | 비용 최소화 | tiered provider router | 무료 잔량>0 시 유료 미호출 |
| 19 | RISK | provider rate-limit 위반 시 차단 | 계정 정지 | provider별 cooldown/backoff | 429 발생률 임계 이하 |
| 20 | TODO | 검색 결과 dedup→기존 raw_events 병합 | 중복 event 폭증 방지 | dedup key(canonical/entity hash) | 중복 event 병합률 측정 |
| 21 | AGENT_HINT | candidate→검색쿼리 LLM 프롬프트 | 쿼리 품질이 확장 품질 결정 | 엄격 schema query generator | 쿼리 JSON schema 통과 |
| 22 | AGENT_HINT | 검색 hit 관련성 LLM 재랭킹 | API 랭킹과 event 관련성 불일치 | relevance scorer | 무관 hit 필터링율 측정 |
| 23 | RISK | LLM query gen 비용/지연 | 호출 폭증 | 배치·캐시·쿼리 재사용 | 동일 event 쿼리 캐시 hit |
| 24 | COMMERCIAL | Guardian 무료 5000/day | 고품질 무료 영문 | 영문 보강 provider | Guardian 쿼터 내 호출 |
| 25 | COMMERCIAL | GNews 무료 100/day 저용량 | 소량 무료 보강 | 보조 tier | 일 100 초과 0건 |
| 26 | COMMERCIAL | Mediastack $24.99 entry | 저비용 유료 옵션 | 비용/용량 트레이드오프 평가 | 채택 시 용량 한계 문서화 |
| 27 | COMMERCIAL | Perigon 1M articles/day 대용량 | 고용량 필요시 후보 | 비용 대비 평가(미채택 기본) | 채택 근거/비용 명시 |
| 28 | RISK | provider 라이선스 상업이용 상이 | 상업 배포 법무 | provider별 라이선스 매트릭스 | 상업가능 여부 전 provider 기록 |
| 29 | TODO | NormalizedHit 스키마 | provider간 정규화 | 공통 pydantic 모델 | 모든 provider 동일 스키마 |
| 30 | TODO | 검색 layer를 ingestion과 격리 | deterministic 오염 방지 | 별도 패키지·호출 경로 | ingestion/ 코드 변경 0 |
| 31 | AGENT_HINT | LangGraph 노드로 search expansion 편입 | 추론 그래프 enrichment 연결 | candidate→expand→merge 노드 | 노드 단위 테스트 통과 |
| 32 | TODO | 검색 호출 결과 캐시(TTL) | 동일 쿼리 반복 비용 | Redis 캐시 + TTL | 캐시 hit 시 API 미호출 |
| 33 | RISK | 캐시 staleness vs freshness | 오래된 결과로 event 왜곡 | event 타입별 TTL 차등 | freshness 요구 event 짧은 TTL |
| 34 | TODO | provider health check + 자동 폐기 감지 | 폐지 provider 무한 실패 방지 | health probe + circuit breaker | dead provider 자동 격리 |
| 35 | RISK | API key 노출 위험(.env만) | 키 유출 시 과금/정지 | os.getenv/pydantic only | 하드코딩 키 0건 |
| 36 | RISK | 에러 메시지에 key 마스킹 | 로그로 키 유출 | 예외 핸들러 마스킹 | 로그에 키 평문 0건 |
| 37 | TODO | 검색 비용 텔레메트리 | 예산 추적 불가 시 폭주 | per-provider counter | 호출/비용 메트릭 수집 |
| 38 | TODO | 월 예산 상한 + 초과 시 유료 차단 | 비용 통제 | global budget guard | 예산 초과 시 유료 off |
| 39 | AGENT_HINT | corroboration count를 신뢰 신호로 | 단일 출처 오보 위험 | ≥N 독립 소스 시 신뢰 상승 | 신뢰 점수에 출처 수 반영 |
| 40 | RISK | 검색 결과 misinformation 유입 | 저신뢰 소스 오염 | source allowlist/신뢰도 가중 | 저신뢰 소스 가중 하향 |
| 41 | TODO | timewindow 필터(event 시점 ±N) | 과거 무관 문서 배제 | 검색 쿼리 날짜 범위 | 시간창 밖 hit 비율 하락 |
| 42 | TODO | 지역 geo 필터링 | event 지역 무관 배제 | geo param/도메인 필터 | 지역 event geo 정합성 |
| 43 | AGENT_HINT | 투자조언 톤 출력 금지(원칙1) | 정책 위반 방지 | 출력 후처리 가드 | 매수/매도 표현 0건 |
| 44 | RISK | 검색 snippet 저작권 | 저작권 | snippet 길이 제한·링크 우선 | 전문 재배포 0건 |
| 45 | TODO | 다중 provider 결과 병합·랭킹 통합 | provider별 랭킹 상이 | 통합 rank fusion | 병합 결과 단일 정렬 |
| 46 | TODO | 검색 실패 graceful degradation | 한 provider 실패가 전체 실패 | fallback chain | 1 provider 실패 시 정상 |
| 47 | RISK | 무료티어 정책 변경 추적 부재 | Brave식 갑작 폐지 | provider 정책 변경 모니터 | 정책 변경 시 알림 경로 |
| 48 | COMMERCIAL | 검색API 단가 변동성 | 예산 예측 불가 | 단가 가정 정기 갱신 | 단가표 최신성 유지 |
| 49 | TODO | 쿼리당 결과 수 상한 | 과다 fetch 비용 | per-query result cap | 결과 수 상한 준수 |
| 50 | AGENT_HINT | event entity 추출 정확도가 쿼리 품질 좌우 | 잘못된 entity→무관 확장 | NER/LLM entity 검증 | entity 추출 정확도 측정 |
| 51 | TODO | 검색 결과→Milvus 임베딩 연계 | 의미 검색 보강 | hit 임베딩 후 dedup | 임베딩 파이프 연결 |
| 52 | TODO | 검색 결과→OpenSearch 색인 연계 | 키워드 검색 보강 | hit 색인 경로 | 색인 후 조회 가능 |
| 53 | RISK | 임베딩 비용(OpenAI) 폭증 | 대량 hit 임베딩 | dedup 후에만 임베딩 | 중복 hit 임베딩 미발생 |
| 54 | TODO | 언어 감지 후 번역/정규화 | 다국어 event 처리 | lang detect + 정규화 | 비영어 hit 언어 태깅 |
| 55 | AGENT_HINT | 검색 확장은 candidate 있을 때만(pull) | 무차별 검색 비용 폭증 | event-triggered 호출만 | 무 candidate 시 검색 0건 |
| 56 | RISK | 검색 layer가 ingestion freshness 가정 깸 | 지연 유입 event 왜곡 | enrichment 비동기 분리 | ingestion latency 영향 없음 |
| 57 | TODO | provider별 timeout/retry 정책 | 느린 provider 그래프 블록 | per-provider timeout | timeout 초과 시 skip |
| 58 | TODO | 검색 호출 audit log | 비용/디버깅 추적 | 호출 로그(쿼리/provider/cost) | 호출 audit 조회 가능 |
| 59 | RISK | PII 검색 결과 유입 | GDPR 위반 | PII 필터/마스킹 | PII 노출 0건 정책 |
| 60 | COMMERCIAL | 무료/유료 혼합 비용 모델 문서화 | 비용 결정 근거 | 비용 모델 문서 | 비용 모델 검토 가능 |
| 61 | TODO | 검색 결과 canonical URL 정규화 | dedup key 일관성 | URL canonicalizer | 동일 문서 단일 URL |
| 62 | TODO | event-검색결과 link join 테이블 | 추적성 | event_id↔hit 매핑 | 매핑 조회 가능 |
| 63 | AGENT_HINT | 확장 결과를 event 요약에 인용 | 출처 추적성 | citation 부착 | 요약에 출처 링크 |
| 64 | RISK | 과확장(over-expansion) noise 유입 | event 정의 희석 | 관련성 임계 컷오프 | 임계 미만 hit 폐기 |
| 65 | TODO | provider 우선순위 설정 가능화 | 비용/품질 튜닝 | config 기반 우선순위 | config로 순서 변경 |
| 66 | RISK | config 우선순위 오설정 | 무료 우선 깨짐 | config 검증 | 잘못된 우선순위 거부 |
| 67 | TODO | 검색 layer 단위 테스트(모킹) | 회귀 방지 | provider mock fixture | mock 테스트 통과 |
| 68 | TODO | 통합 테스트(실호출, rate-gate) | 실제 동작 검증 | rate gate 허용 시만 live | live 테스트 게이트 통과 |
| 69 | RISK | live 테스트가 쿼터 소진 | 무료쿼터 낭비 | 게이트/스킵 기본 | CI 기본 live off |
| 70 | AGENT_HINT | 검색 결과 신뢰도→event ranking 반영 | 랭킹 품질 | source trust → rank weight | 랭킹에 trust 반영 |
| 71 | TODO | 검색 trigger 정책 | 전수 확장 비용 | 우선순위 candidate만 확장 | 저우선 candidate 미확장 |
| 72 | RISK | 검색 결과 무한 루프(확장의 확장) | 비용/시간 폭증 | 확장 depth 상한 | depth 상한 준수 |
| 73 | TODO | snippet→event 본문 보강 매핑 | event 내용 빈약 | snippet/메타 보강 | event에 보강 필드 |
| 74 | COMMERCIAL | provider별 SLA/uptime 평가 | 운영 안정성 | SLA 비교 문서 | SLA 평가 기록 |
| 75 | RISK | 단일 결제수단/계정 의존 | 계정 정지 시 전체 중단 | 키/계정 분산 검토 | 단일 실패점 인지 |
| 76 | TODO | 검색 layer feature flag | 점진 롤아웃 | flag로 on/off | flag off 시 미동작 |
| 77 | AGENT_HINT | LLM 재랭킹 프롬프트 schema 고정 | 출력 파싱 안정성 | strict JSON schema | schema 위반 0건 |
| 78 | RISK | LLM hallucination이 확장 오염 | 가짜 출처/요약 | 출처 URL 실재 검증 | 미실재 URL 차단 |
| 79 | TODO | 검색 결과 신선도(timestamp) 검증 | 날짜 위조/누락 | ts 파싱·검증 | ts 없는 hit 처리 정의 |
| 80 | TODO | provider 응답 스키마 변동 대응 | API 변경 시 파싱 깨짐 | 방어적 파싱+버전 핀 | 스키마 변경 시 graceful |
| 81 | RISK | 검색 의존이 deterministic 원칙 약화 | 비결정 결과 유입 | 확장 결과는 별 신뢰등급 | deterministic 경로 불변 |
| 82 | AGENT_HINT | event 유형별 검색 전략 분기 | 유형마다 최적 provider 상이 | type→provider 매핑 | 유형별 전략 적용 |
| 83 | TODO | 검색 비용 일/월 리포트 | 비용 가시성 | 집계 리포트 | 리포트 생성됨 |
| 84 | RISK | 환율/가격 통화 변동(USD) | 예산 오차 | USD 기준 예산 | 통화 가정 명시 |
| 85 | COMMERCIAL | 무료티어 ToS 상업이용 조항 재확인 | 상업 배포 적법성 | provider별 ToS 인용 | 상업이용 가부 확정 |
| 86 | TODO | 검색 결과 언어별 품질 편차 대응 | 비영어 품질 저하 | 언어별 provider 선택 | 언어별 품질 평가 |
| 87 | RISK | rate-limit 백오프 미구현 시 폭주 | 429 폭증·차단 | 지수 백오프 | 백오프 동작 검증 |
| 88 | TODO | 검색 hit→raw_events 적재 스키마 정합 | 다운스트림 호환 | raw_events 스키마 매핑 | 적재 스키마 검증 |
| 89 | AGENT_HINT | 확장 전 dedup으로 중복 쿼리 차단 | 동일 event 중복 확장 | event dedup 선행 | 중복 event 미확장 |
| 90 | RISK | 검색 결과 paywall 콘텐츠 처리 | 본문 접근 불가/위반 | paywall 감지·메타만 | paywall 전문 미저장 |
| 91 | TODO | provider 추가/제거 플러그인화 | 신규 provider 편입 용이 | registry 패턴 | 신규 provider 등록만으로 동작 |
| 92 | TODO | 검색 결과 품질 메트릭 | 품질 모니터링 | 메트릭 수집 | 품질 메트릭 산출 |
| 93 | RISK | 무료→유료 전환 시점 비용 급증 | 예산 충격 | 임계 알림 | 무료 소진 임박 알림 |
| 94 | COMMERCIAL | 연간 계약 vs 종량제 비교 | 비용 최적화 | 가격 모델 비교 | 비교 문서화 |
| 95 | AGENT_HINT | 확장 결과 노출 시 출처 명시 | 신뢰성/추적성 | UI citation 의무 | 노출 결과 출처 부착 |
| 96 | RISK | 검색 layer 장애가 앱 전체 영향 | 결합도 과다 | 비동기·격리 호출 | 검색 다운 시 앱 정상 |
| 97 | TODO | 검색 결과 캐시 무효화 정책 | stale 캐시 잔존 | 명시적 invalidation | 무효화 동작 검증 |
| 98 | TODO | provider별 결과 수/품질 A/B 평가 | provider 선택 근거 | A/B 평가 하니스 | 평가 결과 기록 |
| 99 | RISK | 검색 확장 범위 무제한 확대 | 범용 검색엔진화 위험 | event 인텔리전스 범위 고정 | 범위 외 기능 거부 |
| 100 | TODO | 검색 layer 문서화(아키텍처/비용/ToS) | 운영·인수인계 | 설계 문서 작성 | 문서 리뷰 통과 |

**완전 달성 기준:** provider-agnostic 추상화 위 무료(GDELT/NewsData.io/Guardian/GNews) 우선 → 유료(Brave/CSE/SerpAPI) fallback tiered router 동작, candidate→query formulation→citation/diversity 확장→dedup→raw_events 적재 연결, per-event·월 예산 guard·rate-limit 백오프·ToS/저작권/PII 준수·health/circuit-breaker·corroboration 신뢰신호·deterministic 불변, mock+게이트 live 통합 테스트 통과.

## L3. Policy-safe fetch / body extraction / evidence gate — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | source_policy_probe로 정책안전 fetch 단일 진입 | 우회 코드 우발 실행 차단 | run_collection_probe 3-way 라우팅 | 모든 fetch가 probe 경유 |
| 2 | IMPLEMENTED | CAPTCHA/login/paywall/robots 감지 시 BLOCKED_TERMINAL | 우회 시도 원천 차단 | STRATEGY blocker 4종 terminal | blocker 감지=즉시 terminal |
| 3 | POLICY | robots.txt allowlist 준수 | ToS/접근정책 위반 방지 | allowlist 외 도메인 거부 | 비허용 도메인 fetch=거부 |
| 4 | IMPLEMENTED | EvidenceGate synthetic/dead URL 거부 | 합성 slug 안정증거 둔갑 방지 | producthunt/culture shell 패턴 거부 | synthetic URL=gate reject |
| 5 | IMPLEMENTED | local/private URL 외부 둔갑 차단 | SSRF·증거위조 방지 | _is_local_or_synthetic | localhost/127.0.0.1=reject |
| 6 | IMPLEMENTED | 전문 저장 금지(raw_text="" 기본) | 저작권 재배포 차단 | bridge 기본값 | raw_text 비어있음 |
| 7 | IMPLEMENTED | body cascade: selector→trafilatura→readability→dom | 안정 본문 추출 | 우선순위 cascade | 4계층 순차 적용 |
| 8 | POLICY | 원문 artifact 내부저장·gitignored | 외부 공개 분리 | .gitignore 9종 | git에 원문 커밋 0 |
| 9 | IMPLEMENTED | gdelt min_interval 60s/cooldown 900s | provider rate limit 준수 | rate_limit_policy.yaml | 60s 위반=차단 |
| 10 | IMPLEMENTED | google_trends_explore 7200s/retry 0 | 우회 금지 강제 | min_interval 7200s | retry_on_429=0 |
| 11 | TODO | SSRF allowlist: 프로토콜+도메인 이중 검증 | 내부망 접근 방지 | http/https only + 도메인 allowlist | non-allowlist=reject |
| 12 | TODO | IP resolve 후 사설/메타데이터 차단 | 클라우드 크리덴셜 탈취 방지 | resolve→169.254.169.254 차단 | 사설/메타IP=reject |
| 13 | TODO | redirect 비활성화 | redirect 통한 allowlist 우회 차단 | follow_redirects=False | 3xx=중단 |
| 14 | TODO | 일관 URL 파싱(parser differential) | parser 차이 통한 bypass 차단 | 단일 파서 정규화 | 파싱 일관성 테스트 |
| 15 | IMPLEMENTED | 429 감지→record_rate_limited 영속 | cooldown 재기동 유지 | local_file/redis backend | 재기동 후 cooldown 유지 |
| 16 | POLICY | proxy rotation 금지 | anti-bot 우회 금지 | 전략에 proxy 미포함 | proxy 코드 0 |
| 17 | POLICY | 내부 RPC/비공개 API 호출 금지 | ToS 위반 차단 | 공식 라우트만 | 비공개 endpoint 0 |
| 18 | IMPLEMENTED | 공식 라우트 우선(SEC/OpenDART/Guardian) | 적법 수집 보장 | API_PROBE_SPEC | 공식 API 우선 라우팅 |
| 19 | IMPLEMENTED | ap_news Google News RSS 프록시 | 직접 스크랩 회피 | RSS 경유 | RSS items 정상 |
| 20 | IMPLEMENTED | newsapi /v2/everything 전환 | 무료티어 endpoint 준수 | everything 엔드포인트 | 200 응답 |
| 21 | RISK | newsapi.org 무료=localhost/dev only | 상업 배포 시 ToS 위반 | 상업 시 제외/유료 | 상업모드 newsapi off |
| 22 | RISK | guardian 재배포 금지 | 전문 게시=위반 | 요약+URL만 | 본문 게시 0 |
| 23 | RISK | nyt 상업 라이선스 필요 | 무라이선스 상업=위반 | 라이선스 확보 전 비상업 | 상업 시 라이선스 확인 |
| 24 | COMMERCIAL | NewsData.io 상업 가능 | 상업 표면 후보 | 상업모드 우선 소스 | ToS 상업조항 확인 |
| 25 | IMPLEMENTED | enrichment query budget 상한 | quota 초과 차단 | per-source budget | budget 초과=중단 |
| 26 | IMPLEMENTED | serper/tavily/exa 이벤트 트리거 전용 | 정기 폴링 quota 보존 | 폴링 금지 | 정기 폴링 0 |
| 27 | IMPLEMENTED | alpha_vantage 25/day 일1회 고정 | 무료 quota 준수 | daily bucket | 25/day 미초과 |
| 28 | TODO | retention TTL 정책 정의 | 저장 데이터 보존기간 제한 | raw artifact TTL | TTL 만료 삭제 |
| 29 | POLICY | publication boundary 수집경로 미연결 | 재배포 경로 격리 | 게시계층 분리 | 수집→게시 직결 0 |
| 30 | IMPLEMENTED | secret 출력 금지(존재/길이만) | 키 유출 방지 | scan_secrets gate | secret scan PASS |
| 31 | TODO | body 추출 시 paywall 콘텐츠 감지 차단 | 페이월 우회 방지 | paywall marker 감지 | paywall=terminal |
| 32 | TODO | extracted_text 길이 상한(인용범위) | fair use 초과 방지 | 요약 길이 cap | 본문 전체저장 0 |
| 33 | IMPLEMENTED | dcinside 본문 실패→신호 source | 본문 재배포 회피 | role 재정의 | 본문 큐 0 |
| 34 | POLICY | dcinside 금융 갤러리 internal_queue_only | 펌핑 게시 차단 | publish_blocked | 펌핑 제목 게시 0 |
| 35 | IMPLEMENTED | EvidenceGate require_body 옵션 | 본문 필수 소스 검증 | gate_records | body 필수 소스 검증 |
| 36 | TODO | source별 ToS rate limit 문서화 | 약관 명시 한도 준수 | per-source policy note | rate_limit_evidence 갱신 |
| 37 | RISK | google_programmable_search CX 미설정 | 재활성화 시 오작동 | 비활성 유지 | 재활성 0 |
| 38 | POLICY | reuters 라이선스+bot 차단 제외 유지 | 라이선스 위반 방지 | MVP_EXCLUDED | 수집 0 |
| 39 | POLICY | x(Twitter) 유료 API 제외 | 무단 수집 방지 | MVP_EXCLUDED | 수집 0 |
| 40 | POLICY | blind login wall 제외 | login 우회 금지 | MVP_EXCLUDED | 수집 0 |
| 41 | POLICY | fmkorea Cloudflare Turnstile 제외 | CAPTCHA 우회 금지 | MVP_EXCLUDED | 수집 0 |
| 42 | IMPLEMENTED | UA 필수 소스(gdelt) UA 설정 | provider 요구 준수 | UA 헤더 | UA 누락=차단 |
| 43 | TODO | extracted_text 출처 metadata 강제 | 인용 표기 의무 | source attribution 필드 | attribution 누락=reject |
| 44 | IMPLEMENTED | 장문 query 절단(truncate_query) | API 오류 방지 | truncate_query | 길이 초과 절단 |
| 45 | IMPLEMENTED | gdelt phrase quoting 전처리 | 오류응답 방지 | _apply_query_override | 따옴표 처리 확인 |
| 46 | TODO | redirect chain 로깅·검증 | 우회 경로 추적 | redirect 비활성+로깅 | redirect 시도 기록 |
| 47 | POLICY | google_trends_explore PASS 표기 금지 | 우회 사칭 방지 | CONFIRMED_EXTERNAL_RATE_LIMIT | PASS 표기 0 |
| 48 | IMPLEMENTED | fallback chain 0 bypass 입증 | 우회 없는 대체경로 | RSS export/news enrichment | bypass 0건 |
| 49 | TODO | extracted_text PII 스크럽 | 개인정보 저장 최소화 | PII 마스킹 | PII 노출 0 |
| 50 | IMPLEMENTED | health gate 네트워크 미호출 즉시반환 | cooldown 중 불필요 호출 차단 | BLOCKED/cooldown gate | 차단 소스 호출 0 |
| 51 | TODO | source_policy_probe robots 캐시 TTL | stale robots 사용 방지 | robots TTL 갱신 | TTL 만료 재조회 |
| 52 | TODO | content-type 검증(html/json만) | 비정상 payload 차단 | content-type allowlist | 비허용 type=거부 |
| 53 | TODO | 응답 크기 상한(DoS·과수집 방지) | 과대 본문 저장 방지 | max body size | 상한 초과=절단 |
| 54 | IMPLEMENTED | naver search budget ≤200/day | quota 1% 미만 유지 | budget cap | 200 초과=중단 |
| 55 | IMPLEMENTED | youtube search ≤50/day | units/day 준수 | budget cap | 50 초과=중단 |
| 56 | TODO | extracted_text 저장 전 dedup hash | 중복 원문 저장 방지 | dedupe_key | 중복 저장 0 |
| 57 | POLICY | 시장 numeric_signal 분류 | 투자조언 분리 | NUMERIC_SIGNAL_SOURCES | 가치판단 0 |
| 58 | TODO | source별 license 메타 필드 | 상업 가부 자동판정 | license field | license 미상=비상업 |
| 59 | IMPLEMENTED | federal_register url+date+abstract만 | 공식 metadata 한정 | 필드 제한 | 전문 0 |
| 60 | IMPLEMENTED | sec_edgar 10req/s 공개 한도 준수 | 공개 한도 위반 방지 | entity query ≤50 | 50 초과=중단 |
| 61 | TODO | extracted_text 언어 감지 후 요약 길이 | 인용범위 일관성 | lang-aware cap | 길이 정책 적용 |
| 62 | POLICY | opendart 공식 API 라우트 | 적법 수집 | API_PROBE | 공식 endpoint |
| 63 | TODO | fetch 타임아웃 강제 | hang·자원고갈 방지 | timeout 설정 | timeout 적용 |
| 64 | IMPLEMENTED | screenshots gitignored | 화면 원문 비커밋 | .gitignore | 커밋 0 |
| 65 | TODO | error 메시지 secret 마스킹 | 키 노출 방지 | 마스킹 필터 | 에러에 키 0 |
| 66 | IMPLEMENTED | rate_limit backend local_file 권장 | 재기동 cooldown 유지 | INGESTION_RATE_LIMIT_BACKEND | 재기동 유지 |
| 67 | TODO | allowlist 변경 audit 로그 | 무단 도메인 추가 방지 | allowlist diff 로깅 | 변경 기록 |
| 68 | POLICY | enrichment 정기폴링 금지(serper 등) | 크레딧 보존 | 트리거 전용 | 폴링 0 |
| 69 | TODO | body 추출 robots noindex 존중 | 게시 정책 정렬 | noindex 감지 | noindex=게시 보류 |
| 70 | IMPLEMENTED | dcinside search_url→본문 e2e | 영구 path 안정 | search path | e2e 성공 |
| 71 | TODO | extracted_text 저작권 라이선스 태그 | 재배포 판정 근거 | license tag | 태그 부착 |
| 72 | IMPLEMENTED | hacker_news title+url+time만 | metadata 한정 | detail 2차 호출 | 전문 0 |
| 73 | TODO | fetch 동시성 상한(politeness) | 서버 부하·차단 방지 | concurrency cap | 동시 호출 제한 |
| 74 | IMPLEMENTED | igdb url+date metadata | 공식 필드 한정 | 필드 매핑 | 전문 0 |
| 75 | TODO | response 캐시 TTL(중복 호출 절감) | quota·politeness | cache_ttl | TTL 적용 |
| 76 | POLICY | krx_kind 공식 API 전환 대기 | 비공식 경로 금지 | DEFERRED | 비공식 수집 0 |
| 77 | TODO | extracted_text 저장 위치 접근통제 | 내부 유출 방지 | 접근 권한 | 무권한 접근 0 |
| 78 | IMPLEMENTED | bok_ecos/eia 샘플 매핑 | metadata 한정 | _SAMPLE_PATHS | 전문 0 |
| 79 | TODO | SSRF 검사 단위 테스트 | 회귀 방지 | 사설/메타IP 테스트 | 테스트 통과 |
| 80 | TODO | URL 정규화 후 재검증 | bypass 차단 | normalize→recheck | 정규화 일관 |
| 81 | IMPLEMENTED | culture_info 날짜 매핑 | 공식 record | period2_detail2 | contract_pass |
| 82 | POLICY | provider rate limit 무시 연속재시도 금지 | ToS 위반 차단 | max_retries 제한 | 연속재시도 0 |
| 83 | TODO | extracted_text 보존기간 만료 잡 | retention 강제 | TTL cron | 만료 삭제 실행 |
| 84 | IMPLEMENTED | EvidenceGate shape 린터 | 증거 형태 검증 | gate_records | 형태 위반=reject |
| 85 | TODO | 외부 fetch IP allowlist도 고려 | egress 통제 | egress 정책 | 비허용 egress 0 |
| 86 | POLICY | 산출물 gitignored 검증 | secret/원문 비커밋 | scan_secrets | 커밋 0 |
| 87 | TODO | content negotiation 헤더 명시 | 일관 응답 | Accept 헤더 | 헤더 일관 |
| 88 | IMPLEMENTED | tmdb/kopis/aladin metadata 한정 | 도메인 record | 필드 매핑 | 전문 0 |
| 89 | RISK | aladin 개인 free, 상업 별도 | 상업 시 라이선스 | 상업 가부 확인 | 상업 시 라이선스 |
| 90 | TODO | fetch 실패 backoff 지수증가 | 서버 부하 방지 | exponential backoff | backoff 적용 |
| 91 | IMPLEMENTED | publication boundary yaml+모듈 | 재배포 격리 가드 | boundary guard | 미연결 확인 |
| 92 | TODO | extracted_text snippet 최대 길이 강제 | fair use 준수 | snippet cap | cap 초과 절단 |
| 93 | POLICY | 우회 제안 거부(SourceSupervisor) | LLM 우회 유도 차단 | supervisor 거부 | 우회 제안 0 |
| 94 | TODO | robots Crawl-delay 존중 | politeness | crawl-delay 파싱 | delay 적용 |
| 95 | IMPLEMENTED | its/kma 샘플 매핑 | metadata 한정 | _SAMPLE_PATHS | 전문 0 |
| 96 | TODO | fetch 도메인별 정책 override 검토 | 약관별 차등 | per-domain policy | 정책 적용 |
| 97 | POLICY | mirror target 기본(실 PG 미연결) | 데이터 유실 아님 검증 | bridge mirror | 계약 검증 |
| 98 | TODO | extracted_text 출처 URL 무결성 검증 | dead/synthetic 방지 | URL liveness | live URL만 |
| 99 | IMPLEMENTED | scan_secrets 2계층 gate | secret 유출 차단 | baseline+종료 | exit code gate |
| 100 | TODO | L3 정책 회귀 테스트 스위트 | 무회귀 보장 | 정책 테스트 | 전 테스트 통과 |

**완전 달성 기준:** 모든 외부 fetch가 source_policy_probe 단일 경유+robots allowlist 준수, SSRF allowlist/IP 차단/redirect 비활성/일관 URL 파싱 4종 TODO→IMPLEMENTED + 단위테스트, EvidenceGate가 synthetic/dead/local URL 100% 거부, 전문 저장 0건(raw_text=""+인용 cap+TTL), RISK 소스 license 자동판정, 우회 0 + rate limit 위반 0.

## L4. EventQueue / raw_events / Redis stream — 100 Insights

**완전 달성 기준:** A `EventQueue.enqueue()` 출력이 `stream:raw_events` XADD → B `group:ingest` consumer XREADGROUP+xack 소비, 미처리분 PEL→DLQ 회수, JSONL은 `REDIS_URL` 미설정 시만, content_hash dedup 재실행 collapse, AOF 크래시 내구성.

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | B producer XADD stream:raw_events | A→B 배선 타깃 확정 | producer.py 재사용 | XADD가 msg_id 반환 |
| 2 | IMPLEMENTED | B consumer XREADGROUP group:ingest | 소비 경로 완성됨 | consumer.py 재사용 | xack 후 PEL 비움 |
| 3 | IMPLEMENTED | consumer heartbeat touch | healthcheck 60s 임계 | /tmp/worker_heartbeat | stale 시 재시작 |
| 4 | IMPLEMENTED | ensure_group BUSYGROUP 무시 | 재기동 멱등 | redis.py | 재호출 예외 없음 |
| 5 | IMPLEMENTED | AOF appendonly yes | 크래시 시 분단위 유실 방지 | compose redis | RDB-only 아님 |
| 6 | TODO | A _redis_enqueue NotImplementedError | P0 갭: A 출력 미배선 | event_queue.py 배선 | enqueue가 XADD 호출 |
| 7 | TODO | A _redis_dequeue 스텁 | 멀티워커 공유 큐 부재 | XREADGROUP 위임 | dequeue 왕복 |
| 8 | TODO | A _redis_peek 스텁 | 큐 가시성 부재 | XRANGE 위임 | peek count 일치 |
| 9 | TODO | A _redis_mark_done 스텁 | ack 경로 부재 | xack 위임 | PEL 비움 |
| 10 | TODO | A payload→B RawEvent 계약 정합 | 스키마 불일치 reject | to_raw_event_create 매핑 | source/url/fetched_at 채움 |
| 11 | TODO | content_hash dedup 재실행 collapse | 중복 적재 방지 | bridge sha256 재사용 | 재실행 written 0 |
| 12 | TODO | url NOT NULL hold 정책 | 가짜 url 생성 금지 | BRIDGE_STATUS_HELD | missing_url → held |
| 13 | TODO | DLQ stream:raw_events:dlq | poison 메시지 격리 | N회 reclaim 실패 시 XADD | DLQ에 격리됨 |
| 14 | TODO | XPENDING 기반 reclaim(XCLAIM) | 죽은 컨슈머 메시지 회수 | min-idle-time claim | orphan 재처리 |
| 15 | TODO | stream MAXLEN 트림 | 무한 성장 메모리 압박 | XADD MAXLEN ~ N | XLEN 상한 유지 |
| 16 | TODO | JSONL 폴백 REDIS_URL 미설정만 | 개발/테스트 동일 동작 | _use_redis 분기 유지 | 폴백 회귀 0 |
| 17 | RISK | JSONL _jsonl_dequeue 전체 rewrite | 대용량 시 O(n) I/O | Redis 전환으로 해소 | Redis 모드 시 비적용 |
| 18 | RISK | JSONL 동시 쓰기 race | 멀티프로세스 손상 | Redis 원자성으로 해소 | 단일 프로세스만 JSONL |
| 19 | RISK | Windows file lock(JSONL) | PermissionError | Redis 전환 권장 | atomic replace 폴백 |
| 20 | TODO | db 분리 broker=db0/stream 정책 | 키 충돌 방지 | DB 분리 | stream db 고정 |
| 21 | AGENT_HINT | source-ingestion-engineer 배선 담당 | 코드 구현 위임 | handoff | 스텁 4개 구현 |
| 22 | TODO | enqueue 실패 시 JSONL mirror | Redis 다운 시 유실 방지 | dual-write fallback | Redis 실패→mirror |
| 23 | TODO | msg_id ↔ A item_id 매핑 | mark_done 식별 | id 보존 dict | id 왕복 일치 |
| 24 | RISK | decode_responses 불일치 | bytes/str 혼선 | redis.py 일관 설정 | 디코딩 통일 |
| 25 | TODO | fetched_at ISO 직렬화 | B payload 계약 | isoformat 보장 | 파싱 가능 |
| 26 | TODO | raw_metadata JSON 직렬화 | 중첩 dict 평탄화 | json.dumps | XADD 수용 |
| 27 | IMPLEMENTED | test_stream_payload_compat | payload 회귀 가드 | B 테스트 존재 | 통과 유지 |
| 28 | TODO | consumer 예외 시 무한루프 방지 | except 후 ack 안 함 | retry count + DLQ | poison 무한재처리 0 |
| 29 | RISK | consumer.py except가 ack 누락 | PEL 영구 적체 | DLQ 라우팅 필요 | 적체 모니터 |
| 30 | TODO | block timeout 튜닝(5000ms) | idle CPU vs 지연 | XREADGROUP block | burst 시 지연 측정 |
| 31 | TODO | count=10 배치 크기 | 처리량 vs 메모리 | XREADGROUP count | burst 흡수 확인 |
| 32 | AGENT_HINT | orchestrator-architect stream 토폴로지 | 큐 분리 설계 | handoff | q_fast/default/browser |
| 33 | TODO | q_browser 동시성 2 제한 | CPU 보호(Playwright) | Celery concurrency | 동시 2 초과 0 |
| 34 | TODO | enqueue 멱등(min_interval 잠금) | 중복 호출 차단 | SET NX EX interval | 동시 2워커 1회만 |
| 35 | RISK | event burst 시 PEL 폭증 | 소비 지연 누적 | XPENDING 알람 | 임계 초과 알람 |
| 36 | TODO | burst backpressure | producer 폭주 방지 | MAXLEN + rate gate | stream 상한 |
| 37 | IMPLEMENTED | Streams sub-10ms/수십만s | burst 흡수 가능 | Redis Streams 특성 | 지연 측정 |
| 38 | TODO | Kafka 불필요 판정 | 무한보존/멀티파티션 과함 | Streams로 충분 | 규모 재평가 트리거 |
| 39 | COMMERCIAL | durable 큐 = 데이터 무손실 | 신뢰성 영업 포인트 | AOF + DLQ | 유실 0 입증 |
| 40 | TODO | stream 보존(hours-days) | 재처리 윈도 | MAXLEN 시간환산 | 보존 기간 명시 |
| 41 | TODO | consumer lag 지표 | 소비 뒤처짐 가시화 | XLEN-last-delivered | lag 대시보드 |
| 42 | TODO | DLQ 재투입 runbook | 수동 복구 절차 | XADD back to main | 재투입 검증 |
| 43 | RISK | google_trends_explore stream 적재 | PASS 둔갑 위험 | record_type 보존 | CONFIRMED 유지 |
| 44 | TODO | held 레코드 별도 stream | url 없는 항목 추적 | stream:held | held 가시화 |
| 45 | TODO | rejected 집계 critical | 스키마 실패 감지 | bridge schema_failures | failed>0 critical |
| 46 | IMPLEMENTED | bridge_contract_pass 게이트 | exit code 연동 | bridge_to_raw_events | contract fail 차단 |
| 47 | TODO | A→B run_id 전파 | trace 연결 | metadata run_id | 양쪽 run_id 일치 |
| 48 | TODO | enqueue/ack metric emit | 처리량 가시화 | counter 증가 | metric 노출 |
| 49 | RISK | redis_data 볼륨 손상 | 전체 큐 유실 | AOF + 백업 | 복구 절차 |
| 50 | TODO | stream 초기화(개발) 정책 | 테스트 격리 | 테스트 stream 분리 | prod stream 불변 |
| 51 | AGENT_HINT | operations-sre-agent PEL 모니터 | 운영 관측 | XPENDING 주기 조회 | 적체 알람 |
| 52 | TODO | XINFO STREAM 헬스 | stream 상태 점검 | XINFO 조회 | 헬스 노출 |
| 53 | TODO | consumer 재기동 시 PEL 재처리 | at-least-once 보장 | startup XCLAIM | 누락 0 |
| 54 | RISK | at-least-once 중복 처리 | 멱등성 필요 | content_hash dedup | 중복 collapse |
| 55 | TODO | downstream(Milvus/PG) 멱등 | 재처리 부작용 | on_conflict_do_nothing | 재실행 안전 |
| 56 | IMPLEMENTED | on_conflict_do_nothing(content_hash) | DB dedup | backend raw_event | 중복 무시 |
| 57 | TODO | EventQueue→discovery_collector 연결 | stub 미구현 | plans/012 §7 | NotImplementedError 해소 |
| 58 | TODO | event_candidate_extractor consumer | 큐 소비자 부재 | LLM 후속 라운드 | 범위 분리 |
| 59 | COMMERCIAL | 큐 분리 = 우선순위 SLA | 유료 티어 차등 | q_fast/default | 티어별 지연 |
| 60 | TODO | stream 키 네임스페이스 정책 | 환경 격리 | dev:/prod: prefix | 충돌 0 |
| 61 | RISK | A/B payload 계약 drift | 한쪽 변경 시 깨짐 | shared schema 테스트 | compat test |
| 62 | IMPLEMENTED | RawEvent pydantic 계약 | 타입 검증 | schemas/events.py | 검증 통과 |
| 63 | TODO | enqueue dry-run 모드 | 안전 테스트 | flag 분기 | 실 적재 0 |
| 64 | TODO | mark_done 미호출 누수 감지 | PEL 영구 적체 | idle 임계 알람 | orphan 검출 |
| 65 | TODO | stream consumer 수평확장 | 처리량 증대 | consumer 이름 분리 | N consumer 분산 |
| 66 | RISK | consumer 이름 충돌 | 메시지 중복배달 | unique consumer id | 충돌 0 |
| 67 | TODO | A enqueue 결과 jsonl 이중기록 | 감사 추적 | plans/012 §2.2 | dual write |
| 68 | TODO | stream→raw_events_service 배선 | B service 연결 | raw_event_service.py | DB 적재 |
| 69 | IMPLEMENTED | raw_events admin API | 운영 조회 | api/admin.py | 조회 동작 |
| 70 | TODO | 적재 실패 raw_events_failed 집계 | critical 트리거 | bridge writer.failed | failed>0 alert |
| 71 | TODO | stream 메시지 TTL/만료 | 오래된 미처리 정리 | MAXLEN 트림 | 만료 적용 |
| 72 | RISK | 무한 pending(소비자 0) | 큐 적체 침묵 | consumer 헬스 게이트 | 0 consumer 알람 |
| 73 | TODO | bridge held→재시도 정책 | url 확보 후 재적재 | held 큐 drain | held 해소 |
| 74 | AGENT_HINT | source-ingestion: held url 보강 | enrichment로 url 확보 | search enrichment | held 감소 |
| 75 | TODO | stream 백프레셔 메트릭 | producer 속도 제어 | XLEN 임계 | 제어 발동 |
| 76 | COMMERCIAL | 무손실+재처리 = 감사가능성 | B2B 계약 요건 | DLQ+AOF 증빙 | 감사 로그 |
| 77 | TODO | consumer graceful shutdown | 처리중 메시지 보존 | SIGTERM 핸들 | PEL 보존 |
| 78 | RISK | Windows solo pool 처리량 | 단일 스레드 한계 | 컨테이너 prefork | Linux worker |
| 79 | TODO | stream 모니터 대시보드 | 운영 가시성 | XLEN/XPENDING 수집 | 대시보드 |
| 80 | TODO | enqueue idempotency key | 중복 발행 방지 | dedup_key 활용 | 중복 발행 0 |
| 81 | IMPLEMENTED | bridge dedup_key 산출 | 결정적 키 | _content_hash | 재현성 |
| 82 | TODO | stream→Milvus 임베딩 경로 | 벡터 검색 적재 | 후속 라운드 | 범위 분리 |
| 83 | TODO | stream→OpenSearch 색인 | 검색 색인 | publish_pipeline | 색인 동작 |
| 84 | IMPLEMENTED | publish_pipeline 존재 | B 발행 경로 | workers/pipelines | 발행 |
| 85 | TODO | A/B 통합 e2e 테스트 | 배선 회귀 가드 | enqueue→consume→DB | e2e green |
| 86 | RISK | 통합 테스트 부재 P0 | 배선 깨짐 미감지 | e2e 추가 | 커버리지 |
| 87 | TODO | redis 연결 풀 설정 | 연결 고갈 방지 | pool size | 고갈 0 |
| 88 | TODO | redis 재연결 backoff | 일시 단절 복구 | retry on conn error | 자동 복구 |
| 89 | RISK | redis 단일 장애점 | 전체 중단 | sentinel/replica(후속) | HA 평가 |
| 90 | TODO | stream 소비 순서 보장 범위 | FIFO per stream | 단일 stream FIFO | 순서 검증 |
| 91 | COMMERCIAL | 실시간 처리 = 제품 가치 | 신선도 차별화 | sub-10ms 큐 | 지연 SLA |
| 92 | TODO | enqueue 배치 최적화 | 다건 발행 효율 | pipeline XADD | 배치 처리량 |
| 93 | TODO | dead consumer 자동 정리 | 좀비 consumer | XGROUP DELCONSUMER | 정리 동작 |
| 94 | RISK | PEL 무한증가 메모리 | OOM 위험 | reclaim+DLQ+ack | PEL 상한 |
| 95 | TODO | stream 메트릭→Prometheus | 표준 관측 | exporter | 메트릭 수집 |
| 96 | AGENT_HINT | orchestrator-architect db0/1/2 분리 | broker/cache/retry | plans/012 §1 | DB 격리 |
| 97 | TODO | enqueue 실패율 알람 | 발행 장애 감지 | failure rate | 임계 알람 |
| 98 | TODO | A 단일프로세스 모드 폴백 | Celery 없는 환경 | JSONL + local_file | 폴백 동작 |
| 99 | IMPLEMENTED | local_file rate_limit 영속 | 재기동 생존 | rate_limit_store.py | 생존 확인 |
| 100 | TODO | 완전배선 verdict 게이트 | P0 종료 조건 | A_to_B_wired flag | e2e PASS |

## L5. Storage and indexing: Postgres / OpenSearch / vector DB — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | Postgres holds raw_events as SoT | 원천 데이터 단일 진실원 | raw_events 유지 | INSERT 후 SELECT round-trip 일치 |
| 2 | IMPLEMENTED | Postgres holds event_cards normalized | 정규화 카드 기준 | event_cards 스키마 유지 | upsert_card 후 PG 조회 성공 |
| 3 | IMPLEMENTED | upsert_card commits to PG first | PG가 SoT | upsert_card→PG commit 순서 | PG commit 실패 시 인덱싱 미진행 |
| 4 | IMPLEMENTED | Milvus insert swallows errors | 인덱싱 실패가 파이프라인 무중단 | try/swallow | Milvus 다운 시 PG commit 유지 |
| 5 | IMPLEMENTED | OpenSearch index swallows errors | 키워드 인덱싱 장애 격리 | try/swallow | OS 다운 시 무중단 |
| 6 | IMPLEMENTED | Milvus event_embeddings dim=1536 | 임베딩 차원 고정 | dim=1536 | dim 불일치 insert 거부 |
| 7 | IMPLEMENTED | Milvus IVF_FLAT/COSINE | 의미 유사 메트릭 | IVF_FLAT, COSINE | 인덱스 메트릭 COSINE |
| 8 | IMPLEMENTED | OpenSearch standard analyzer | 키워드 토크나이즈 | standard analyzer | 영문 토큰 분리 |
| 9 | IMPLEMENTED | multi_match bool/must title^2 | 제목 가중 매칭 | title^2 부스트 | title 매칭 score 가산 |
| 10 | IMPLEMENTED | pymilvus pinned 2.4.4 | 클라이언트 안정 | requirements 핀 | pymilvus==2.4.4 |
| 11 | IMPLEMENTED | MockEmbeddingClient sha256 결정론 | 테스트 결정론 | sha256 벡터 | 동일 입력 동일 벡터 |
| 12 | IMPLEMENTED | EMBEDDING_PROVIDER env switch | Mock↔OpenAI 전환 | env로 선택 | env 변경 시 교체 |
| 13 | TODO | 인덱스 정합성 vs PG | swallow silent drift | 실패 재시도 큐 | 실패 카드 재인덱싱 정합 |
| 14 | TODO | Outbox pattern | PG 커밋과 인덱싱 원자성 | outbox 테이블+워커 | 미전파 카드 0건 수렴 |
| 15 | TODO | Dead-letter for failed indexing | 영구 실패 추적 | DLQ 테이블 | 실패 N회 후 DLQ |
| 16 | TODO | Reindex/backfill job | 인덱스 재구축 | 배치 reindex | 전체 재인덱싱 완료 |
| 17 | TODO | nori analyzer for Korean | 한국어 키워드 미지원 | OpenSearch nori | 한글 형태소 분리 |
| 18 | TODO | Synonym filter | 동의어 recall | synonym token filter | 동의어 쿼리 매칭 |
| 19 | RISK | swallow hides index failures | 장애 인지 불가 | swallow에 메트릭/로그 | 실패 카운터 노출 |
| 20 | TODO | Index lag metrics | 인덱싱 지연 가시화 | PG↔index 카운트 diff | lag 대시보드 |
| 21 | TODO | pgvector evaluation vs Milvus | 인프라 단순화 검토 | pgvector PoC 벤치 | 50M까지 latency 비교 |
| 22 | COMMERCIAL | pgvector 0.9 HNSW up to 50M | 별도 인프라 0 | PG vector 컬럼+HNSW | HNSW recall 측정 |
| 23 | COMMERCIAL | Qdrant ACORN filtered HNSW | 필터+벡터 | Qdrant 평가 | 필터 쿼리 recall |
| 24 | COMMERCIAL | Milvus 2.5 hybrid 30x>ES | 대규모 hybrid | Milvus 2.5 검토 | hybrid latency 벤치 |
| 25 | COMMERCIAL | LanceDB embedded/edge | 엣지 배포 | LanceDB 평가 | 임베디드 검색 |
| 26 | COMMERCIAL | Redis vector 10-15ms | 초저지연 | Redis 벡터 평가 | p99 10-15ms |
| 27 | TODO | Vector DB ADR | 선택 근거 문서화 | ADR 작성 | ADR 승인 |
| 28 | RISK | Dual write PG+Milvus+OS divergence | 3중 쓰기 정합성 | 단일 전파 경로 | 3엔진 카운트 일치 |
| 29 | TODO | Idempotent upsert by card id | 재처리 중복 방지 | card_id upsert | 중복 insert 시 1건 |
| 30 | TODO | Soft delete propagation | 삭제 카드 인덱스 잔존 | delete 전파 | 삭제 카드 검색 제외 |
| 31 | TODO | Embedding version field | 모델 교체 추적 | embedding_model 컬럼 | 버전별 재임베딩 |
| 32 | RISK | OpenAI embedding cost at scale | 대량 임베딩 비용 | 배치+캐시 | 비용 상한 모니터 |
| 33 | TODO | Embedding batch API | 처리량 향상 | batch embedding | 배치 처리량 측정 |
| 34 | TODO | Embedding cache by content hash | 중복 임베딩 절감 | content hash 캐시 | 동일 본문 재호출 0 |
| 35 | RISK | dim=1536 model lock-in | 모델 변경 마이그 | dim 추상화/버전 | dim 변경 마이그 경로 |
| 36 | TODO | Milvus partition by time | 시간 파티션 효율 | 시간 partition | 최근 파티션 우선 |
| 37 | TODO | TTL/retention on raw_events | 저장 비용 관리 | retention 정책 | 만료 raw 정리 |
| 38 | TODO | Evidence URL+summary only storage | 전문 저장 금지 준수 | URL+summary | 본문 전문 미저장 |
| 39 | RISK | Storing full article text | 저작권/비용 | 전문 저장 차단 | 카드 본문 길이 상한 |
| 40 | TODO | OpenSearch mapping for filters | 시간/소스 필터 | date/source 매핑 | range/term 필터 |
| 41 | TODO | PG indexes on query columns | 쿼리 성능 | published_at/source 인덱스 | EXPLAIN 인덱스 사용 |
| 42 | TODO | Connection pooling for PG | 동시성 안정 | pool 설정 | 커넥션 고갈 없음 |
| 43 | TODO | Milvus connection retry | 일시 장애 복원 | retry/backoff | 자동 복구 |
| 44 | TODO | OpenSearch bulk indexing | 처리량 향상 | _bulk API | 배치 처리량 |
| 45 | AGENT_HINT | Card schema is the chunk unit | 이벤트는 카드=청크 | 카드 단위 임베딩 | 카드별 1 임베딩 |
| 46 | AGENT_HINT | PG is authoritative for agents | 에이전트 PG 기준 | 읽기 SoT=PG | 불일치 시 PG 우선 |
| 47 | TODO | Schema migration tooling | 스키마 진화 안전 | alembic | 마이그 up/down 통과 |
| 48 | TODO | event_embeddings id↔card id link | 벡터↔카드 매핑 | card_id를 Milvus PK | 벡터로 카드 역참조 |
| 49 | TODO | OpenSearch refresh interval tune | 인덱싱 지연 vs 부하 | refresh_interval | 가시성 지연 목표 |
| 50 | RISK | IVF_FLAT recall vs HNSW | 검색 정확도 | nlist/nprobe 튜닝 | recall 목표 |
| 51 | TODO | nprobe tuning | recall/latency 균형 | nprobe 스윕 | recall-latency 곡선 |
| 52 | TODO | HNSW migration on Milvus | 정확도 향상 | HNSW 평가 | recall 개선 |
| 53 | TODO | Normalize vectors for COSINE | 코사인 정합 | insert 전 정규화 | norm=1 확인 |
| 54 | TODO | Backpressure on indexing queue | 폭주 보호 | 큐 길이 제한 | 과부하 시 throttle |
| 55 | TODO | Healthcheck for 3 engines | 가용성 가시화 | /health 3엔진 | 엔진별 상태 노출 |
| 56 | TODO | Startup schema bootstrap | 초기화 자동화 | 부팅 시 컬렉션 생성 | 신규 환경 자동 구성 |
| 57 | RISK | Index/PG schema skew | 필드 불일치 | 스키마 동기 검증 | skew 검출 알람 |
| 58 | TODO | Multi-tenant/source isolation | 소스별 격리 | source 파티션/필터 | 소스별 조회 격리 |
| 59 | AGENT_HINT | retrieve_past_context uses Milvus top-k | 그래프 노드 실호출 | top-k 노드 유지 | top-k 결과 반환 |
| 60 | TODO | Configurable top-k | 검색 폭 조정 | k 파라미터화 | k 변경 반영 |
| 61 | TODO | Filtered vector search by time | freshness 결합 | Milvus expr 필터 | 시간 범위 필터 |
| 62 | TODO | Source field in vector payload | 다양성 후처리 | payload에 source | 결과에 source 포함 |
| 63 | RISK | Mock vs OpenAI vector 혼용 오염 | provider 혼용 | provider별 컬렉션 분리 | 혼용 시 분리 보장 |
| 64 | TODO | Embedding dimension assert at boot | 설정 오류 조기 검출 | 부팅 시 dim 검증 | mismatch fail-fast |
| 65 | TODO | OpenSearch analyzer per-field | 필드별 분석 최적 | 제목/본문 분석기 | 필드별 매핑 |
| 66 | TODO | Stopword/lowercase normalization | 매칭 일관성 | analyzer 필터 | 대소문자/불용어 정규화 |
| 67 | COMMERCIAL | Cohere embeddings option | 임베딩 품질 비교 | Cohere embed 평가 | recall 비교 |
| 68 | COMMERCIAL | Voyage embeddings option | 도메인 임베딩 | Voyage embed 평가 | recall 비교 |
| 69 | TODO | Embedding eval set | 임베딩 품질 측정 | golden set | nDCG 베이스라인 |
| 70 | TODO | Storage cost dashboard | 비용 가시화 | PG/Milvus/OS 용량 | 용량 추세 |
| 71 | RISK | Unbounded index growth | 저장 폭증 | retention+파티션 | 용량 상한 |
| 72 | TODO | Snapshot/backup for PG | 복구 가능성 | PG 백업 | 복구 리허설 |
| 73 | TODO | Milvus collection backup | 인덱스 복구 | 백업/복구 | 복원 검증 |
| 74 | TODO | OpenSearch snapshot | 인덱스 복구 | snapshot repo | 복원 검증 |
| 75 | TODO | Re-embed on model upgrade | 모델 진화 대응 | 재임베딩 잡 | 재임베딩 완료 |
| 76 | AGENT_HINT | Deterministic Mock for CI | CI 무외부호출 | Mock provider | CI에서 OpenAI 미호출 |
| 77 | TODO | OpenSearch index alias | 무중단 reindex | alias 스위치 | reindex 중 무중단 |
| 78 | TODO | PG read replica for search | 읽기 부하 분산 | read replica | 읽기 라우팅 |
| 79 | RISK | Single-writer bottleneck | 쓰기 병목 | 비동기 인덱싱 워커 | 처리량 목표 |
| 80 | TODO | Card dedup before index | 동일 사건 중복 | dedup by url/hash | 중복 미인덱싱 |
| 81 | TODO | Canonical URL normalization | URL 중복 제거 | URL 정규화 | 변형 URL 동일 |
| 82 | TODO | Language field on cards | 다국어 라우팅 | lang 필드 | 언어별 분석기 |
| 83 | TODO | OpenSearch numeric/date fields | 필터/정렬 | date/numeric 매핑 | range/sort 동작 |
| 84 | TODO | Milvus scalar fields for filter | 필터 동반 검색 | scalar field | scalar 필터 검색 |
| 85 | RISK | COSINE without normalization drift | 유사도 왜곡 | 정규화 강제 | 정규화 단위 테스트 |
| 86 | TODO | Index write idempotency key | 중복 쓰기 방지 | card_id 멱등 | 재인덱싱 1건 |
| 87 | TODO | Observability tracing on writes | 쓰기 경로 추적 | LangSmith/trace | 쓰기 span 노출 |
| 88 | TODO | Config-driven engine toggles | 엔진 선택 유연 | settings on/off | 비활성 시 우회 |
| 89 | AGENT_HINT | Swallow=best-effort, not guaranteed | 에이전트 가정 명확화 | 문서/주석 명시 | best-effort 표기 |
| 90 | TODO | Schema contract tests | 다운스트림 호환 | 계약 테스트 | 스키마 변경 감지 |
| 91 | TODO | Bulk reembed throughput target | 재임베딩 SLA | 배치 처리량 | 목표 throughput |
| 92 | TODO | OpenSearch shard/replica sizing | 가용성/성능 | shard 계획 | 샤드 설계 검증 |
| 93 | TODO | Milvus segment/flush tuning | 검색 성능 | flush/segment 튜닝 | latency 개선 |
| 94 | RISK | Cross-engine ID mismatch | 역참조 실패 | 통일 card_id PK | 3엔진 동일 ID |
| 95 | TODO | Cold start index warmup | 첫 쿼리 지연 | 인덱스 warmup | p99 안정화 |
| 96 | TODO | Storage layer integration tests | 회귀 방지 | 3엔진 통합 테스트 | CI 통과 |
| 97 | TODO | Disaster recovery runbook | 장애 복구 절차 | DR 런북 | 리허설 완료 |
| 98 | TODO | Per-source retention policy | 소스별 보존 | source별 TTL | 정책 적용 |
| 99 | AGENT_HINT | Evidence-centric, no full text | 도메인 저장 원칙 | URL+summary만 | 전문 미저장 검증 |
| 100 | TODO | Consolidate to fewer engines roadmap | 운영 단순화 | pgvector 통합 로드맵 | 통합 결정 ADR |

**완전 달성 기준:** 3엔진이 단일 card_id PK로 일관 매핑, PG 커밋과 인덱스 전파가 outbox/DLQ로 정합성(미전파 0건, swallow 실패 메트릭 가시화), nori·dim/COSINE 정규화·retention·백업/복구·통합 테스트 CI 통과, pgvector vs Milvus 결정 ADR 확정, IMPLEMENTED 경로 회귀 없음.

## L6. RAG retrieval and reranking — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | Milvus top-k via retrieve_past_context | 의미 검색 실호출 | top-k 벡터 검색 노드 | top-k 후보 반환 |
| 2 | IMPLEMENTED | OpenSearch keyword retrieval | 키워드 후보 생성 | multi_match | 키워드 후보 반환 |
| 3 | IMPLEMENTED | multi_match title^2 boosting | 제목 관련도 가중 | title^2 | 제목 매칭 우선 |
| 4 | IMPLEMENTED | Deterministic Mock embeddings | 테스트 재현성 | Mock provider | 동일 쿼리 동일 결과 |
| 5 | TODO | Hybrid BM25+dense fusion | 단일 엔진 한계 보완 | RRF 융합 | 융합 nDCG 향상 |
| 6 | TODO | RRF fusion implementation | 점수 스케일 무관 병합 | RRF rank 결합 | RRF 순위 산출 |
| 7 | TODO | Cross-encoder reranker | query-aware 정밀 재정렬 | rerank 단계 | rerank 후 top-k 정확도↑ |
| 8 | TODO | Two-stage retrieve→rerank | recall→precision 분리 | top-1000→top-100 | p99 내 2단계 |
| 9 | COMMERCIAL | Cohere rerank v4 Pro | 고품질 reranker | Cohere rerank | rerank nDCG 측정 |
| 10 | COMMERCIAL | Voyage rerank-2.5 | instruction+긴 컨텍스트 | Voyage rerank | 긴 문맥 rerank 검증 |
| 11 | COMMERCIAL | FlashRank lightweight | 로컬 저비용 | FlashRank | 로컬 rerank latency |
| 12 | TODO | nori for Korean retrieval | 한국어 recall | nori 분석기 | 한글 recall↑ |
| 13 | RISK | Keyword-only misses paraphrase | recall 손실 | dense 병행 | 패러프레이즈 매칭 |
| 14 | RISK | Vector-only misses exact entities | 정확 매칭 손실 | BM25 병행 | 엔티티 정확 매칭 |
| 15 | TODO | Freshness time-decay scoring | 이벤트 최신성 | decay 가중 | 최신 이벤트 상위 |
| 16 | TODO | Source diversity (MMR) | 출처 편중 억제 | MMR 재정렬 | 동일 소스 중복↓ |
| 17 | TODO | Event cluster dedup in results | 동일 사건 중복 제거 | cluster dedup | 중복 사건 1건 |
| 18 | TODO | Query understanding/expansion | recall 향상 | 쿼리 확장 | 확장 쿼리 recall↑ |
| 19 | TODO | Hybrid weight tuning | BM25/dense 균형 | 가중치 스윕 | 최적 가중 도출 |
| 20 | TODO | Reranker top-N cutoff | 비용/정확 균형 | rerank N 설정 | N별 nDCG-cost 곡선 |
| 21 | TODO | Retrieval eval golden set | 품질 측정 기준 | golden set | nDCG/Recall@k 기준선 |
| 22 | TODO | Recall@k metric | recall 가시화 | Recall@k 계측 | 베이스라인 측정 |
| 23 | TODO | nDCG@k metric | 순위 품질 | nDCG 계측 | 베이스라인 측정 |
| 24 | TODO | MRR metric | 첫 정답 위치 | MRR 계측 | 베이스라인 측정 |
| 25 | TODO | Latency p99 budget | SLA 준수 | p99 측정/예산 | p99 예산 내 |
| 26 | TODO | Rerank caching by query | 반복 쿼리 절감 | rerank 캐시 | 캐시 적중률 |
| 27 | RISK | Reranker latency spike | p99 악화 | 비동기/배치 | p99 회귀 없음 |
| 28 | TODO | Fallback when reranker down | 가용성 | rerank 실패 시 fusion만 | 폴백 결과 반환 |
| 29 | TODO | Configurable retrieval pipeline | 실험 유연성 | 단계 toggle | 단계 on/off |
| 30 | TODO | Time-window filter in retrieval | freshness 결합 | 시간 필터 | 범위 외 제외 |
| 31 | TODO | Source filter in retrieval | 소스 선택 | source 필터 | 지정 소스만 |
| 32 | TODO | Language-aware retrieval | 다국어 정확도 | lang 라우팅 | 언어별 분석기 |
| 33 | AGENT_HINT | Evidence URL+summary as context | 전문 미사용 컨텍스트 | URL+summary 주입 | 컨텍스트에 전문 없음 |
| 34 | AGENT_HINT | Card=chunk for retrieval | 청크 단위 명확 | 카드 단위 검색 | 카드 단위 후보 |
| 35 | TODO | Page/card-level rerank | 세분 재정렬 효과 | card-level rerank | card 단위 점수 |
| 36 | TODO | Chunking strategy for long bodies | 긴 본문 처리 | summary 청크 | summary 단위 검색 |
| 37 | TODO | Query-time embedding provider parity | 색인/쿼리 동일 모델 | 동일 provider 강제 | mismatch 차단 |
| 38 | RISK | Index/query embedding mismatch | 검색 품질 저하 | 동일 모델 검증 | mismatch fail-fast |
| 39 | TODO | Hybrid result normalization | 점수 정규화 | min-max/RRF | 정규화 점수 |
| 40 | TODO | Tie-breaking by recency | 동점 처리 | recency tie-break | 최신 우선 |
| 41 | TODO | Boost authoritative sources | 신뢰도 반영 | source weight | 신뢰 소스 가산 |
| 42 | RISK | Source bias amplification | 편향 강화 | diversity 균형 | 편중 억제 검증 |
| 43 | TODO | Negative/duplicate filtering | 노이즈 제거 | dedup/filter | 중복 제거 |
| 44 | TODO | Snippet/highlight generation | 근거 가시화 | highlight 추출 | 근거 스니펫 반환 |
| 45 | TODO | Retrieval tracing (LangSmith) | 관측성 | 검색 span | 단계별 trace |
| 46 | TODO | A/B retrieval experiments | 개선 검증 | 실험 프레임 | 변형 비교 |
| 47 | TODO | Reranker model versioning | 재현/회귀 | 버전 기록 | 버전별 평가 |
| 48 | TODO | Top-1000 retrieve budget | recall 확보 | 1단계 폭 | top-1000 후보 |
| 49 | TODO | Top-100 rerank budget | precision 확보 | 2단계 정밀 | top-100 재정렬 |
| 50 | TODO | Hybrid for both KO/EN | 다국어 hybrid | nori+dense | 양 언어 recall↑ |
| 51 | AGENT_HINT | retrieve_past_context is live node | 실호출 경로 보존 | 노드 유지 | top-k 호출 동작 |
| 52 | TODO | Pluggable reranker interface | 벤더 교체 용이 | rerank 추상화 | 벤더 교체 무변경 |
| 53 | COMMERCIAL | pgvector hybrid feasibility | 통합 hybrid | PG BM25+vector | PG 단독 hybrid PoC |
| 54 | COMMERCIAL | Qdrant filtered HNSW retrieval | 필터+벡터 | Qdrant 평가 | 필터 검색 recall |
| 55 | COMMERCIAL | Milvus 2.5 native hybrid | 엔진 내 hybrid | Milvus hybrid API | hybrid latency |
| 56 | TODO | Retrieval timeout/circuit breaker | 장애 격리 | timeout 설정 | 타임아웃 폴백 |
| 57 | RISK | Cross-encoder cost at scale | 비용 폭증 | top-N 제한+캐시 | 비용 상한 |
| 58 | TODO | Batch rerank requests | 처리량 | 배치 rerank | 배치 throughput |
| 59 | TODO | Query log collection | 평가/개선 | 쿼리 로깅 | 로그 적재 |
| 60 | TODO | Hard-negative mining | 임베딩 개선 | hard negative | eval 개선 |
| 61 | TODO | Freshness vs relevance weight | 균형 튜닝 | 가중 조합 | 가중 곡선 |
| 62 | TODO | Decay half-life config | 도메인 맞춤 | half-life 파라미터 | 도메인별 decay |
| 63 | RISK | Stale results ranked high | 오래된 이벤트 노출 | decay 강제 | 최신성 보장 |
| 64 | TODO | Dedup by canonical URL | 중복 근거 | URL 정규화 dedup | 동일 URL 1건 |
| 65 | TODO | Multi-vector/late interaction eval | 정확도 옵션 | ColBERT류 평가 | nDCG 비교 |
| 66 | TODO | Retrieval cache layer | 지연 절감 | 결과 캐시 | 적중률 측정 |
| 67 | TODO | Cold/warm cache strategy | p99 안정 | warmup | p99 안정화 |
| 68 | AGENT_HINT | Use PG SoT to hydrate results | 정합 보장 | id로 PG hydrate | 결과 본문 PG 기준 |
| 69 | TODO | Result schema contract | 다운스트림 안정 | 결과 스키마 | 계약 테스트 |
| 70 | TODO | Guardrail: no investment advice | 도메인 원칙 | 출력 필터 | 조언 표현 차단 |
| 71 | RISK | Ranking implies recommendation | 원칙 위반 소지 | 정보 환원 톤 | 가치판단 미출력 |
| 72 | TODO | Explainable ranking signals | 신뢰성 | 점수 근거 노출 | 신호별 기여 표시 |
| 73 | TODO | Per-source recency normalization | 소스 빈도 차이 | source별 정규화 | 빈출 소스 보정 |
| 74 | TODO | Diversity@k metric | 다양성 측정 | diversity 계측 | 베이스라인 측정 |
| 75 | TODO | Reranker instruction prompt | instruction-following | rerank 지시문 | 지시 반영 검증 |
| 76 | COMMERCIAL | Voyage instruction reranking | 도메인 지시 | Voyage instruct | 지시 rerank 효과 |
| 77 | TODO | Hybrid candidate dedup pre-rerank | 중복 입력 제거 | rerank 전 dedup | 중복 후보 제거 |
| 78 | TODO | Score calibration | 임계 일관 | 점수 보정 | 임계 안정 |
| 79 | TODO | Threshold cutoff for low relevance | 노이즈 컷 | min score | 저관련 제외 |
| 80 | RISK | Over-pruning hides recall | 과도 컷 | 임계 튜닝 | recall 유지 |
| 81 | TODO | Multilingual rerank support | KO/EN rerank | 다국어 reranker | 양 언어 rerank |
| 82 | TODO | Retrieval integration tests | 회귀 방지 | end-to-end 테스트 | CI 통과 |
| 83 | TODO | Eval harness in CI | 품질 회귀 감지 | CI eval | 기준 미달 시 fail |
| 84 | TODO | Shadow rerank rollout | 안전 도입 | shadow 비교 | 품질 비교 후 승격 |
| 85 | AGENT_HINT | Two-stage default once built | 표준 파이프라인 | retrieve→rerank | 기본 파이프라인 |
| 86 | TODO | Configurable fusion weights | 튜닝 유연 | weight config | 가중 반영 |
| 87 | TODO | Reranker batch timeout | p99 보호 | batch+timeout | p99 내 |
| 88 | RISK | RRF flattens strong signals | 신호 손실 | weighted RRF 고려 | 강신호 보존 |
| 89 | TODO | Query intent classification | 라우팅 | intent 분류 | 의도별 파이프 |
| 90 | TODO | Entity-aware boosting | 고유명사 정확 | entity boost | 엔티티 가산 |
| 91 | TODO | Time-range intent parsing | 시간 의도 | 날짜 파싱 | 범위 필터 적용 |
| 92 | TODO | Result freshness display | 사용자 신뢰 | timestamp 표시 | 최신성 노출 |
| 93 | TODO | Source attribution in output | 근거 추적 | source 표기 | 출처 명시 |
| 94 | AGENT_HINT | Mock path for deterministic CI | CI 안정 | Mock 검색 경로 | CI 외부호출 0 |
| 95 | TODO | Pagination/cursor for results | UX | cursor 페이징 | 다음 페이지 일관 |
| 96 | TODO | Rerank only on ambiguous queries | 비용 절감 | 조건부 rerank | 명확 쿼리 스킵 |
| 97 | TODO | Feedback loop (clicks) to ranking | 지속 개선 | 클릭 신호 | 신호 반영 |
| 98 | TODO | Cross-engine candidate union | recall 확대 | PG/Milvus/OS union | 합집합 후보 |
| 99 | RISK | Latency from union+rerank | p99 악화 | 단계 예산 관리 | p99 예산 준수 |
| 100 | TODO | Roadmap: hybrid→rerank→nori | 도입 순서 명확 | 단계적 롤아웃 | 순서대로 출시 |

**완전 달성 기준:** hybrid(BM25+dense, RRF) baseline 동작, 2단계 retrieve(top-1000)→rerank(top-100) p99 내, 이벤트 신호(freshness/diversity/cluster-dedup) 반영, nori 한국어 recall, golden set nDCG/Recall@k/MRR/Diversity@k CI 통과, reranker 장애 fusion-only 폴백 + 투자조언 미출력, IMPLEMENTED 경로 회귀 없음.

## L7. KG-RAG / GraphRAG / entity-event graph — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | RISK | entity_linking.py가 mock 고정값 | 그래프 입력이 가짜라 추론 무의미 | 실 NER 교체 전 착수 금지 | mock 0건, 실 엔티티 추출 |
| 2 | RISK | sector_mapping 하드코딩 | 섹터 엣지 동일값 오염 | LLM/룰 분류로 교체 | 섹터 분포 입력 다양성 반영 |
| 3 | TODO | Entity 노드 스키마 정의 | 그래프 1차 식별 단위 | type+canonical_id | 스키마 문서+마이그 |
| 4 | TODO | Event 노드를 event_card 1:1 | RDB 투영 일관성 | event_card.id를 그래프 키 | 카드↔노드 1:1 검증 |
| 5 | TODO | Source 노드+신뢰등급 | evidence 가중 근거 | source_registry 등급 | 모든 Source에 trust_tier |
| 6 | TODO | Time 노드/버킷 | 시계열 multi-hop | occurred_at/observed_at | 시간 필터 질의 |
| 7 | TODO | Evidence 노드(raw_event 단편) | SUPPORTS/CONTRADICTS | raw_events FK 재사용 | evidence→event 링크 100% |
| 8 | TODO | MENTIONS 엣지(Event→Entity) | 기본 검색 경로 | entity_linking 출력 연결 | mock 제거 후 활성화 |
| 9 | RISK | RELATED_TO weight 미정 | 임의 가중치 신뢰 훼손 | 공출현/명시관계 분리 | weight 산출식 문서화 |
| 10 | TODO | REPORTED_BY 엣지 | 출처 다양성/편향 | bridge 활용 | 다중 소스 카드 탐지 |
| 11 | TODO | SUPPORTS/CONTRADICTS 엣지 | 상충 이벤트 탐지 | llm_judge 출력 연결 | 상충 케이스 질의 |
| 12 | TODO | OCCURRED_AT 엣지 | 시간 전파 분석 | 정규화 시각 | 시간 누락 카드 0 |
| 13 | RISK | PRECEDES/CAUSES 인과오류 | 상관을 인과로 오표기 | CAUSES 보류, PRECEDES만 | 인과 라벨 미출력 |
| 14 | RISK | entity resolution 최대 유지보수 부담 | 미관리 30-40% 중복 | resolution 파이프라인 | 중복률 지표 |
| 15 | RISK | 이름기반 매칭 동명이인 충돌 | 잘못된 병합=오추론 | context 임베딩 보조 | 충돌 테스트셋 통과 |
| 16 | TODO | canonical_id 정책 | resolution 일관성 | 외부 ID 우선 | ID 충돌 해소 규칙 |
| 17 | TODO | alias 테이블 | 다중표기 통합 | alias→canonical | alias 조회 동작 |
| 18 | COMMERCIAL | GraphRAG vector RAG 3-5x 운영비 | ROI 판단 수치 | 고가치 use case 한정 | 비용/질의 대시보드 |
| 19 | COMMERCIAL | 그래프 인덱싱 10-100x 비용 | 실시간성 충돌 | 배치 주기 분리 | 인덱싱 비용 측정 |
| 20 | RISK | <1000 엔티티면 vector RAG 동등 | 과잉설계 | 엔티티 수 임계 모니터 | 임계 전 미도입 |
| 21 | TODO | hybrid RAG P0 선행 | GraphRAG 기준선 | OpenSearch/LanceDB | hybrid 질의 정확도 |
| 22 | AGENT_HINT | 단순 질의는 vector RAG 라우팅 | 불필요 그래프 비용 | 질의 분류기 | multi-hop만 그래프 |
| 23 | TODO | multi-hop 질의 로그 수집 | 실수요 검증 | 실패 질의 라벨링 | 그래프 필요 질의 통계 |
| 24 | RISK | GraphRAG 선투입 미검증 수요 | 인프라 매몰비용 | 수요 실측 후 | 도입 전 수요 근거 |
| 25 | TODO | LlamaIndex PropertyGraphIndex 프로토타입 | 저비용 실험 | kg_extractors | 프로토 그래프 생성 |
| 26 | TODO | Neo4j vs Memgraph 평가 | 운영 vs 스트리밍 | 동시성/실시간 비교 | 평가 매트릭스 |
| 27 | COMMERCIAL | Neo4j 성숙도/운영도구 | 운영 리스크 감소 | 규모 확대 승격 후보 | PoC 벤치 |
| 28 | COMMERCIAL | Memgraph 인메모리/스트리밍 | 실시간 적합 | 스트리밍 부하 테스트 | 지연 측정 |
| 29 | TODO | LanceDB 벡터 레이어 평가 | 임베딩+메타 통합 | OpenSearch 비교 | 비용/성능 비교 |
| 30 | RISK | MS GraphRAG community summary 실시간 충돌 | 인덱싱 주기 불일치 | 코퍼스 요약 한정 | 배치 질의 분리 |
| 31 | TODO | 그래프=RDB 투영 | SoT 단일화 | RDB 원본, 그래프 파생 | 재생성 스크립트 |
| 32 | RISK | 그래프 원본 삼으면 정합성 붕괴 | 이중 진실 소스 | 단방향 동기 | 동기 일관성 테스트 |
| 33 | TODO | 그래프 재구축 파이프라인 | 멱등 재생성 | RDB 스냅샷→빌드 | 재실행 동일 |
| 34 | TODO | 증분 업데이트 전략 | 전체 재빌드 비용 회피 | event_card 델타 | 증분 후 정합성 |
| 35 | RISK | relation extraction 정밀도 미측정 | 오추론 전파 | 골든셋 평가 | precision/recall 기준선 |
| 36 | TODO | relation extraction 골든셋 | 추출 품질 측정 | 수작업 라벨 | 골든셋 N건 |
| 37 | AGENT_HINT | LLM 추출 환각 관계 | 없는 관계 날조 | 근거 인용 필수 | 무근거 관계 거부 |
| 38 | RISK | 모호 노드 누적 | 그래프 품질 저하 | 정기 노드 audit | 모호 노드 비율 추적 |
| 39 | TODO | 노드 품질 audit 잡 | 중복/고아 탐지 | 주기적 점검 | audit 리포트 |
| 40 | TODO | 고아 노드 정리 정책 | 무의미 노드 제거 | evidence 없는 노드 격리 | 고아 노드 0 목표 |
| 41 | COMMERCIAL | multi-hop 인사이트=차별화 | 경쟁 우위 | 공급망 전파 시나리오 | 차별 질의 데모 |
| 42 | COMMERCIAL | 상충 evidence 탐지=신뢰 | 정보 신뢰성 | SUPPORTS/CONTRADICTS | 상충 카드 UI |
| 43 | RISK | 투자조언 경계 | 인과 추론 권유 오해 | 정보 환원 톤 | 추천 표현 미출력 |
| 44 | AGENT_HINT | 인과 그래프는 정보 전달용만 | 매수/매도 함의 금지 | 가치판단 제거 | 중립 표현 검증 |
| 45 | TODO | 엔티티 임베딩 저장 | resolution/검색 보조 | 노드별 벡터 | 임베딩 조회 |
| 46 | TODO | 그래프 질의 API 경계 | backend 통합 | search_service 확장 | 그래프 질의 엔드포인트 |
| 47 | RISK | 그래프 질의 지연시간 | UX 저하 | 홉 수 제한/캐싱 | p95 지연 기준 |
| 48 | TODO | 홉 수 상한 정책 | 폭발적 탐색 방지 | 기본 2-3홉 | 상한 초과 차단 |
| 49 | TODO | 그래프 질의 캐싱 | 반복 비용 절감 | 결과 캐시 | 캐시 적중률 |
| 50 | AGENT_HINT | 질의 분류기로 그래프 진입 통제 | 비용 게이트 | multi-hop 판별 | 오분류율 측정 |
| 51 | TODO | Time 버킷 해상도 | 시계열 정밀도 | 시/일/주 다단계 | 버킷 질의 동작 |
| 52 | TODO | 이벤트 전파 경로 질의 | 핵심 multi-hop | 충격→섹터 경로 | 전파 질의 결과 |
| 53 | RISK | 전파 추론 과대해석 | 약한 연결 인과화 | weight 임계 필터 | 저신뢰 경로 배제 |
| 54 | TODO | weight 임계 필터 | 노이즈 경로 제거 | 최소 weight 컷오프 | 컷오프 적용 |
| 55 | COMMERCIAL | 그래프 시각화=프리미엄 | 상위 티어 차별 | 관계 그래프 UI | 시각화 데모 |
| 56 | TODO | 그래프 시각화 데이터 API | 프론트 통합 | 노드/엣지 직렬화 | viz 페이로드 검증 |
| 57 | RISK | PII 엔티티 처리 | 개인정보/명예훼손 | 인물 노드 정책 검토 | PII 정책 문서 |
| 58 | RISK | 명예훼손(CAUSES 라벨) | 인물 인과 법적위험 | 인물 인과 엣지 보류 | 인물 CAUSES 미생성 |
| 59 | TODO | 엔티티 출처 추적 | provenance | 모든 엔티티에 evidence | 무출처 엔티티 0 |
| 60 | TODO | evidence 인용구 저장 | 신뢰성 근거 | raw_event 단편 | 인용 표시 동작 |
| 61 | AGENT_HINT | 상충 시 양측 evidence 노출 | 편향 방지 | CONTRADICTS 함께 표시 | 양면 노출 검증 |
| 62 | RISK | 소스 편향 그래프 증폭 | 단일 출처 편향 강화 | 소스 다양성 가중 | 편향 지표 추적 |
| 63 | TODO | 소스 다양성 점수 | 편향 완화 | REPORTED_BY 분산 | 다양성 점수 산출 |
| 64 | TODO | 그래프 스키마 버전관리 | 진화 추적 | 마이그 버전 태그 | 버전 이력 |
| 65 | RISK | 스키마 변경 재인덱싱 비용 | 운영 중단 | 무중단 마이그 | 재인덱싱 절차 문서 |
| 66 | TODO | 그래프-벡터 동기화 | hybrid 일관성 | 임베딩↔노드 동기 | 동기 누락 0 |
| 67 | RISK | 동기 누락 검색 불일치 | 결과 신뢰 저하 | 동기 모니터링 | 불일치 알림 |
| 68 | TODO | 그래프 빌드 Celery 잡 | 비동기 인덱싱 | Celery 태스크 | 빌드 잡 동작(미구현) |
| 69 | AGENT_HINT | 인덱싱은 수집과 분리 큐 | 부하 격리 | 별도 Celery 큐 | 큐 분리 확인 |
| 70 | TODO | 그래프 빌드 실패 재시도 | 내구성 | 멱등 재시도 | 재시도 후 정합 |
| 71 | RISK | 대량 엔티티 그래프 폭발 | 질의 성능 붕괴 | 노드 수 모니터+파티션 | 노드 증가 추적 |
| 72 | TODO | 그래프 파티셔닝 | 확장성 | 시간/도메인 파티션 | 파티션 질의 |
| 73 | COMMERCIAL | 그래프 단계적 비용 정당화 | 투자 의사결정 | use case별 ROI | ROI 보고서 |
| 74 | TODO | use case별 가치 측정 | 우선순위 근거 | 질의별 가치 라벨 | 가치 랭킹 |
| 75 | RISK | 그래프 없이도 80% 질의 해결 | 도입 명분 약화 | vector RAG 커버리지 측정 | 커버리지 수치 |
| 76 | AGENT_HINT | vector RAG 실패 질의만 그래프행 | 비용 최적화 | fallback 라우팅 | fallback 동작 |
| 77 | TODO | 그래프 질의 DSL/추상화 | 백엔드 결합도 감소 | Cypher 추상 래퍼 | DSL 질의 동작 |
| 78 | RISK | DB 종속(Cypher) 락인 | 마이그 비용 | 추상 레이어 격리 | DB 교체 가능성 |
| 79 | TODO | 엔티티 타입 온톨로지 | 분류 일관성 | 도메인 타입 정의 | 온톨로지 문서 |
| 80 | RISK | 온톨로지 과설계 | 유지보수 부담 | 최소 타입 시작 | 타입 수 제한 |
| 81 | TODO | 관계 타입 화이트리스트 | 추출 노이즈 제한 | 허용 관계만 저장 | 미허용 관계 거부 |
| 82 | AGENT_HINT | 관계 추출 화이트리스트 제약 | 환각 관계 차단 | 사전 정의 관계만 | 임의 관계 미생성 |
| 83 | TODO | 그래프 평가 메트릭 | 품질 측정 | 노드/엣지 정밀도 | 메트릭 대시보드 |
| 84 | TODO | 그래프 답변 faithfulness | 환각 답변 방지 | 근거 노드 추적 | faithfulness 측정 |
| 85 | RISK | 그래프 답변 환각 | 신뢰성 위협 | 근거 노드 필수 인용 | 무근거 답변 거부 |
| 86 | AGENT_HINT | 답변은 그래프 경로 근거 첨부 | 추적성 | 경로→인용 변환 | 경로 표시 동작 |
| 87 | TODO | 그래프 PoC 범위 한정 | 실험 비용 통제 | 단일 도메인 슬라이스 | PoC 범위 문서 |
| 88 | TODO | PoC 성공 기준 사전 정의 | 도입 판단 객관화 | multi-hop 정확도 목표 | 기준 충족 판정 |
| 89 | RISK | PoC 없이 전면 도입 | 실패 비용 극대화 | PoC 게이트 필수 | PoC 통과 후 확장 |
| 90 | COMMERCIAL | 단계적 도입=리스크 분산 | 자본 효율 | 레이어 점진 추가 | 단계별 게이트 |
| 91 | TODO | 엔티티 disambiguation UI | 운영자 교정 | 모호 노드 수동 병합 | 병합 UI 동작 |
| 92 | AGENT_HINT | 자동 resolution+인간 검수 | 정확도/효율 균형 | 저신뢰만 human-in-loop | 검수 큐 동작 |
| 93 | RISK | 완전 자동 resolution 과신 | 오병합 누적 | 신뢰도 임계 검수 | 임계 미달 검수행 |
| 94 | TODO | resolution 신뢰도 스코어 | 검수 라우팅 | 매칭 확신도 | 스코어 분포 추적 |
| 95 | TODO | 그래프 백업/복구 절차 | 운영 내구성 | RDB 재생성 가능성 | 복구 절차 검증 |
| 96 | RISK | 그래프 단독 장애 서비스 영향 | 가용성 | vector RAG fallback | 그래프 다운 시 동작 |
| 97 | AGENT_HINT | 그래프 장애 시 vector로 graceful degrade | 가용성 보장 | 자동 fallback | degrade 동작 |
| 98 | TODO | 그래프 비용 모니터링 대시보드 | ROI 추적 | 질의/인덱싱 비용 | 대시보드 운영 |
| 99 | RISK | 비용 추적 없이 운영 | 예산 초과 | 비용 알림 임계 | 비용 알림 동작 |
| 100 | TODO | mock 의존 제거 후 그래프 착수 게이트 | 가짜 입력 그래프 방지 | entity/sector mock 제거 선행 | mock 0 확인 후 진입 |

**완전 달성 기준:** entity_linking/sector_mapping mock 전부 실 NER·실 분류 대체(1·2·100), vector+메타 hybrid RAG P0 안정화 + 질의 커버리지 실측(21·75), vector RAG로 못 푸는 multi-hop 고가치 use case 한정(23·24·74), RDB 투영(31·32) PoC 게이트(87-89) 통과 단계 도입, 답변 근거 노드/경로 인용(84·86), human-in-loop entity resolution(92·94), ROI 대시보드(18·98).

## L8. Event clustering / dedup / ranking / timeline — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | content_hash UNIQUE ON CONFLICT DO NOTHING | 바이트 동일 재수집 차단 | 유지, 변경 금지 | 동일 payload 재삽입 row 미증가 |
| 2 | PARTIAL | deduplicate.py가 dedupe_key만 부여 | 의미 dedup 부재 | STEP-010 벡터 dedup | near-dup 그룹 동일 키 |
| 3 | TODO | vector-based dedup(cosine>τ skip) | 다른 바이트 누수 | 유사도 비교 노드 | cosine≥τ skip 카운트 |
| 4 | TODO | MinHash LSH near-dup 후보 | O(N²) 회피 | 제목+요약 shingle, LSH band | 후보쌍 recall≥0.95 |
| 5 | TODO | cross-source event clustering | 같은 사건 멤버 묶기 | 임베딩+HDBSCAN, source 보존 | homogeneity≥0.8 |
| 6 | TODO | article-level vs event-level 분리 | dedup이 corroboration 지움 | 2레이어 분리, cluster 대표 | event_cards가 cluster 단위 1행 |
| 7 | TODO | cluster→timeline 정렬 | 사건 전개 추적 | published_at 정렬 | 타임라인 시간 단조 |
| 8 | TODO | First Story Detection(origin) | 첫 보도 식별 | 클러스터 최초 멤버 flag | origin precision≥0.9 |
| 9 | TODO | RevDet 반복 클러스터링 | 신규 멤버 증분 병합 | 슬라이딩 재클러스터 | 신규 멤버 흡수 |
| 10 | TODO | Headline Grouping | 같은 사건 헤드라인 묶기 | 제목 임베딩 보조 | V-measure≥0.8 |
| 11 | TODO | freshness 신호 | 오래된 사건 상위 방지 | 시간 감쇠 | 최신 멤버 가중 단조 |
| 12 | TODO | corroboration count 신호 | 신뢰도 정량화 | 독립 outlet 수 집계 | 같은 outlet 중복 제외 |
| 13 | TODO | source diversity 신호 | 단일소스 편향 | 카테고리 엔트로피 | 동일카테고리 N개=1 효과 |
| 14 | TODO | impact 신호 | 중요도 반영 | significance/sectors 결합 | impact가 ranking 반영 |
| 15 | TODO | 클러스터 랭킹 통합 점수 | 신호 결합 | 가중합, 가중치 설정화 | top-K 안정성 회귀 통과 |
| 16 | RISK | cosine 임계 하드코딩 | 도메인별 부적합 | 설정값/시간창 적응 | 상수 0개, config 노출 |
| 17 | RISK | corroboration 동일통신사 재게재 부풀림 | 가짜 신뢰도 | outlet 정규화 dedup | 재게재 시 count 미증가 |
| 18 | RISK | duplicate leakage | 피드 near-dup 범람 | leakage rate 측정 | leakage<10% |
| 19 | RISK | HDBSCAN noise=단발사건 손실 | 신규사건 누락 | noise를 singleton 화 | noise 멤버도 카드 발행 |
| 20 | RISK | cluster drift(주제 혼합) | 다른 사건 병합 | homogeneity 모니터 | impurity 경보 임계 |
| 21 | IMPLEMENTED | community_corroboration_gate publish 등급 | 익명신호 직행 차단 | 유지, cluster 전단 적용 | 금융갤=internal_queue_only |
| 22 | IMPLEMENTED | requires_external_confirmation=True | 익명 corroboration 강제 | 클러스터 corroboration 연계 | 익명 단독 cluster publish 차단 |
| 23 | RISK | §1 info-not-advice in impact | 가치판단 노출 | impact 톤 정보환원 | 매수/매도 표현 0 |
| 24 | TODO | event_cards 대표 선정 | 어떤 멤버를 카드로 | centroid 최근접+신뢰소스 | 대표 1개 결정 규칙 |
| 25 | TODO | cluster_id 영속화 | 재기동 후 유실 | event_cards에 cluster_id | cluster_id FK 유지 |
| 26 | TODO | 시간창(window) 정의 | 무한 누적 클러스터링 | 48h 슬라이딩 | 윈도우 밖 멤버 제외 |
| 27 | AGENT_HINT | dedup 노드는 cluster 전단 | 순서 의존 | dedup→cluster→rank | 노드 순서 고정 |
| 28 | AGENT_HINT | 임베딩 모델 = retrieved_context 동일 | 공간 불일치 방지 | 동일 embedder | 같은 임베딩 차원 |
| 29 | TODO | 라벨링 평가셋 구축 | 임계 보정 근거 | 수동 라벨 N건 | gold set 존재 |
| 30 | TODO | cluster purity/homogeneity 측정 | quality 정량화 | V-measure | purity≥0.8 리포트 |
| 31 | TODO | FSD latency 측정 | 탐지 지연 | 첫보도→탐지 시간 | latency 분포 기록 |
| 32 | COMMERCIAL | corroboration=B2B 신뢰 셀링 | event quality 차별 | "N개 소스 교차확인" | 카드에 corrob 배지 |
| 33 | COMMERCIAL | timeline=사건 전개 제품가치 | coverage>quality 전환 | 타임라인 뷰 | 타임라인 API 응답 |
| 34 | COMMERCIAL | FSD=속보 우위 | 첫 탐지 마케팅 | origin flag | origin 표시 UI |
| 35 | TODO | dedupe_key 안정성 | 재실행 키 변동 | 결정적 해시 | 동일입력 동일키 |
| 36 | RISK | 임베딩 비용/지연 | 대량 O(N²) | LSH 사전필터 필수 | 비교쌍 수 상한 |
| 37 | TODO | multilingual 클러스터링 | KR/EN 혼합 사건 | 다국어 임베딩 | 교차언어 병합 |
| 38 | RISK | published_at 결측/부정확 | 타임라인 깨짐 | observed_at fallback | 결측 시 정렬 안정 |
| 39 | TODO | numeric_signal은 cluster 제외 | body 없음 정상 | signal_ready 별도 경로 | 신호는 cluster 우회 |
| 40 | AGENT_HINT | EventCandidate→cluster 승격 | seed≠cluster | 다운스트림 승격 단계 | 승격 시 cluster 할당 |
| 41 | TODO | HDBSCAN min_cluster_size 튜닝 | 과/소 분할 | 2부터 grid search | 분할수 안정 |
| 42 | TODO | cosine 후보 임계 τ 튜닝 | recall/precision | ROC로 τ 선택 | τ 문서화 |
| 43 | RISK | cluster 폭주(거대 cluster) | 무관 사건 흡수 | max size 상한+재분할 | 단일 cluster 비율 상한 |
| 44 | TODO | incremental vs batch 클러스터링 | 실시간성 | RevDet 증분 모드 | 신규 item p95 지연 |
| 45 | IMPLEMENTED | FinalEventCard.confidence_score | 신뢰도 필드 존재 | corroboration으로 채움 | corrob→confidence 매핑 |
| 46 | IMPLEMENTED | FinalEventCard.impact_path | impact 필드 존재 | impact 신호 연결 | 비어있지 않게 채움 |
| 47 | TODO | theme/sectors 클러스터 일관성 | 멤버 간 불일치 | 멤버 다수결/centroid | cluster theme 단일 |
| 48 | TODO | 랭킹 가중치 학습 여지 | 정적 가중 한계 | 클릭/피드백 신호 후행 | 가중치 config 분리 |
| 49 | RISK | 동일사건 시간차 재등장 | 중복 cluster 생성 | RevDet 기존 cluster 매칭 | 재등장 흡수율 |
| 50 | TODO | noise/singleton 처리 정책 | 신규사건 vs 잡음 | FSD로 신규 승격 | singleton도 평가 |
| 51 | AGENT_HINT | EvidenceGate 통과분만 cluster | 품질 미달 차단 | gate 후단 clustering | gate fail 미진입 |
| 52 | TODO | cluster 멤버 evidence 집계 | 근거 링크 | 멤버 source_url 수집 | cluster에 evidence list |
| 53 | COMMERCIAL | source diversity=편향완화 셀링 | 신뢰 메시징 | diversity 점수 노출 | diversity 배지 |
| 54 | RISK | 펌핑신호 cluster 진입 | §1 위반 | corroboration_gate 선적용 | solicitation cluster 차단 |
| 55 | TODO | 클러스터 요약(timeline summary) | 긴 타임라인 가독성 | 추출/추상 요약 | 요약 충실도 평가 |
| 56 | TODO | duplicate_rate 모니터 지표 | 품질 회귀 감지 | 파이프라인 메트릭 | rate<10% 알림 |
| 57 | RISK | 임베딩 모델 변경 cluster 불연속 | 버전 드리프트 | embedder 버전 고정 | 버전 메타 기록 |
| 58 | TODO | cross-source URL 정규화 | 같은기사 다른URL | canonical_url 활용 | URL 정규화 후 dedup |
| 59 | AGENT_HINT | dedupe_key를 cluster 입력 키로 | 키 재사용 | near-dup 그룹=1 멤버 | 그룹 내 단일 대표 |
| 60 | TODO | cluster 생애주기(TTL) | 무한 활성 cluster | 윈도우 만료 archive | 만료 cluster 비활성 |
| 61 | RISK | 소규모 corpus HDBSCAN 불안정 | 초기 데이터 부족 | min_cluster_size 보수적 | 저volume 폴백 |
| 62 | TODO | 평가 자동화 핸드오프 | 수동 검증 한계 | test-validation-agent | schema+purity 자동검증 |
| 63 | COMMERCIAL | event quality>coverage 포지셔닝 | 차별화 축 | quality 지표 대시보드 | quality KPI 노출 |
| 64 | TODO | ranking explainability | 왜 상위인가 불투명 | 신호별 기여 기록 | 점수 분해 가능 |
| 65 | RISK | freshness 과중→중요사건 침몰 | 중요도 손실 | freshness/impact 균형 | 가중 민감도 테스트 |
| 66 | TODO | corroboration 독립성 판정 | 재게재=비독립 | outlet ownership 매핑 | 동일소유 비독립 처리 |
| 67 | AGENT_HINT | cluster_id를 event_state에 추가 | 상태 전파 | EventState 확장 | state에 cluster_id |
| 68 | TODO | 다중 언어 corroboration | KR+EN 교차확인 | 다국어 cluster 멤버 | 교차언어 corrob 인정 |
| 69 | RISK | 클러스터링 비결정성 | 재현 불가 | seed 고정 | 동일입력 동일cluster |
| 70 | TODO | cluster centroid 갱신 | 멤버 추가 표류 | centroid 재계산 | centroid 안정 |
| 71 | COMMERCIAL | 타임라인=리텐션 기능 | 재방문 유도 | 사건 추적 알림 | 타임라인 업데이트 푸시 |
| 72 | TODO | 랭킹 top-K 회귀 테스트 | 무음 회귀 | 골든 top-K 고정 | 회귀 시 실패 |
| 73 | RISK | content_hash만 믿고 cluster 생략 | exact만 막힘 | cluster 필수화 | near-dup도 묶임 |
| 74 | TODO | cluster 멤버 수 상한/하한 | 품질 경계 | size 정책 | 비정상 size 경보 |
| 75 | AGENT_HINT | numeric_signal body_length 면제 | 기준 오적용 방지 | signal_ready 분기 | 신호 cluster 미적용 |
| 76 | TODO | impact 신호 출처 명확화 | significance 신뢰 | significance 소스 검증 | impact 근거 추적 |
| 77 | RISK | 대표카드 편향(특정소스 선호) | 공정성 | 대표 선정 규칙 명시 | 선정 규칙 감사 |
| 78 | TODO | cluster 간 병합/분할 이벤트 | 사건 합쳐짐/갈라짐 | merge/split 핸들 | merge 후 단일 cluster |
| 79 | COMMERCIAL | corroboration precision=품질 SLA | B2B 신뢰 약속 | precision 측정 공개 | precision≥목표 |
| 80 | TODO | 시간窓 외 늦은 보도 처리 | 윈도우 경계 사건 | grace period | 경계 멤버 흡수 |
| 81 | RISK | LSH band 파라미터 오설정 | recall/precision 붕괴 | band/row 튜닝 | 후보 recall 검증 |
| 82 | TODO | 임베딩 캐시 | 재계산 비용 | content_hash 키 캐시 | 캐시 적중률 |
| 83 | AGENT_HINT | dedup→cluster 사이 EvidenceGate | 품질 미달 차단 | gate 위치 명시 | gate fail 미진입 |
| 84 | TODO | cluster quality 리포트 자동화 | 수동 판정 한계 | 정기 메트릭 잡 | 리포트 주기 생성 |
| 85 | RISK | 멤버 published_at 타임존 혼재 | 타임라인 왜곡 | UTC 정규화 | 단일 타임존 |
| 86 | TODO | 신규소스 추가 cluster 영향 | 분포 변화 | 임계 재보정 트리거 | 신규소스 회귀 |
| 87 | COMMERCIAL | event quality KPI 영업자료 | 구매 근거 | purity/corrob 공개 | KPI 시트 |
| 88 | TODO | ranking 페이지네이션 안정성 | 순서 흔들림 | tie-break 결정적 | 동점 안정정렬 |
| 89 | RISK | cluster 폭주 시 메모리 | 대량 멤버 | 멤버 상한+샘플링 | 메모리 상한 |
| 90 | TODO | first-seen vs published 구분 | 탐지/발행 시점 혼동 | 두 시점 분리 저장 | 두 필드 존재 |
| 91 | AGENT_HINT | corroboration_gate publish_level 존중 | 발행 등급 우회 금지 | level별 cluster 처리 | internal_queue 미발행 |
| 92 | TODO | cluster→event_cards 멱등 발행 | 중복 카드 | upsert by cluster_id | 재실행 중복 0 |
| 93 | RISK | 가중치 튜닝 과적합 | 특정구간 편향 | holdout 검증 | holdout 성능 유지 |
| 94 | TODO | 다운스트림 confidence_score 매핑 | 신뢰도 일관성 | corrob+diversity→confidence | 매핑 공식 문서화 |
| 95 | COMMERCIAL | timeline summary 프리미엄 | 수익화 후보 | 요약 tier 구분 | tier 게이팅 |
| 96 | TODO | cluster 품질 임계 게이트 | 저품질 발행 | min purity gate | 미달 cluster 보류 |
| 97 | RISK | 무라벨 운영 중 임계 표류 | silent 품질저하 | 주기적 라벨 샘플 | drift 모니터 |
| 98 | AGENT_HINT | EventState에 cluster 신호 필드 | 노드 간 전달 | TypedDict 확장 | 필드 정의 존재 |
| 99 | TODO | 랭킹/클러스터 옵저버빌리티 | 디버깅 | LangSmith trace | 단계별 trace |
| 100 | TODO | 전체 파이프라인 E2E 평가 | 부분 검증 한계 | dedup→rank E2E | E2E gold 통과 |

**완전 달성 기준:** content_hash exact dedup + MinHash LSH near-dup + 임베딩 HDBSCAN cross-source 클러스터링이 article/event level 분리 동작, 각 cluster가 4신호로 결정적·설명가능 랭킹, cluster→timeline(FSD origin) 단조 정렬, gold set purity≥0.8·leakage<10%·schema validation E2E 통과, community_corroboration_gate publish_level과 §1 톤 위반 0.

## L9. LLM SourceSupervisor / judge / analyst agents — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | judge BaseJudgeClient.complete/complete_json | 가치지점 LLM 표준 | llm_judge.py 유지 | 파싱실패시 None |
| 2 | IMPLEMENTED | mock↔openai 토글 LLM_PROVIDER | 키 없이 결정적 동작 | create_judge_client env 분기 | 키 len=0이면 Mock fallback |
| 3 | IMPLEMENTED | supervisor deterministic decide() | LLM 미설정시 규칙동작 | source_supervisor.decide | llm_available=False시 allowed[0] |
| 4 | IMPLEMENTED | unsafe 전략 영구차단 frozenset | 우회 금지 | _UNSAFE_STRATEGIES | proxy_rotation 제안도 rejected |
| 5 | IMPLEMENTED | allowed 밖 LLM 제안 무시 | 비결정 우회 차단 | decide() proposed in allowed | 밖 제안시 fallback |
| 6 | IMPLEMENTED | blocking layer→allowed map | 실패유형별 안전후보 | _ALLOWED_BY_LAYER | 8개 layer 매핑 |
| 7 | IMPLEMENTED | root_cause 후보 추출 | 실패 진단 입력 | _root_causes | 429→provider_rate_limit |
| 8 | IMPLEMENTED | SourceSupervisorDecision frozen | 감사 가능 결정 | frozen=True | confidence high/medium/low |
| 9 | IMPLEMENTED | downstream judge fact_check | hold/pass 판정 | fact_check_claims | None시 status=pass |
| 10 | IMPLEMENTED | impact_analysis LLM 노드 | 영향 분석 | analyze_impact | None시 fallback horizon=medium |
| 11 | IMPLEMENTED | final_card_writer LLM 노드 | 최종 카드 생성 | write_final_card | None시 fallback summary |
| 12 | IMPLEMENTED | event_candidate 추출 judge | 구조화 이벤트 | graph 노드 | EventCandidate schema 검증 |
| 13 | IMPLEMENTED | llm_quality_judge 노드 | 추출 품질 판정 | _node_llm_quality_judge | is_valid/confidence/reason |
| 14 | IMPLEMENTED | investment advice 금지 프롬프트 | 정책 | "Do NOT include investment advice" | 출력에 매수/매도 없음 |
| 15 | TODO | supervisor 실 LLM provider 루프 | 학습 가속 | llm_propose 실연결 | 옵션 켜도 allowed 게이트 통과 |
| 16 | TODO | supervisor↔judge 역할 경계 문서화 | 책임 혼선 방지 | 모듈 docstring | 한쪽이 다른쪽 import 안함 |
| 17 | TODO | audit_trace에 LLM 결정 기록 | 규제·감사 | audit_trace.py | 모든 decide() trace |
| 18 | TODO | judge confidence 임계 게이트 | 저신뢰 hold | confidence<0.5시 HOLD | publish_or_hold 연동 |
| 19 | TODO | LLM 비용 카운터 | 비용 통제 | provider별 토큰 | run당 토큰/비용 리포트 |
| 20 | TODO | LangSmith trace 연결 | 관측 | LANGSMITH env | judge 호출 trace |
| 21 | RISK | OpenAI RateLimitError 폭주 | 비용·지연 | tenacity stop_after_attempt(2) | 2회후 reraise |
| 22 | RISK | mock judge가 실데이터로 오인 | 품질 착시 | mock 응답에 [mock] 마커 | 마커로 mock 식별 |
| 23 | RISK | judge None 누적시 빈 카드 | 빈 출력 | fallback 기본값 보장 | None→fallback 100% |
| 24 | RISK | LLM 우회 전략 제안 | 정책 위반 | allowed 게이트+unsafe 차단 | 우회 제안 0건 채택 |
| 25 | RISK | supervisor 무한 재시도 | 자원 소진 | max_strategies_per_url 예산 | 예산 초과시 None |
| 26 | AGENT_HINT | never_disable_on_single_429 | 단발 429로 소스 안 죽임 | llm_agent_hints 저장 | gdelt 단발 429시 cooldown만 |
| 27 | AGENT_HINT | google_trends=CONFIRMED_EXTERNAL_RATE_LIMIT | PASS 금지 | terminal status | judge가 PASS 표기 안함 |
| 28 | AGENT_HINT | rate_limit→cooldown_resume 우선 | 우회 대신 대기 | allowed[RATE_LIMIT][0] | cooldown 전략 선택 |
| 29 | TODO | analyst agent 보류 | 현재 불필요 | 도입 보류 명시 | 미구현 표기 |
| 30 | TODO | judge 프롬프트 버전핀 | 재현성 | prompt_versions | v1 고정 기록 |
| 31 | IMPLEMENTED | complete_json schema 검증 | 구조 강제 | model_validate | 스키마 불일치시 None |
| 32 | RISK | judge temperature 비결정 | 재현성 저하 | temperature=0.1 고정 | 기본 0.1 확인 |
| 33 | TODO | supervisor 결정 HITL 승인 | low confidence 검토 | manual_operator_review | low시 사람 큐 |
| 34 | AGENT_HINT | parser_or_selector 진단 분기 | 파서 실패 식별 | _root_causes selector | no_rows→parser |
| 35 | AGENT_HINT | missing_official_api_or_key | API 계약 필요 식별 | API_CONTRACT layer | requires_official_api |
| 36 | TODO | judge 출력 PII/secret 마스킹 | 보안 | 로그 마스킹 | 키 노출 0 |
| 37 | RISK | mock/openai 출력 schema 차이 | 통합 깨짐 | 동일 schema 강제 | 양 provider 동일 schema |
| 38 | TODO | judge 호출 timeout 표준 | 지연 통제 | timeout=30s | 초과시 None |
| 39 | IMPLEMENTED | OpenAIJudgeClient 키 검증 | 키 없으면 즉시 실패 | len(key)==0 ValueError | 키 부재 명확 에러 |
| 40 | AGENT_HINT | confidence=high(allowed 1개) | 단일 안전후보 확신 | len(allowed)==1 | high 기록 |
| 41 | TODO | supervisor decision→strategy_memory 반영 | 학습 저장 | successful_strategy 갱신 | 성공시 memory update |
| 42 | IMPLEMENTED | preferred_strategy_for memory 조회 | 무의미 반복 회피 | 함수 | 학습전략 우선 |
| 43 | IMPLEMENTED | is_known_dead_end 판정 | 닫힌 소스 스킵 | terminal+no success | dead_end True시 스킵 |
| 44 | RISK | LLM 환각 entity | 잘못된 링크 | entity_linking 검증 | 근거없는 entity 필터 |
| 45 | TODO | judge 응답 길이 제한 | 비용 | max_tokens=512 | 초과 절단 |
| 46 | AGENT_HINT | body_ladder_fetch(BODY_FETCH) | 본문 점진 페치 | allowed[BODY_FETCH] | static→ladder |
| 47 | TODO | supervisor multi-source 배치 진단 | 효율 | 배치 decide | N소스 1회 진단 |
| 48 | RISK | judge JSON 파싱 깨짐 | None 양산 | try/except 로깅 | parse error 로그 |
| 49 | TODO | analyst→LangSmith eval set | 품질 회귀 | eval dataset | judge 정확도 추적 |
| 50 | IMPLEMENTED | _BASELINE_REJECTED 투명성 보고 | 거부 가시화 | rejected에 항상 포함 | proxy 등 보고됨 |
| 51 | AGENT_HINT | login_wall 진단 | 로그인벽 식별 | _root_causes login | login→manual |
| 52 | AGENT_HINT | captcha_challenge 진단 | 캡차 식별 | _root_causes captcha | captcha→차단보고 |
| 53 | TODO | judge fallback 사용률 메트릭 | 품질 모니터 | fallback 카운트 | fallback율 리포트 |
| 54 | RISK | openai import 비용(lazy) | 콜드스타트 | lazy import 유지 | mock시 openai 미import |
| 55 | TODO | supervisor confidence→재시도 예산 연동 | 적응 예산 | low시 예산 축소 | low시 1회만 |
| 56 | IMPLEMENTED | EVIDENCE_ANCHOR→adapter_anchor_fix | 근거 앵커 수정 | allowed map | anchor fix 선택 |
| 57 | IMPLEMENTED | SOURCE_VALUE→disable_low_value | 저가치 비활성 | allowed map | disable 선택 |
| 58 | TODO | judge 다국어 처리 검증 | ko/en 혼재 | language hint | ko 본문 정상 |
| 59 | RISK | supervisor LLM 콜백 예외 | 크래시 | try/except→None | 예외시 fallback |
| 60 | AGENT_HINT | ROBOTS→use_robots_allowed_path | robots 준수 | allowed[ROBOTS] | 허용경로만 |
| 61 | TODO | judge 결과 캐싱 | 중복 호출 절감 | content hash 캐시 | 동일입력 1회 |
| 62 | TODO | analyst agent 보류 결정 문서 | 범위 통제 | 도입 안함 명시 | 미도입 기록 |
| 63 | RISK | downstream 6 MOCK 노드 실데이터 오인 | 미완성 은폐 | MOCK 표기 유지 | mock 식별 가능 |
| 64 | IMPLEMENTED | fact_check hold→publish_or_hold | 발행 게이트 | downstream 연결 | hold시 미발행 |
| 65 | TODO | judge prompt injection 방어 | 보안 | 입력 sanitize | injection 무력화 |
| 66 | AGENT_HINT | spaced_probe(rate limit) | 간격 두고 탐침 | spaced_probe | 간격 준수 |
| 67 | TODO | supervisor 결정 reproducibility test | 회귀 | 동일입력 동일출력 | deterministic 검증 |
| 68 | IMPLEMENTED | confidence medium(다후보) | 복수 안전후보 | len(allowed)>1 | medium 기록 |
| 69 | RISK | LLM 비용 무제한 | 예산 초과 | run budget cap | cap 초과 중단 |
| 70 | TODO | judge eval golden set | 품질 기준 | golden 10건 | pass율 측정 |
| 71 | AGENT_HINT | cooldown_policy 저장 | 재실행 간격 | memory cooldown_policy | gdelt 900s |
| 72 | TODO | supervisor→audit_trace 일관 포맷 | 감사 표준 | 공통 schema | trace 필드 일치 |
| 73 | IMPLEMENTED | safety_policy=no_bypass 기본 | 우회 금지 기본 | memory default | no_bypass 유지 |
| 74 | RISK | mock judge significance 고정값 | 랭킹 왜곡 | mock 0.6 고정 인지 | 실 provider시 동적 |
| 75 | TODO | judge 응답 schema 진화 호환 | 버전 충돌 | optional 필드 | 구버전 파싱 |
| 76 | AGENT_HINT | unclassified_failure 기본 | 미분류 안전처리 | _root_causes 기본 | 미분류시 review |
| 77 | TODO | supervisor 실패 요약 LLM | 진단 품질 | 요약 프롬프트 | 요약 정확 |
| 78 | RISK | judge None→fallback 통계 누락 | 가시성 | fallback 카운트 | 누락 0 |
| 79 | IMPLEMENTED | get_judge mock 기본 | 키 없이 동작 | default mock | env 미설정시 mock |
| 80 | TODO | analyst 트렌드 종합 보류 명시 | 범위 | 미구현 | 표기 |
| 81 | AGENT_HINT | preferred_next_strategy fallback | 성공없을때 후보 | memory 필드 | next 후보 제공 |
| 82 | TODO | judge 호출 동시성 제한 | rate limit | semaphore | 동시 N제한 |
| 83 | RISK | supervisor 학습 오염 | 잘못된 성공기록 | 검증후 저장 | 검증된 success만 |
| 84 | IMPLEMENTED | adapter_name 메모리 저장 | 어댑터 재사용 | memory adapter_name | 저장됨 |
| 85 | TODO | judge 출력 톤(투자조언) 검사 | 정책 | 후처리 필터 | 매수/매도 0 |
| 86 | AGENT_HINT | body_fetch_strategy 저장 | 본문전략 학습 | memory 필드 | 저장됨 |
| 87 | TODO | supervisor decision 만료 | 오래된 학습 폐기 | TTL | 만료 재학습 |
| 88 | RISK | LLM 모델 변경시 회귀 | 출력 drift | model 핀 | model_used 기록 |
| 89 | IMPLEMENTED | browser_strategy 저장 | 브라우저전략 | memory 필드 | 저장됨 |
| 90 | TODO | judge 멀티스키마 라우팅 | 노드별 schema | schema map | 정확 라우팅 |
| 91 | AGENT_HINT | parser_notes 저장 | 셀렉터 메모 | memory 필드 | 저장됨 |
| 92 | TODO | supervisor HITL escalation 로그 | 추적 | escalation event | 로그 존재 |
| 93 | RISK | downstream LLM 연쇄 None | 빈 카드 | 노드별 fallback | 각 노드 fallback |
| 94 | IMPLEMENTED | evidence 필드 fact_check 입력 | 근거 기반 판정 | evidence list | 근거 전달 |
| 95 | TODO | judge 비용/품질 trade 리포트 | 운영 결정 | provider 비교 | 비교 리포트 |
| 96 | AGENT_HINT | evidence anchor fix 학습 | 앵커 수정 재사용 | memory | 저장 |
| 97 | TODO | supervisor 정책 변경 audit | 거버넌스 | allowed map 변경 로그 | 변경 추적 |
| 98 | RISK | LLM 응답 지연 누적 | 그래프 지연 | timeout+fallback | 지연시 fallback |
| 99 | TODO | judge golden 회귀 CI | 품질 게이트 | CI eval | PR시 eval |
| 100 | AGENT_HINT | confidence low→manual_operator_review | 사람 개입 | allowed 없을때 | low시 manual |

**완전 달성 기준:** judge(단기 무상태)/supervisor(장기 stateful) 코드 분리, LLM 제안 allowed 집합 안에서만(우회 0 채택), 모든 LLM 결정 audit trace+confidence, 실패→deterministic fallback 100%(예외 전파 0), supervisor 실 provider 옵션(끄면 규칙기반 완전 동작).

## L10. Agent orchestration framework: LangGraph / Deep Agents / tools / memory — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | downstream 11노드 StateGraph | 이벤트 처리 골격 | event_processing_graph.py | compile+invoke 성공 |
| 2 | IMPLEMENTED | source_parse(REAL) | 원천 파싱 | parse_source.py | 실동작 |
| 3 | IMPLEMENTED | normalize_event(REAL) | 정규화 | normalize_event.py | 실동작 |
| 4 | IMPLEMENTED | deduplicate_event(partial REAL) | 중복 제거 | deduplicate.py | dedupe_key 생성 |
| 5 | IMPLEMENTED | retrieve_past_context(REAL) | 과거맥락 | retrieve_context.py | 컨텍스트 조회 |
| 6 | IMPLEMENTED | publish_or_hold(REAL) | 발행 게이트 | publish_or_hold.py | status 결정 |
| 7 | IMPLEMENTED | entity_linking(MOCK) | 엔티티 연결 | entity_linking.py MOCK | MOCK 표기 |
| 8 | IMPLEMENTED | sector_mapping(MOCK) | 섹터 매핑 | sector_mapping.py MOCK | MOCK 표기 |
| 9 | IMPLEMENTED | impact_analysis(MOCK) | 영향분석 | impact_analysis.py MOCK | MOCK 표기 |
| 10 | IMPLEMENTED | evidence_check(MOCK) | 근거확인 | evidence_check.py MOCK | MOCK 표기 |
| 11 | IMPLEMENTED | fact_check(MOCK) | 사실확인 | fact_check.py MOCK | MOCK 표기 |
| 12 | IMPLEMENTED | final_writer(MOCK) | 최종카드 | final_writer.py MOCK | MOCK 표기 |
| 13 | IMPLEMENTED | env 토글 LLM/EMBEDDING_PROVIDER | mock/openai 전환 | settings | env 분기 |
| 14 | IMPLEMENTED | 크롤링 14노드 그래프 | 수집 상태머신 | ingestion/agents/graph.py | compile 성공 |
| 15 | IMPLEMENTED | 조건부 엣지 라우팅 | 성공/에러 분기 | add_conditional_edges | success/error |
| 16 | IMPLEMENTED | retry_decision 라우팅 | pass/retry/exhaust | _route_retry_decision | 3분기 동작 |
| 17 | IMPLEMENTED | strategy_sequence ladder | 전략 순차 | STRATEGY_SEQUENCE | 순서 진행 |
| 18 | IMPLEMENTED | 전략 소진 종료 | 무한루프 방지 | strategy_exhausted | exhaust→reflection |
| 19 | IMPLEMENTED | max_attempts 예산 | 자원 통제 | attempt>=max | 예산 종료 |
| 20 | IMPLEMENTED | error_analysis 노드 | 실패 분류 | _node_error_analysis | BLOCKED/retryable |
| 21 | IMPLEMENTED | source-specific extract hook | 소스별 커스텀 | src.extract() | API경로 우회 |
| 22 | IMPLEMENTED | strategy_router metadata | 수집 메타 결정 | strategy_router.py | StrategyDecision |
| 23 | IMPLEMENTED | decide_strategy_with_memory | 학습 반영 라우팅 | memory 덮어쓰기 | learned 우선 |
| 24 | TODO | redis checkpointer(durable) | 중단·재개 | redis saver 옵션 | 미도입시도 동작 |
| 25 | TODO | LangGraph 1.0 평가(redis 전환 동시) | durable execution | 전환 시점 평가 | 평가 문서 |
| 26 | TODO | Deep Agents 미도입 결정 문서 | 범위 통제 | 도입 안함 명시 | 결정 기록 |
| 27 | TODO | OpenAI Agents SDK 미도입 결정 | 일관성 | 도입 안함 | 기록 |
| 28 | TODO | CrewAI 미도입 결정 | 일관성 | 도입 안함 | 기록 |
| 29 | IMPLEMENTED | 버전핀 langgraph 0.2.76 | 안정성 | requirements 핀 | 핀 유지 |
| 30 | IMPLEMENTED | 버전핀 langchain 0.2.11 | 호환성 | 핀 유지 | v1 보류 |
| 31 | IMPLEMENTED | tool registry(allowed map) | 안전 전략 | _ALLOWED_BY_LAYER | 8 layer |
| 32 | IMPLEMENTED | unsafe 영구차단 | 우회 금지 | _UNSAFE_STRATEGIES | proxy 차단 |
| 33 | IMPLEMENTED | rate_limit→cooldown(우회 아님) | rate 준수 | allowed[RATE_LIMIT] | cooldown 선택 |
| 34 | AGENT_HINT | gdelt min_interval 60s/cooldown 900s | soft-429 회피 | scheduler 간격 | 60s 미만 호출 0 |
| 35 | AGENT_HINT | google_trends optional_enrichment | CONFIRMED_EXTERNAL_RATE_LIMIT | PASS 금지 | enrichment 표기 |
| 36 | AGENT_HINT | trends fallback chain | 대체 경로 | trending_now→RSS→serper/naver | fallback 동작 |
| 37 | TODO | Celery beat near_real_time(5~15분) | 실시간성 | beat schedule | bucket 등록 |
| 38 | TODO | Celery beat short_interval(30~60분) | 준실시간 | beat schedule | bucket 등록 |
| 39 | TODO | Celery beat medium_interval(2~6시간) | 중간주기 | beat schedule | bucket 등록 |
| 40 | TODO | Celery beat daily | 일배치 | beat schedule | bucket 등록 |
| 41 | TODO | Celery broker redis 전환 | memory→redis | REDIS_URL | redis 연결 |
| 42 | RISK | gdelt 빠른연속→soft-429 | 차단 | min_interval 강제 | 실측 60s |
| 43 | RISK | trends PASS 오표기 | 정책위반 | terminal status 고정 | PASS 0건 |
| 44 | RISK | LangGraph 1.0 마이그레이션 회귀 | 깨짐 | 회귀 테스트 | 11/14노드 통과 |
| 45 | RISK | checkpointer 없이 장기작업 중단 손실 | 재실행 비용 | redis saver | 도입시 재개 |
| 46 | IMPLEMENTED | event_queue 경계 | 수집↔처리 분리 | pipeline/event_queue.py | enqueue 분리 |
| 47 | TODO | event_queue redis 백엔드 | 영속 큐 | redis list | redis 전환 |
| 48 | IMPLEMENTED | runner map(run_one_source 등) | 실행 진입점 | runners/ | runner 동작 |
| 49 | IMPLEMENTED | run_phase 배치 실행 | phase 수집 | run_phase.py | phase 실행 |
| 50 | IMPLEMENTED | run_all_phases | 전체 실행 | run_all_phases.py | 전 phase |
| 51 | TODO | runner→Celery task 래핑 | 비동기화 | task decorator | task 등록 |
| 52 | TODO | runner contract runner 목록 명시 연결 | 누락 방지 | runner↔task 매핑 | 매핑 확정 |
| 53 | IMPLEMENTED | source_strategy_memory.yaml 영속 | 학습 저장 | configs yaml | 커밋됨 |
| 54 | IMPLEMENTED | save/load_strategy_memory | 메모리 IO | source_strategy_memory.py | round-trip |
| 55 | IMPLEMENTED | preferred_strategy_for consumer | 라우터 진입점 | 함수 | learned 반환 |
| 56 | IMPLEMENTED | is_known_dead_end 스킵 | 무의미 회피 | 함수 | dead_end 스킵 |
| 57 | TODO | context offloading 불필요 명시 | Deep Agents 회피근거 | 문서 | 결정 기록 |
| 58 | TODO | write_todos 플래닝 불필요 | 규칙기반 충분 | 문서 | 결정 기록 |
| 59 | IMPLEMENTED | audit_trace 모듈 | 감사 | audit_trace.py | trace 기록 |
| 60 | TODO | audit_trace 전 노드 커버 | 완전 감사 | 노드별 append | 누락 0 |
| 61 | RISK | celery memory backend 휘발 | 재시작 손실 | redis 전환 | plans/012 |
| 62 | AGENT_HINT | RATE_LIMIT decide→cooldown_resume | 우회 안함 | supervisor allowed | cooldown |
| 63 | IMPLEMENTED | production_scheduler | 스케줄 골격 | production_scheduler.py | 스케줄 동작 |
| 64 | IMPLEMENTED | production_state | 상태 추적 | production_state.py | 상태 머신 |
| 65 | TODO | scheduler→beat bucket 매핑 | 주기 배치 | bucket 함수 | 4 bucket |
| 66 | TODO | rate_limit_policy per-source | 소스별 간격 | policy 로드 | 간격 적용 |
| 67 | RISK | 동시 소스 호출 폭주 | rate 위반 | concurrency cap | 동시 제한 |
| 68 | IMPLEMENTED | source_parse→normalize 엣지 | 순차 처리 | add_edge | 순서 보장 |
| 69 | IMPLEMENTED | publish_or_hold→END | 종료 | add_edge END | 정상 종료 |
| 70 | RISK | final_card None시 RuntimeError | 크래시 | None 체크 | 예외 명확 |
| 71 | TODO | downstream HITL(publish 승인) | 사람 검토 | 0.2.76 interrupt | hold시 검토 |
| 72 | TODO | graph trace LangSmith | 관측 | LANGSMITH env | trace 노출 |
| 73 | IMPLEMENTED | EventState TypedDict | 상태 스키마 | event_state.py | 필드 정의 |
| 74 | IMPLEMENTED | CrawlingAgentState TypedDict | 크롤링 상태 | state.py | 필드 정의 |
| 75 | IMPLEMENTED | prompt_versions state | 재현성 | initial state | v1 핀 |
| 76 | RISK | TypedDict 직렬화(경로 str) | 직렬화 깨짐 | path를 str 저장 | str 유지 |
| 77 | TODO | 그래프 시각화 mermaid | 문서 | get_graph mermaid | 다이어그램 |
| 78 | AGENT_HINT | RSS 소스 playwright 스킵 | 불필요 렌더 회피 | _is_rss_or_feed | RSS시 httpx만 |
| 79 | IMPLEMENTED | selenium fallback(ready 체크) | 렌더 대체 | selenium_env_status | NOT_READY 처리 |
| 80 | IMPLEMENTED | playwright ladder | JS 렌더 | _PLAYWRIGHT_STRATEGIES | 순차 시도 |
| 81 | IMPLEMENTED | EXTRACTION_EMPTY→playwright 점프 | 효율 | select_next_strategy | 직접 점프 |
| 82 | RISK | playwright 자원 소비 | 메모리 | budget cap | 예산 제한 |
| 83 | TODO | runner 멱등성 보장 | 재실행 안전 | idempotent | 중복 무해 |
| 84 | TODO | Celery task 재시도 정책 | 실패 복구 | max_retries | 정책 정의 |
| 85 | TODO | dead letter queue | 실패 격리 | DLQ | 실패 분리 |
| 86 | AGENT_HINT | preferred_browser=selenium 힌트 | 브라우저 선택 | source_spec | selenium 우선 |
| 87 | IMPLEMENTED | quality_score 게이트 | 품질 임계 | compute_quality_score | 임계 판정 |
| 88 | IMPLEMENTED | SUCCESS/PARTIAL/BLOCKED/FAILED | 상태 분류 | quality_status | 4상태 |
| 89 | TODO | graph 단위 회귀 테스트 | 안정성 | invoke 테스트 | 통과 |
| 90 | RISK | 6 MOCK 노드 프로덕션 오용 | 가짜 출력 | MOCK 게이트 | mock 표기 강제 |
| 91 | TODO | downstream→실 provider 전환 검증 | 실동작 | openai 토글 | 실 출력 |
| 92 | AGENT_HINT | confirmation_policy community 보정 | 단독확정 금지 | strategy_router | unconfirmed 강제 |
| 93 | IMPLEMENTED | artifact_store 경로 표준 | 산출물 추적 | artifact_store.py | 경로 일관 |
| 94 | TODO | run_id 전 파이프 전파 | 추적성 | run_id state | 전파 확인 |
| 95 | RISK | langchain 0.2.11 보안패치 | 취약점 | 핀 유지+모니터 | CVE 추적 |
| 96 | TODO | beat schedule rate-aware 검증 | rate 준수 | 간격 테스트 | 위반 0 |
| 97 | AGENT_HINT | disable_low_value(SOURCE_VALUE) | 저가치 비활성 | allowed map | disable |
| 98 | TODO | orchestration handoff 문서 동기화 | 인계 | 08 handoff md | 최신화 |
| 99 | IMPLEMENTED | _compiled 싱글톤 캐시 | 재컴파일 회피 | get_compiled_graph | 1회 컴파일 |
| 100 | TODO | runner ↔ beat bucket ↔ rate policy 연결표 | 완전 결선 | 매핑표 | 3자 매핑 완성 |

**완전 달성 기준:** 두 그래프(14/11노드) compile+invoke, 5 REAL + 6 MOCK 명시, tool registry/allowed strategy로 우회 영구차단, checkpointer 미도입시도 단발 invoke 완전 동작, Deep Agents/벤더SDK 미도입 결정 + 버전핀(0.2.76/0.2.11) 유지.

## L11. Safety / legal / trust / no-bypass — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | POLICY | 우회 전면 금지 불변(R-Bypass) | 법적·ToS 노출 차단 | 코드/문서 enforced | 우회 코드 0 |
| 2 | IMPLEMENTED | CAPTCHA 우회 금지→BLOCKED_TERMINAL | CFAA/ToS 위반 방지 | blocker terminal | CAPTCHA=terminal |
| 3 | IMPLEMENTED | login wall 우회 금지 | 무단접근 방지 | LOGIN blocker | login=terminal |
| 4 | IMPLEMENTED | paywall 우회 금지 | 저작권·계약 위반 방지 | PAYWALL blocker | paywall=terminal |
| 5 | POLICY | robots 무시 금지 | 접근정책 준수 | allowlist | robots 위반 0 |
| 6 | POLICY | proxy rotation 금지 | anti-bot 회피 차단 | proxy 미사용 | proxy 0 |
| 7 | POLICY | 내부 RPC scraping 금지 | 비공개 API 위반 차단 | 공식 라우트만 | 비공개 호출 0 |
| 8 | POLICY | google_trends PASS 금지 | 우회 사칭 방지 | CONFIRMED_EXTERNAL_RATE_LIMIT | PASS 0 |
| 9 | RISK | newsapi 비상업 약관(localhost) | 상업 위반 노출 | CONDITIONAL | 상업 시 off/유료 |
| 10 | RISK | guardian 재배포 금지 | 전문 게시 위반 | CONDITIONAL 요약+URL | 본문 게시 0 |
| 11 | RISK | nyt 상업 라이선스 필요 | 무라이선스 상업 위반 | CONDITIONAL | 라이선스 전 비상업 |
| 12 | RISK | aladin 개인free/상업별도 | 상업 위반 노출 | CONDITIONAL | 상업 시 라이선스 |
| 13 | POLICY | reuters 라이선스+bot 제외 | 라이선스 위반 차단 | MVP_EXCLUDED | 수집 0 |
| 14 | POLICY | x 유료 API 제외 | 무단 수집 차단 | MVP_EXCLUDED | 수집 0 |
| 15 | IMPLEMENTED | 전문 저장/재배포 금지(R-FullText) | 저작권 침해 차단 | raw_text="" | 전문 0 |
| 16 | IMPLEMENTED | CommunityCorroborationGate publish 봉인 | 미검증 신호 게시 차단 | gate | dcinside publish gated |
| 17 | POLICY | community=early signal≠evidence | 명예훼손·오보 차단 | corroboration 요구 | 단독 신호 게시 0 |
| 18 | IMPLEMENTED | 펌핑/투자권유 제목 publish_blocked | 시세조종 조력 차단 | publish_blocked | 펌핑 게시 0 |
| 19 | POLICY | 금융 익명 갤러리 internal_queue_only | 미검증 금융신호 격리 | internal_queue | 외부노출 0 |
| 20 | POLICY | 투자조언 금지(정보제공만) | 금융규제 위반 방지 | 가치판단 차단 | 매수/매도 출력 0 |
| 21 | POLICY | 시장가격 가치판단 금지 | 조언 경계 유지 | 톤다운 필터 | 좋다/사라 0 |
| 22 | IMPLEMENTED | EvidenceGate synthetic URL 거부 | 위조증거 차단 | 패턴 reject | synthetic 0 |
| 23 | IMPLEMENTED | dead/local URL 안정증거 금지 | hallucinated evidence 차단 | _is_local_or_synthetic | dead URL 0 |
| 24 | RISK | dcinside ToS 적법성 UNVERIFIED | 자동수집 적법성 미확정 | 수집닫고 publish봉인 | 법무검토 전 봉인 |
| 25 | IMPLEMENTED | dcinside 닉네임 PII 미수집 | 개인정보 노출 차단 | PII 제외 | PII 0 |
| 26 | POLICY | "ToS verified" 사칭 금지 | 허위 적법성 주장 차단 | UNVERIFIED 명시 | 사칭 0 |
| 27 | TODO | AI 요약 명예훼손 가드 | 허위사실 적시 차단 | 사실/추정 라벨 | 단정 표현 검토 |
| 28 | TODO | 미검증 신호 "unverified" 라벨 | 신뢰 오인 방지 | label 부착 | 라벨 누락 0 |
| 29 | TODO | retention TTL 정책 | 개인정보·저장 최소화 | TTL cron | 만료 삭제 |
| 30 | TODO | PII 스크럽 파이프라인 | 개인정보보호 | 마스킹 | PII 노출 0 |
| 31 | IMPLEMENTED | secret 출력 금지(존재/길이만) | 키 유출 차단 | scan_secrets | secret scan PASS |
| 32 | IMPLEMENTED | .env os.getenv/pydantic만 | 하드코딩 차단 | settings | 하드코딩 0 |
| 33 | IMPLEMENTED | 산출물 gitignored | 원문/키 비커밋 | .gitignore | 커밋 0 |
| 34 | IMPLEMENTED | forbidden_command_guard | 파괴적 명령 차단 | guard | rm/push/reset 차단 |
| 35 | POLICY | git push/reset/clean 금지 | 데이터 유실 차단 | guard | 실행 0 |
| 36 | POLICY | publication boundary 격리 | 재배포 경로 차단 | boundary | 수집→게시 직결 0 |
| 37 | IMPLEMENTED | SourceSupervisor 우회 제안 거부 | LLM 우회 유도 차단 | 거부 로직 | 우회 제안 0 |
| 38 | RISK | prompt injection(외부텍스트→LLM) | hallucinated evidence | EvidenceGate+신뢰경계 | 주입 가드 |
| 39 | TODO | LLM 입력 신뢰경계 재검토 | 6 mock 노드 실연결 시 | 입력 sanitize | 경계 검증 |
| 40 | POLICY | gdelt 단일429 disable 금지 | 과잉차단 방지 | cooldown+카운터 | 단일429 유지 |
| 41 | IMPLEMENTED | provider rate limit 준수 | ToS 위반 차단 | min_interval | 위반 0 |
| 42 | TODO | source별 ToS 약관 한도 문서화 | 한도 준수 근거 | policy note | 문서 갱신 |
| 43 | COMMERCIAL | NewsData.io 상업 가능 | 상업 표면 후보 | 상업 우선 | ToS 확인 |
| 44 | COMMERCIAL | SEC EDGAR/OpenDART 공공데이터 | 상업 제약 낮음 | 공식 API | 라이선스 확인 |
| 45 | TODO | source license 메타 자동판정 | 상업 가부 게이트 | license field | 미상=비상업 |
| 46 | RISK | google_programmable_search CX 미설정 | 재활성 오작동 | 비활성 유지 | 재활성 0 |
| 47 | POLICY | fmkorea Turnstile 우회 금지 | CAPTCHA 위반 차단 | MVP_EXCLUDED | 수집 0 |
| 48 | POLICY | blind login 우회 금지 | 무단접근 차단 | MVP_EXCLUDED | 수집 0 |
| 49 | TODO | 명예훼손 리스크 소스 식별 | 고위험 콘텐츠 관리 | 위험 태그 | 식별 완료 |
| 50 | TODO | 인용 출처 표기 강제 | fair use·저작권 | attribution | 누락 0 |
| 51 | IMPLEMENTED | evidence URL 중심 표면 | 전문 비공개 | URL+요약 | 전문공개 0 |
| 52 | TODO | 요약 길이 인용범위 cap | fair use 준수 | snippet cap | 초과 절단 |
| 53 | POLICY | krx_kind 비공식 경로 금지 | ToS 위반 차단 | DEFERRED | 비공식 0 |
| 54 | TODO | GDPR/개인정보 대상 데이터 식별 | 규제 준수 | PII 분류 | 분류 완료 |
| 55 | TODO | 데이터 주체 삭제요청 처리 경로 | 개인정보권 | 삭제 API | 삭제 가능 |
| 56 | IMPLEMENTED | numeric_signal 분류 | 투자조언 분리 | NUMERIC_SIGNAL | 조언 0 |
| 57 | TODO | 금융 콘텐츠 면책 고지 | 규제 대응 | disclaimer | 고지 노출 |
| 58 | POLICY | fallback chain 0 bypass | 우회 없는 대체 | RSS/news | bypass 0 |
| 59 | TODO | 저작권 침해 신고 대응 경로 | DMCA 등 대응 | takedown 절차 | 절차 존재 |
| 60 | TODO | source 추가 전 법무 게이트 | 무검토 추가 차단 | 리뷰 필수 | 미검토 추가 0 |
| 61 | TODO | 상업 배포 전 라이선스 전수검토 | 상업 위반 차단 | 라이선스 매트릭스 | 전수 확인 |
| 62 | IMPLEMENTED | health gate cooldown 차단 호출 0 | 과수집·차단 회피 | gate | 차단 소스 호출 0 |
| 63 | TODO | rate limit 약관수치 vs 보수설정 정합 | 한도 준수 | policy 정렬 | 정합 확인 |
| 64 | POLICY | 우회 제안 문서/코드 금지 | 정책 일관성 | 리뷰 | 우회 제안 0 |
| 65 | TODO | community 콘텐츠 보존기간 단축 | 개인정보 최소화 | community TTL | 단축 TTL |
| 66 | TODO | 익명 사용자 식별정보 비저장 | PII 보호 | 익명화 | 식별정보 0 |
| 67 | IMPLEMENTED | dcinside role 신호로 재정의 | 본문 재배포 회피 | 신호 source | 본문 0 |
| 68 | TODO | AI 생성물 출처 명시 | 신뢰·투명성 | "AI 요약" 라벨 | 라벨 부착 |
| 69 | TODO | 허위정보 정정 메커니즘 | 신뢰 유지 | 정정 경로 | 정정 가능 |
| 70 | POLICY | secret 에러메시지 마스킹 | 키 유출 차단 | 마스킹 | 에러에 키 0 |
| 71 | TODO | 제3자 라이선스 콘텐츠 격리 | 재배포 위반 차단 | license 격리 | 격리 적용 |
| 72 | TODO | 데이터 국외이전 검토 | 규제 준수 | 이전 정책 | 검토 완료 |
| 73 | IMPLEMENTED | Admin API server-only 격리 | 토큰 노출 차단 | server-only | 노출 0 |
| 74 | RISK | Admin 빈토큰=허용(dev) | 운영 전 인증 우회 | token 필수화+RBAC | 운영 전 강제 |
| 75 | TODO | audit 로그(정책 위반 추적) | 사후 추적 | audit log | 로그 존재 |
| 76 | POLICY | 사용자 명시 없이 excluded 미접촉 | 무단 재활성 차단 | EXCLUDED 종결 | 접촉 0 |
| 77 | TODO | 콘텐츠 신선도 vs 보존 균형 | retention 정책 | freshness TTL | 균형 적용 |
| 78 | TODO | 상업/비상업 모드 토글 | ToS 차등 적용 | mode flag | 모드별 소스 |
| 79 | COMMERCIAL | 공공데이터 저제약 | 상업 표면 안전 | 공식 API | 라이선스 확인 |
| 80 | TODO | 뉴스 헤드라인 저작권 검토 | 짧은 표현 보호 여부 | 인용 정책 | 검토 완료 |
| 81 | POLICY | reddit MVP 보류(사용자 확정) | 무단 수집 차단 | MVP_DEFERRED | 수집 0 |
| 82 | TODO | LLM 출력 투자조언 누출 모니터 | 규제 위반 차단 | 출력 필터 | 조언 0 |
| 83 | TODO | 미성년/민감정보 필터 | 개인정보보호 | 민감정보 차단 | 노출 0 |
| 84 | IMPLEMENTED | EvidenceGate role+proof 권위증거 | 계약 독립입증 | source_specific_proof | contract_pass |
| 85 | TODO | takedown 후 재수집 차단 목록 | DMCA 재발 방지 | blocklist | 재수집 0 |
| 86 | POLICY | 산출물 secret scan 상시 PASS | 유출 상시 차단 | scan gate | PASS 유지 |
| 87 | TODO | community 신호 신뢰도 점수화 | 오보 가중 방지 | confidence score | 점수 부착 |
| 88 | TODO | 외부 텍스트 sanitize(injection) | LLM 안전 | sanitize | 주입 차단 |
| 89 | POLICY | gdelt UA 필수 준수 | provider 요구 | UA 헤더 | UA 설정 |
| 90 | TODO | 데이터 처리방침 문서 공개 | 투명성·규제 | privacy policy | 문서 공개 |
| 91 | TODO | 소스별 robots 재검증 주기 | stale robots 방지 | robots TTL | 재검증 |
| 92 | IMPLEMENTED | mirror 데이터 유실 아님 검증 | 무결성 | bridge mirror | 계약 검증 |
| 93 | TODO | 명예훼손 고위험 키워드 게이트 | 법적 노출 차단 | 키워드 필터 | 게이트 적용 |
| 94 | POLICY | 비공개 endpoint 호출 금지 | ToS 위반 차단 | 공식만 | 비공개 0 |
| 95 | TODO | 상업 라이선스 매트릭스 유지 | 상업 가부 단일출처 | license matrix | 갱신 유지 |
| 96 | TODO | EU/한국 개인정보법 적용범위 | 관할 규제 | 관할 분석 | 분석 완료 |
| 97 | IMPLEMENTED | 우회 0건 입증(rate_limit_evidence §5) | 정책 준수 증거 | evidence 문서 | bypass 0 |
| 98 | TODO | 면책·이용약관 사용자 고지 | 법적 보호 | ToS 페이지 | 고지 존재 |
| 99 | TODO | L11 정책 회귀 테스트 | 무회귀 | 정책 테스트 | 전 통과 |
| 100 | TODO | 정기 법무 재검토 주기 | 약관 변경 대응 | 분기 리뷰 | 리뷰 실행 |

**완전 달성 기준:** 우회 0건 + google_trends CONFIRMED_EXTERNAL_RATE_LIMIT 유지, 전문 저장/재배포 0건 + evidence 중심, CommunityCorroborationGate 봉인 + 미검증 라벨 + 명예훼손 게이트, 투자조언 0건(numeric 분류+필터+면책), RISK 소스 CONDITIONAL + 상업/비상업 토글, retention TTL/PII 스크럽/삭제경로 IMPLEMENTED 전환, secret scan 상시 PASS + 파괴 명령 guard.

## L12. Monitoring / observability / cost / rate-limit — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | production_summary.json run별 산출 | 운영 지표 단일 출처 | monitoring.py | summary 생성 |
| 2 | IMPLEMENTED | alerts.json + critical 분리 | exit code 연동 | build_alerts | critical 게이트 |
| 3 | IMPLEMENTED | source_health.csv | 소스별 상태 추적 | write_monitoring_report | csv 생성 |
| 4 | IMPLEMENTED | raw_events_failure CRITICAL | 적재 실패 차단 | build_alerts | failed>0 차단 |
| 5 | IMPLEMENTED | bridge_contract_fail CRITICAL | 스키마 실패 차단 | contract pass | fail 차단 |
| 6 | IMPLEMENTED | secret_exposure 스캔 | 키 노출 방지 | _scan_secret_suspect | needle 검출 |
| 7 | IMPLEMENTED | source_without_state CRITICAL | 침묵 실패 방지 | state summary | 누락 차단 |
| 8 | IMPLEMENTED | needs_operator_review ERROR | 사람 개입 트리거 | source state | ERROR 발생 |
| 9 | IMPLEMENTED | worker heartbeat healthcheck | 죽은 워커 감지 | compose 60s | stale 재시작 |
| 10 | IMPLEMENTED | agent heartbeat healthcheck | agent 워커 헬스 | compose 60s | stale 재시작 |
| 11 | IMPLEMENTED | LANGSMITH opt-in 트레이싱 | LLM 관측 선택적 | LANGSMITH_TRACING | opt-in 동작 |
| 12 | TODO | 실시간 rate-limit 대시보드 | cooldown 가시성 부재 | rate_limit_store 노출 | cooldown 조회 |
| 13 | TODO | 429 카운트 추적 | provider throttle 추세 | counter per source | 429 추세 |
| 14 | TODO | cooldown_until 노출 | 다음 재시도 시점 | get_next_retry_at | 시각 표시 |
| 15 | TODO | quarantine 현황 노출 | 격리 소스 가시화 | quarantine hash | 격리 목록 |
| 16 | TODO | LLM 토큰 cost 추적 | 비용 폭발 감지 | token counter | 토큰 집계 |
| 17 | TODO | 검색 API cost 추적 | serper/tavily/exa 비용 | call counter | 호출 집계 |
| 18 | TODO | daily quota 카운터 가시화 | 한도 소진 가시성 | quota:{src}:{date} | 잔여 노출 |
| 19 | RISK | quota 미구현 비용 폭발 | RISK-R02 | quota_guard INCR+TTL | 한도 적용 |
| 20 | TODO | newsapi 90 한도 알람 | 무료 티어 보호 | daily_quota yaml | 90 도달 skip |
| 21 | TODO | nyt 450 한도 알람 | 티어 마진 | daily_quota yaml | 450 skip |
| 22 | RISK | google_trends PASS 둔갑 금지 | 거짓 보고 | CONFIRMED 고정 | PASS 표기 0 |
| 23 | IMPLEMENTED | EXTERNAL_RATE_LIMITED 상태 | 정직한 종결 | production_state | READY 둔갑 0 |
| 24 | TODO | gdelt escalation 카운터 노출 | 무한 pending 침묵 방지 | consecutive_pending | threshold=3 ESCALATE |
| 25 | TODO | next_resume_at 가시화 | 자동 재개 시점 | governor state | 재개 시각 |
| 26 | TODO | cost 일일 상한 알람 | 예산 초과 방지 | budget threshold | 초과 알람 |
| 27 | COMMERCIAL | daily_quota = 비용 예측성 | 가격·마진 설계 | quota guard | 최악 비용 산출 |
| 28 | COMMERCIAL | 우회 0 = 계약 가능성 | B2B 법무 통과 | no-bypass 정책 | grep 0건 |
| 29 | TODO | XLEN 큐 깊이 모니터 | 소비 지연 감지 | XLEN 주기 조회 | 깊이 대시보드 |
| 30 | TODO | XPENDING PEL 적체 모니터 | poison/지연 감지 | XPENDING 조회 | 적체 알람 |
| 31 | TODO | consumer lag 지표 | 처리 뒤처짐 | lag 계산 | lag 알람 |
| 32 | TODO | avg_latency_ms per source | 소스별 성능 | summary 필드 | latency 추세 |
| 33 | IMPLEMENTED | avg_latency_ms 필드 | 지연 집계 자리 | build_monitoring_summary | 값 채움 |
| 34 | IMPLEMENTED | error_by_root_cause 집계 | 실패 원인 분류 | summary 필드 | unknown 0 지향 |
| 35 | TODO | unknown_root_cause 0 게이트 | 침묵 실패 방지 | taxonomy 강제 | unknown 추적 |
| 36 | IMPLEMENTED | state_distribution 집계 | 소스 상태 분포 | summarize_states | 분포 노출 |
| 37 | TODO | all_sources_skipped WARNING 추적 | cadence 오류 감지 | plan_due=0 | 의도 확인 |
| 38 | IMPLEMENTED | external_errors WARNING | 외부 장애 집계 | build_alerts | 집계 동작 |
| 39 | IMPLEMENTED | quarantined WARNING | 격리 집계 | build_alerts | 집계 동작 |
| 40 | TODO | alerting 채널(slack/webhook) | critical 실시간 통지 | webhook emit | 알림 도달 |
| 41 | RISK | alert 파일만 존재 푸시 없음 | 인지 지연 | webhook 연동 | 푸시 동작 |
| 42 | TODO | rate_limit_cache.json 가시화 | 현재 유일 모니터 자산 | state 파일 노출 | 조회 가능 |
| 43 | IMPLEMENTED | rate_limit_store status() | 백엔드 헬스 | READY/DEGRADED | 상태 노출 |
| 44 | TODO | DEGRADED_FALLBACK 알람 | redis 다운 감지 | store status | fallback 알람 |
| 45 | RISK | redis 다운 시 memory 폴백 침묵 | 멀티워커 정합 깨짐 | status 알람 | fallback 가시화 |
| 46 | TODO | cooldown 지수증가 추적 | IP 차단 예방 가시화 | 600→1800→7200 | 증가 로그 |
| 47 | IMPLEMENTED | _MAX_COOLDOWN 86400 clamp | 무한 대기 방지 | governor | clamp 적용 |
| 48 | TODO | Retry-After 헤더 우선 추적 | provider 지시 준수 | 헤더>cooldown | 헤더 적용 |
| 49 | TODO | per-source 호출 빈도 추적 | min_interval 준수 검증 | call timestamp | 위반 0 |
| 50 | RISK | min_interval 위반 IP 차단 | 데이터 자산 손실 | SET NX EX 잠금 | 위반 0 |
| 51 | IMPLEMENTED | gdelt 60s/900s 정책 | 보수적 throttle | rate_limit_policy.yaml | 정책 일치 |
| 52 | IMPLEMENTED | trends 7200s/3600s/0재시도 | anti-abuse 준수 | rate_limit_policy.yaml | max_retries 0 |
| 53 | TODO | cost per source 집계 | 소스별 비용 귀속 | API call×단가 | 비용 분해 |
| 54 | TODO | LLM provider cost(LangSmith) | 토큰 비용 추적 | LangSmith opt-in | 토큰 노출 |
| 55 | COMMERCIAL | cost 가시성 = 마진 관리 | 단가 설계 | cost 대시보드 | 마진 산출 |
| 56 | TODO | run간 비용 추세 | 비용 증가 감지 | 시계열 집계 | 추세 알람 |
| 57 | TODO | worker 처리량 메트릭 | 용량 계획 | task/min | 처리량 노출 |
| 58 | TODO | Celery task 실패율 | 미구현 task 모니터 | Flower/메트릭 | 실패율 |
| 59 | RISK | Celery 미구현 task 관측 공백 | plans/012 | Flower 연동 | task 가시화 |
| 60 | TODO | beat 스케줄 발행 로그 | 스케줄 정합 검증 | beat dry-run | 발행 확인 |
| 61 | TODO | quota/quarantine 제외 반영 로그 | 스케줄 정확성 | beat tick 로그 | 제외 확인 |
| 62 | TODO | retry_queue 깊이 모니터 | 재시도 적체 | ZCARD retry_queue | 깊이 노출 |
| 63 | TODO | retry_queue drain 지연 | 만기 항목 적체 | ZRANGEBYSCORE 모니터 | drain 지연 |
| 64 | TODO | DLQ 깊이 알람 | poison 누적 | XLEN dlq | dlq>0 알람 |
| 65 | RISK | DLQ 침묵 시 데이터 손실 | 미인지 유실 | dlq 알람 | 0 유지 |
| 66 | IMPLEMENTED | AOF durability | 크래시 내구성 | appendonly yes | RDB-only 아님 |
| 67 | TODO | AOF 디스크 사용 모니터 | 디스크 고갈 방지 | redis_data 용량 | 용량 알람 |
| 68 | TODO | redis 메모리 사용 모니터 | OOM 방지 | INFO memory | maxmemory 정책 |
| 69 | RISK | redis maxmemory 미설정 | OOM 위험 | eviction 정책 | 정책 설정 |
| 70 | TODO | heartbeat stale 알람 push | 워커 죽음 통지 | healthcheck→alert | 통지 도달 |
| 71 | IMPLEMENTED | restart on-failure | 자동 복구 | compose | 재시작 동작 |
| 72 | TODO | container 헬스 집계 대시보드 | 전체 스택 가시성 | compose ps | 헬스 노출 |
| 73 | TODO | postgres 미구현 모니터 공백 | raw_events 적재처 | PG 연동 후 | 적재 모니터 |
| 74 | RISK | postgres 미구현 P0 | 영속 적재처 부재 | plans/012 | DB 배선 |
| 75 | TODO | Milvus 헬스 모니터 | 벡터 검색 가용성 | 9091 metrics | 헬스 노출 |
| 76 | IMPLEMENTED | Milvus healthz healthcheck | 컨테이너 헬스 | compose | healthz 동작 |
| 77 | IMPLEMENTED | OpenSearch cluster health | 색인 가용성 | compose | health 동작 |
| 78 | TODO | secret 마스킹 로그 검증 | 키 노출 0 | 마스킹 정책 | grep 0건 |
| 79 | IMPLEMENTED | secret scan PASS 게이트 | CI 가드 | scan 도구 | PASS 유지 |
| 80 | TODO | source별 success rate 추세 | 소스 건강도 | success/attempt | rate 추세 |
| 81 | TODO | dedup rate 모니터 | 중복 비율 가시화 | duplicates/collected | dedup 노출 |
| 82 | IMPLEMENTED | duplicates_skipped 집계 | dedup 효과 | summary 필드 | 집계 동작 |
| 83 | TODO | body_present rate | 본문 확보율 | body_present_count | rate 노출 |
| 84 | IMPLEMENTED | record_type별 카운트 | 수집 구성 | summary 필드 | 분포 노출 |
| 85 | TODO | time_precision 분포 모니터 | 시각 품질 | time_precision 필드 | 분포 노출 |
| 86 | TODO | run_id 전 구간 trace | A→B→DB 추적 | run_id 전파 | trace 연결 |
| 87 | RISK | A/B trace 단절 | 장애 추적 곤란 | run_id 공유 | 연결 확인 |
| 88 | TODO | alert 심각도별 라우팅 | 노이즈 감소 | sev→채널 | 라우팅 |
| 89 | TODO | flapping 소스 감지 | 격리/복귀 반복 | state 전이 추적 | flap 알람 |
| 90 | TODO | 4주 연속 BLOCKED 제안 리포트 | registry 갱신 제안 | 자동 미수정 | 사람 승인 리포트 |
| 91 | COMMERCIAL | 자동 격리·복귀 = 운영인력 최소화 | 죽은 소스 비가시 | quarantine 자동 | 인력 절감 |
| 92 | COMMERCIAL | 가용성 SLA = 신뢰 | 사용자 신뢰 | health 게이트 | SLA 측정 |
| 93 | AGENT_HINT | operations-sre-agent: 진단 담당 | 운영 이슈 원인 특정 | 본 보고서 | 원인 명확 |
| 94 | AGENT_HINT | orchestrator-architect: 대시보드 설계 | 관측 토폴로지 | handoff | 설계 수정 |
| 95 | TODO | Prometheus exporter | 표준 메트릭 | exporter 추가 | 메트릭 수집 |
| 96 | TODO | Grafana 대시보드 | 시각화 | 패널 정의 | 대시보드 |
| 97 | RISK | Windows solo pool 모니터 한계 | 단일 스레드 | 컨테이너 관측 | Linux 메트릭 |
| 98 | TODO | live_smoke_audit 정기화 | 회귀 감지 | live_smoke_audit.py | 주기 실행 |
| 99 | IMPLEMENTED | live_smoke_audit 존재 | 스모크 자산 | orchestration | 감사 동작 |
| 100 | TODO | 완전관측 verdict 게이트 | L12 종료 조건 | cost+rate+health 노출 | 3축 가시화 |

**완전 달성 기준:** production_summary/alerts/source_health가 critical alert로 exit code 좌우(구현), 실시간 rate-limit 가시성(cooldown_until·429·quarantine)과 cost 추적(LLM 토큰·검색 quota) 노출, heartbeat worker 헬스 + AOF durability, google_trends가 어떤 지표에서도 PASS 미표기.

## L13. Product surface: dashboard / alert / report / API / community — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | IMPLEMENTED | events list 라우트(/events) | 코어 탐색 표면 | 유지, evidence 구조화 후 재사용 | /events 200, EventCard 렌더 |
| 2 | IMPLEMENTED | event detail(/events/[eventId]) | 근거 추적 종착점 | evidence pane 강화 | 404 분기, evidence 섹션 |
| 3 | IMPLEMENTED | search 라우트(/search) | 발견성 핵심 | search hit→detail 연결 | 쿼리 입력 시 hits 표시 |
| 4 | IMPLEMENTED | themes list/detail 라우트 | 집계 탐색 진입 | PARTIAL 라벨 부착 | 라우트 200, 미검증 라벨 |
| 5 | IMPLEMENTED | sectors list/detail 라우트 | 섹터별 필터 진입 | PARTIAL 라벨 부착 | 라우트 200 |
| 6 | IMPLEMENTED | admin 라우트(server-only X-Admin-Token) | 운영 표면 분리 | 토큰 서버측 유지 | 클라에 토큰 미노출 |
| 7 | IMPLEMENTED | 11 라우트 + layout/loading/error/not-found | 기본 UX 셸 | 유지 | 4개 상태 컴포넌트 |
| 8 | IMPLEMENTED | ConfidenceBadge 백분율 | 신뢰 점수 가시화 | tooltip/근거 연결 | 점수 0~100% 렌더 |
| 9 | IMPLEMENTED | EventFilters 컴포넌트 | 목록 좁히기 | 유지 | theme/sector 필터 |
| 10 | IMPLEMENTED | HealthStatus 컴포넌트 | 시스템 신뢰 신호 | source status 연계 | health API 상태 |
| 11 | TODO | evidence 타입 string[]→구조화 객체 | attribution 필수 | {source_name,url,published_at,snippet,source_status} | 출처명+링크+날짜 표시 |
| 12 | TODO | evidence pane 카드형 UI | 추적성 차별화 핵심 | favicon+발행일+외부링크+snippet | detail evidence 카드 |
| 13 | TODO | 출처 외부 링크(rel=noopener) | 원본 검증 경로 | anchor+보안 rel | 클릭 시 원문 새 탭 |
| 14 | TODO | 재배포 금지 소스 snippet-only | guardian/nyt 라이선스 | source_license 플래그 | nyt 본문 미노출, snippet+링크 |
| 15 | TODO | alert 제품표면(이벤트 push) | retention/B2B 1순위 | 신규 라우트+구독 | 구독 이벤트 시 alert 큐잉 |
| 16 | TODO | alert 규칙 빌더(theme/sector/keyword) | 사용자별 관련성 | 필터 조건 저장 | 규칙 저장/매칭 |
| 17 | TODO | API 상품(외부 계약 노출) | events/search 재활용 | OpenAPI+키 인증 | 인증 키로 events 조회 |
| 18 | TODO | API rate limit/quota | B2B 과금 단위 | 키별 카운터 | 초과 시 429 |
| 19 | TODO | report 상품(themes/sectors 집계) | Meltwater형 워크플로 | PARTIAL 해소 선행 | 집계 리포트 생성 |
| 20 | TODO | shadcn/ui 도입 | 일관 컴포넌트/접근성 | 기본 Tailwind→shadcn | 버튼/카드/뱃지 전환 |
| 21 | TODO | i18n(ko/en) | B2B 글로벌 | next-intl | 언어 전환 시 라벨 변경 |
| 22 | TODO | Playwright e2e | 회귀 방지 | golden path | list→detail→evidence 통과 |
| 23 | TODO | confidence tooltip(근거 설명) | black-box 점수 방지 | 호버 시 출처수/교차검증 | tooltip 노출 |
| 24 | TODO | saved search / watchlist | retention 엔진 | 사용자별 저장 | 저장 항목 재방문 표시 |
| 25 | TODO | "투자 조언 아님" 면책 배너 | 규제/톤 리스크 | 전역 footer+상세 고지 | 모든 페이지 면책 |
| 26 | RISK | confidence 색상(70/40) 투자신호 오인 | 매수/매도로 읽힘 | 중립 색/라벨 검토 | 색상 가치판단 암시 안 함 |
| 27 | RISK | evidence 출처 누락 시 신뢰 붕괴 | 점수만 근거 없음 | 출처 0개 카드 경고 | 단일/무출처 명시 |
| 28 | RISK | themes/sectors PARTIAL 노출 | 미완성 집계 신뢰 훼손 | "미검증" 라벨 강제 | 라벨 없는 집계 차단 |
| 29 | RISK | comments/ai_replies PARTIAL 노출 | 미완성 UI 역효과 | feature flag 뒤로 | flag off 시 미렌더 |
| 30 | RISK | 외부 링크 rel 누락 | tabnabbing 보안 | rel=noopener noreferrer | 모든 외부 anchor rel |
| 31 | RISK | created_at 타임존 모호 | 실시간 신뢰 저하 | UTC→로컬 명시 | 날짜에 타임존 표시 |
| 32 | RISK | impact_path가 예측처럼 읽힘 | 투자 예측 오인 | "추정 경로, 비예측" 라벨 | impact_path 면책 라벨 |
| 33 | RISK | search 빈 결과 UX 부재 | 이탈 유발 | EmptyState 연결 | 0건 시 안내 |
| 34 | RISK | confidence_score null 처리 | 검색 hit nullable | null→"평가중" | null 시 크래시 없음 |
| 35 | RISK | admin 토큰 클라 유출 | 보안 사고 | server-only 검증 | 번들에 토큰 부재 |
| 36 | COMMERCIAL | alert가 광고보다 현실적 수익 | B2B ARPU | 구독 티어 | 유료 티어 정의 |
| 37 | COMMERCIAL | API 사용량 과금 | 개발자/기업 | 키별 미터링 | 과금 데이터 수집 |
| 38 | COMMERCIAL | report PR/리스크 워크플로 | Meltwater 포지션 | 템플릿 리포트 | 리포트 export |
| 39 | COMMERCIAL | evidence 추적성=세일즈 포인트 | 애널리스트 인용 | 데모에 추적 흐름 | 출처 클릭 데모 |
| 40 | COMMERCIAL | dashboard는 lead-in, 매출 약함 | funnel 상단 | free tier 배치 | 무료→유료 전환 |
| 41 | COMMERCIAL | watchlist=lock-in | 전환비용 | 저장 데이터 축적 | 재방문율 측정 |
| 42 | COMMERCIAL | Dataminr 대비 가격 포지션 | 후발 차별화 | 추적성+저가 진입 | 가격표 정의 |
| 43 | COMMERCIAL | i18n=글로벌 B2B 확장 | 시장 확대 | en 우선 추가 | 영문 데모 |
| 44 | AGENT_HINT | evidence 구조화는 백엔드 계약 선행 | 프론트 단독 불가 | source-ingestion 위임 | evidence 객체 API |
| 45 | AGENT_HINT | alert push 인프라 백엔드 필요 | Celery/Redis 활용 | 백엔드 위임 | 구독 매칭 잡 |
| 46 | AGENT_HINT | API 상품 계약 frontend-integration | 타입 동기화 | OpenAPI 공유 | 타입 일치 |
| 47 | AGENT_HINT | 세그먼트 우선순위 commercialization | 사용자 데이터 | strategist 협업 | 세그먼트 정의 |
| 48 | TODO | golden path: list→detail→evidence→원문 | 핵심 신뢰 흐름 | flow 검증 | e2e 통과 |
| 49 | TODO | edge: 무출처 이벤트 카드 | 추적성 깨짐 경고 | "단일/무출처" 뱃지 | 경고 표시 |
| 50 | TODO | edge: confidence null/0 | 평가 미완 | "평가중" 상태 | null 안전 렌더 |
| 51 | TODO | edge: 재배포 금지 소스 본문 | 라이선스 위반 방지 | snippet-only 강제 | 본문 차단 검증 |
| 52 | TODO | edge: 깨진 출처 링크 | dead link 신뢰 저하 | link health 표기 | 404 출처 라벨 |
| 53 | TODO | edge: 빈 evidence 배열 | 분기 존재 | "근거 수집중" | 빈 배열 시 안내 |
| 54 | TODO | edge: 매우 긴 summary | 레이아웃 깨짐 | line-clamp | 2줄 클램프 |
| 55 | TODO | edge: 다국어 엔티티명 | 깨진 글자 | UTF-8/폰트 확인 | 한/영/CJK 렌더 |
| 56 | TODO | alert 빈도 제어(피로도) | 과알림 이탈 | 묶음/다이제스트 | 빈도 설정 동작 |
| 57 | TODO | alert 채널(email/web/webhook) | 도달 경로 다양화 | 채널 추상화 | 최소 1채널 발송 |
| 58 | TODO | source status 카드 레벨 표기 | 출처 수 가시화 | "검증 N개" microcopy | 출처 수 표시 |
| 59 | TODO | evidence 정렬(날짜/신뢰순) | 최신/핵심 우선 | published_at 정렬 | 정렬 동작 |
| 60 | TODO | confidence 산출 방법론 공개 페이지 | 신뢰 투명성 | /methodology | 페이지 접근 |
| 61 | RISK | 색맹 접근성(녹/황/적만) | 색 단독 의미전달 | 텍스트 라벨 병기 | 색+텍스트 동시 |
| 62 | RISK | alert 오탐(false positive) | 신뢰 훼손 | confidence 임계 게이트 | 저신뢰 alert 억제 |
| 63 | RISK | report 자동집계 오류 | PARTIAL 기반 | 검증 전 draft 표기 | draft 워터마크 |
| 64 | RISK | i18n 미적용 영문 사용자 이탈 | 글로벌 장벽 | 우선순위 백로그 | en 라우트 계획 |
| 65 | RISK | shadcn 미적용 접근성 부채 | a11y 미흡 | 점진 도입 | 키보드 네비 |
| 66 | RISK | API 무인증 노출 | 데이터 유출 | 키 인증 필수 | 무키 401 |
| 67 | RISK | created_at 미래/과거 이상치 | 데이터 신뢰 | 범위 검증 표기 | 이상 날짜 플래그 |
| 68 | COMMERCIAL | free→alert 전환 funnel | 핵심 수익 경로 | upgrade CTA | 전환율 추적 |
| 69 | COMMERCIAL | enterprise SSO/감사로그 | 대기업 요건 | 백로그 | 요건 정의 |
| 70 | COMMERCIAL | evidence export(인용용) | 애널리스트 워크플로 | CSV/링크 export | 출처 포함 export |
| 71 | AGENT_HINT | confidence 방법론 백엔드 정의 | 점수 신뢰 | 엔지니어 위임 | 산출식 문서화 |
| 72 | AGENT_HINT | source_license 메타 백엔드 | 라이선스 차단 | 수집 단계 태깅 | license 필드 |
| 73 | AGENT_HINT | link health 체크 잡 | dead link 탐지 | 주기 검사 잡 | 상태 필드 갱신 |
| 74 | TODO | "정보제공, 투자조언 아님" 상세 고지 | 규제 톤 준수 | impact_path 인접 고지 | 고지 문구 노출 |
| 75 | TODO | 가치판단 표현 필터("사라/팔라") | 정책 | 출력 후처리 | 금지 표현 부재 |
| 76 | TODO | onboarding 첫 화면 가이드 | 신규 이해도 | 3스텝 안내 | 첫 방문 가이드 |
| 77 | TODO | event card hover 미리보기 | 탐색 효율 | summary 확장 | 호버 시 확장 |
| 78 | TODO | 키보드 접근성(Link focus) | a11y | focus ring | tab 네비 |
| 79 | TODO | 모바일 반응형 검증 | 멀티 디바이스 | breakpoint 점검 | 모바일 레이아웃 |
| 80 | TODO | dark/light 테마 | 사용자 선호 | dark 고정→토글 | 테마 전환 |
| 81 | RISK | snippet 길이 라이선스 한계 | 과인용 위험 | 길이 캡 | snippet 글자수 제한 |
| 82 | RISK | alert 미발송 silent fail | 신뢰 붕괴 | 발송 로그/재시도 | 실패 로깅 |
| 83 | RISK | search relevance 낮음 | 발견성 저하 | score 노출/튜닝 | 상위 hit 관련성 |
| 84 | RISK | entities 미연결(링크 없음) | 탐색 단절 | 엔티티→필터 연결 | 엔티티 클릭 동작 |
| 85 | RISK | theme/sector 명명 불일치 | 혼란 | 표준 라벨 매핑 | 일관 라벨 |
| 86 | COMMERCIAL | 가격 티어(free/pro/enterprise) | 수익 구조 | 3티어 정의 | 티어별 기능 구분 |
| 87 | COMMERCIAL | trial 기간 alert 체험 | 전환 유도 | 14일 trial | trial 발송 |
| 88 | COMMERCIAL | webhook=개발자 lock-in | 통합 비용 | webhook 상품화 | webhook 발송 |
| 89 | AGENT_HINT | retention 지표 정의 commercialization | 측정 기준 | strategist 위임 | DAU/재방문 정의 |
| 90 | AGENT_HINT | alert UX→frontend-integration 계약 | 구독 API | 타입 공유 | 구독 API 계약 |
| 91 | TODO | empty/error 상태 일관화 | 견고한 UX | EmptyState/ErrorState 재사용 | 전 라우트 적용 |
| 92 | TODO | confidence 정렬/필터 옵션 | 신뢰순 탐색 | 정렬 컨트롤 | 신뢰순 정렬 |
| 93 | TODO | 출처 다양성 지표(교차검증) | 신뢰 강화 | "N개 독립 출처" | 출처 수 집계 |
| 94 | TODO | 타임라인 뷰(사건 전개) | 맥락 제공 | created_at 시계열 | 타임라인 렌더 |
| 95 | TODO | watchlist 알림 연동 | retention+alert 결합 | 저장→alert 규칙 | 저장 항목 alert |
| 96 | RISK | community(comments) 스팸/모더레이션 | 품질 저하 | flag 뒤 보류 | MVP 제외 |
| 97 | RISK | ai_replies 환각 책임 | 신뢰/규제 | 출처 강제+면책 | 근거 없는 reply 차단 |
| 98 | COMMERCIAL | community=후순위 retention 옵션 | 데이터 부족 단정불가 | 세그먼트 검증 후 | UNKNOWN, 데이터 대기 |
| 99 | AGENT_HINT | shadcn/i18n/e2e는 frontend 위임 | 구현 영역 | frontend-integration | 구현 완료 |
| 100 | AGENT_HINT | 전체 attribution 정책 commercialization+legal | 라이선스 리스크 | strategist+법무 | attribution 정책 승인 |

**완전 달성 기준:** evidence가 {source_name,url,published_at,snippet,source_status} 구조 승격되어 모든 카드/detail에서 출처명+발행일+원문링크 표시(재배포 금지 소스 snippet-only), confidence가 근거 추적 tooltip+가치판단 없는 중립 표기, golden path Playwright e2e 검증, alert 1순위 정의, PARTIAL(themes/sectors=미검증 라벨, comments/ai_replies=flag 차단) 신뢰 훼손 없음, 모든 페이지 면책 노출.

## L14. Commercialization / pricing / GTM / vertical strategy — 100 Insights

| No | Type | Insight / Checklist | Why it matters | Implementation direction | Acceptance criteria |
|---:|---|---|---|---|---|
| 1 | COMMERCIAL | 1차 ICP: AI/SaaS 제품팀·PM·DevRel | 구체 타겟 필수 | 경쟁/제품 incident 모니터 | ICP 1문장 정의 |
| 2 | COMMERCIAL | 세그먼트표: ICP/문제/WTP/채널 | GTM 기반 | 표 작성 | 4열 세그먼트표 |
| 3 | COMMERCIAL | AI팀 문제=경쟁·자사 제품 incident 추적 | WTP 근거 | incident vertical 매핑 | 문제 진술 검증 |
| 4 | COMMERCIAL | AI팀 WTP=팀당 월 $X(중간) | 가격 가설 | 인터뷰로 확정 | WTP 범위 산정 |
| 5 | COMMERCIAL | AI팀 채널=HN/ProductHunt/뉴스레터 | 저CAC | 커뮤니티 런칭 | 채널별 가입 |
| 6 | COMMERCIAL | 금융 세그먼트: 리서치/IR(Phase2) | 최고 WTP | sec/opendart 연결 후 | Phase2 세그먼트 정의 |
| 7 | COMMERCIAL | 규제 세그먼트: compliance팀(Phase2) | 낮은 법적리스크 | federal_register 상품화 | 규제 세그먼트 정의 |
| 8 | COMMERCIAL | Free 티어: 기본 피드+제한 alert | 획득 깔때기 | freemium 경계 | Free 기능 분리 |
| 9 | COMMERCIAL | Pro 티어: 무제한 alert+evidence 심층 | 개인/소팀 | $/seat 기본 | Pro 가격 책정 |
| 10 | COMMERCIAL | Team 티어: 다인+공유+섹터필터 | 팀 단위 | seat+usage | Team 가격 책정 |
| 11 | COMMERCIAL | Enterprise: API+custom+SLA | 대형 딜 | custom 견적 | 엔터 트랙 정의 |
| 12 | COMMERCIAL | hybrid 과금: base seat+alert/API usage | 시장 61% hybrid | usage 미터 구현 | 미터 정의 |
| 13 | COMMERCIAL | usage 단위=alert 발송/API콜/레코드 | seat 무력화 대응 | 미터링 설계 | 과금 단위 확정 |
| 14 | RISK | 순수 per-seat 회피(시장 15%↓) | 가격 경쟁력 | hybrid 채택 | seat-only 가격표 폐기 |
| 15 | COMMERCIAL | 진입가는 경쟁 최저가 이하 | underdog 침투 | SMB 가격대 | 경쟁 가격 비교표 |
| 16 | COMMERCIAL | Dataminr=엔터 seat+add-on 참조 | 가격 구조 벤치 | add-on 모델 차용 | 구조 비교 |
| 17 | COMMERCIAL | AlphaSense=Standard/Premium/Enterprise | 3티어 벤치 | 티어 구조 차용 | 티어 매핑 |
| 18 | RISK | 경쟁 분석 없는 가격 책정 금지 | 실패 조건 | 5개 경쟁사 매핑 | 경쟁 가격표 |
| 19 | COMMERCIAL | 차별점1=다중소스 교차검증 | 단일소스 우위 | 3층 카드 | 차별 명문화 |
| 20 | COMMERCIAL | 차별점2=증거체인 evidence link | 신뢰+저작권안전 | evidence_links | 차별 명문화 |
| 21 | COMMERCIAL | 차별점3=사건중심 능동감지 | 검색엔진 대비 | event queue | 차별 명문화 |
| 22 | COMMERCIAL | 차별점4=정보제공 규제안전 | 조달 통과 | 투자조언 0 | 차별 명문화 |
| 23 | COMMERCIAL | 수익화1=alert 구독(B2C/팀) | 경로1 | 구독 결제 | 경로 정의 |
| 24 | COMMERCIAL | 수익화2=B2B event queue API | 경로2 | API rate plan | 경로 정의 |
| 25 | COMMERCIAL | 수익화3=정기 리포트 구독 | 경로3 | 자동 리포트 | 경로 정의 |
| 26 | TODO | M1: P0 브리지+단일 vertical 큐 라이브 | 데모 선결 | A→B 배선 | 라이브 큐 동작 |
| 27 | TODO | M1: AI incident vertical 소스셋 확정 | 초점 | 6소스 활성 | 소스셋 문서 |
| 28 | TODO | M1: ICP 인터뷰 5건 | WTP 검증 | 고객 접촉 | 인터뷰 완료 |
| 29 | TODO | M2: 랜딩+무료티어 가입 오픈 | 깔때기 가동 | freemium 출시 | 가입 ≥N |
| 30 | TODO | M2: HN/ProductHunt 런칭 | 저CAC 획득 | 커뮤니티 런칭 | 런칭 트래픽 |
| 31 | TODO | M2: alert 구독 결제 베타 | 수익화1 검증 | 결제 연동 | 첫 유료 가입 |
| 32 | TODO | M3: 파일럿 3곳 LOI | B2B 검증 | 영업 개시 | LOI ≥3 |
| 33 | TODO | M3: evidence 심층 premium 출시 | upsell | 모순분석 | premium 전환 |
| 34 | TODO | M4: B2B API 베타 | 수익화2 | API 계약 | API 첫 고객 |
| 35 | TODO | M4: 케이스스터디 1건 | 레퍼런스 | 파일럿 성과화 | 케이스스터디 게시 |
| 36 | TODO | M5: 금융 vertical 확장 검토 | Phase2 진입 | sec/opendart 평가 | 확장 결정 |
| 37 | TODO | M5: 정기 리포트 구독 출시 | 수익화3 | 자동 리포트 | 리포트 첫 구독 |
| 38 | TODO | M6: 가격 최적화+티어 재조정 | 마진 개선 | 가격 실험 반영 | 신가격표 |
| 39 | TODO | M6: 6개월 KPI 리뷰 | 검증 종료 | MRR/전환/churn | KPI 리포트 |
| 40 | RISK | 브리지 전 영업 시작 금지 | 공허한 데모 | M1 후 영업 | 데모 선결 |
| 41 | RISK | 다vertical 동시 출시 금지 | 초점 분산 | M1=1 vertical | 단일 vertical |
| 42 | COMMERCIAL | 파일럿=저가/무료+케이스스터디 교환 | 레퍼런스 확보 | 파일럿 계약 | 케이스스터디 권리 |
| 43 | COMMERCIAL | activation=첫 의미있는 alert | retention 시작 | seed 키워드 추천 | TTV 단축 |
| 44 | COMMERCIAL | retention=큐 신선도+alert 정확도 | LTV | 신선도 SLA | churn 측정 |
| 45 | RISK | false alert가 최대 churn 원인 | 신뢰 붕괴 | evidence 게이트 | false rate 상한 |
| 46 | COMMERCIAL | upsell 트리거=alert 한도 초과 | Free→Pro | 한도 게이팅 | 전환율 |
| 47 | COMMERCIAL | expansion=seat 추가+섹터 확장 | NRR | Team upsell | expansion 매출 |
| 48 | COMMERCIAL | Dataminr 약점공략: 가격 접근성 | 침투 | SMB 가격 | 경쟁 약점표 |
| 49 | COMMERCIAL | AlphaSense 대비: 능동 alert | 차별 | 감지 latency | 대비 메시지 |
| 50 | COMMERCIAL | Recorded Future 대비: 범용 incident | 사이버 특화 회피 | vertical 폭 | 대비 메시지 |
| 51 | COMMERCIAL | Meltwater/Talkwalker 대비: 증거검증 | PR모니터 대비 | evidence 라벨 | 대비 메시지 |
| 52 | COMMERCIAL | Liveuamap 대비: 검증+요약 | OSINT 차별 | 검증 라벨 | 대비 메시지 |
| 53 | COMMERCIAL | Perplexity 대비: 능동감지 vs 질의 | 검색 차별 | event 스트림 | 대비 메시지 |
| 54 | COMMERCIAL | 국내 뉴스포털 대비: 교차검증+공식 | 단일소스 대비 | 3층 구조 | 대비 메시지 |
| 55 | RISK | google_trends/x 의존 GTM 금지 | 정책 차단 소스 | 가용 소스만 약속 | 차단소스 약속 0 |
| 56 | COMMERCIAL | TAM=bottom-up(ICP수×ARPU) | 근거 있는 추정 | SOM 산식 | TAM 출처 명시 |
| 57 | RISK | top-down 막연 TAM 금지 | 실패 조건 | bottom-up only | 산식 검증 |
| 58 | COMMERCIAL | SOM 1차=AI/tech 제품팀 도달 가능수 | 현실 시장 | bottom-up | SOM 문서 |
| 59 | COMMERCIAL | CAC=커뮤니티 런칭으로 최소화 | 마진 | HN/PH organic | CAC 측정 |
| 60 | COMMERCIAL | LTV/CAC≥3 목표 | 지속성 | 단가×retention | 비율 측정 |
| 61 | RISK | LLM 비용>alert 단가 역마진 | 적자 | 게이트 입력절감 | 사건당 비용 상한 |
| 62 | COMMERCIAL | 무료소스(NewsData.io 등) 우선 | 마진 방어 | 무료티어 소스 | 무료소스 비율 |
| 63 | COMMERCIAL | quota guard로 최악비용 상한 | 가격 설계 | 일일 quota 산정 | 가격>비용 |
| 64 | COMMERCIAL | enterprise SLA=가격 프리미엄 | 마진 | uptime 보장 | SLA 가격 |
| 65 | COMMERCIAL | API 과금=콜/레코드 미터 | usage 모델 | 미터링 | API 가격표 |
| 66 | COMMERCIAL | 리포트=주간 vertical 요약 구독 | recurring | 자동 생성 | 리포트 구독 |
| 67 | RISK | 전재 금지=리포트는 요약+링크만 | 저작권 | evidence 중심 | 원문 0 |
| 68 | COMMERCIAL | 저작권 안전이 엔터 조달 통과 | B2B 판매성 | legal 문서화 | 조달 통과 |
| 69 | COMMERCIAL | 정보제공 포지션=금융 vertical 가능 | 규제 회피 | 투자조언 0 | 톤 검사 |
| 70 | RISK | 금융 alert의 투자조언화 위험 | 규제 | 가치판단 제거 | 출력 검수 |
| 71 | COMMERCIAL | 규제 vertical=느리지만 고정 수요 | 안정 매출 | compliance 타겟 | 세일즈 사이클 가정 |
| 72 | COMMERCIAL | media vertical=brand risk 알림 | 추가 시장 | dcinside 반응+뉴스 | 상품 후보 검증 |
| 73 | RISK | media vertical 명예훼손 리스크 | 평판/법적 | 사실 라벨 강제 | unconfirmed 처리 |
| 74 | COMMERCIAL | 핵심 카피="먼저+믿을수있게" | 포지셔닝 | 헤드라인 | 메시지 합의 |
| 75 | COMMERCIAL | 포지션=event intelligence(검색 아님) | 카테고리 정의 | alert/stream 언어 | 메시징 일관성 |
| 76 | TODO | 경쟁 포지셔닝 맵(가격×깊이) | 위치 명확 | 2축 매핑 | 맵 1장 |
| 77 | TODO | 가격 민감도 실험(Van Westendorp) | 가격 확정 | 인터뷰 설계 | 가격 인터뷰 |
| 78 | COMMERCIAL | 무료→유료 전환율 목표 설정 | 깔때기 KPI | 전환 추적 | 전환율 목표 |
| 79 | COMMERCIAL | NRR>100% 목표(expansion) | SaaS 건전성 | upsell 설계 | NRR 측정 |
| 80 | RISK | churn 미측정시 LTV 과대 | 마진 착시 | churn 추적 | churn 대시보드 |
| 81 | COMMERCIAL | 첫 100 유료고객=AI vertical 집중 | beachhead | 단일 vertical | 100 고객 도달 |
| 82 | COMMERCIAL | beachhead 후 인접 vertical 확장 | 단계적 성장 | 금융/규제 순 | 확장 순서 |
| 83 | AGENT_HINT | Layer3 deep agent=research premium | 부가가치 | 매출 후 추가 | MVP 제외 |
| 84 | COMMERCIAL | research assistant=enterprise add-on | 고단가 | agent 계층 | add-on 가격 |
| 85 | RISK | premium agent를 MVP 비용에 넣기 금지 | 출시 지연 | 매출 검증 후 | MVP 제외 확인 |
| 86 | TODO | onboarding 키워드 추천 설계 | activation | seed 추천 | TTV 측정 |
| 87 | COMMERCIAL | 신뢰 라벨이 유료 정당화 | 가격 근거 | official 라벨 | 라벨 가치 검증 |
| 88 | COMMERCIAL | alert 정확도=핵심 품질 지표 | retention | evidence 게이트 | 정확도 측정 |
| 89 | RISK | 가용소스 46 기준 계획(57 아님) | 과대평가 금지 | READY46 | 계획 기준 확인 |
| 90 | TODO | KPI: MRR/파일럿/전환/churn/TTV | 검증 기준 | 대시보드 | KPI 정의 |
| 91 | COMMERCIAL | 6개월 목표=파일럿3+유료30+MRR검증 | 현실적 KPI | 단계 목표 | 목표 합의 |
| 92 | RISK | "돈 번다" 마케팅 금지 | 정책 | 정보가치 소구 | 카피 검수 |
| 93 | COMMERCIAL | 경쟁차별 종합 4축 메시지 | 포지셔닝 | 가격+검증+감지+범용 | 4축 합의 |
| 94 | TODO | adversarial-reality-critic 가설 의뢰 | 리스크 차단 | 가설 목록 | 회신 수령 |
| 95 | TODO | product-ux-strategist UX 연계 | 일관성 | onboarding/카드 UX | UX 핸드오프 |
| 96 | TODO | business-intelligence-analyst 시장데이터 | 인사이트 | vertical 시장 분석 | 데이터 요청 |
| 97 | COMMERCIAL | 결제/구독 인프라 선택(Stripe 등) | 수익화 인프라 | 결제 연동 | 결제 동작 |
| 98 | RISK | 결제 전 무료만 운영시 매출 0 | 검증 불가 | M2 결제 오픈 | 첫 매출 |
| 99 | COMMERCIAL | 분기 가격 재검토 루틴 | 가격 진화 | 정기 리뷰 | 리뷰 캐던스 |
| 100 | COMMERCIAL | 최종 GTM=beachhead→인접확장→API | 성장 경로 | 단계 실행 | 경로 합의 |

**완전 달성 기준:** 6개월 내 P0 해소→AI/tech incident vertical 라이브 큐→freemium→유료 전환(alert 구독)→파일럿 LOI 3+→API 베타까지 도달, 경쟁 5사 대비 차별 4축과 hybrid 3-4티어 가격표가 bottom-up SOM 근거와 함께 확정, false alert rate·churn·LTV/CAC가 측정 가능한 KPI로 추적.

---

## 집계 (총 1500항목)

| Layer | 항목 | 주요 Type 분포(개요) |
|---|---:|---|
| L0 Product thesis | 100 | COMMERCIAL/RISK 중심, IMPLEMENTED 7 |
| L1 Source discovery | 100 | IMPLEMENTED 40 + TODO/RISK/AGENT_HINT |
| L2 Search expansion | 100 | TODO/RISK 중심(미구현 layer) |
| L3 Policy-safe fetch | 100 | IMPLEMENTED/POLICY 다수 |
| L4 EventQueue/Redis | 100 | IMPLEMENTED(B)+TODO(A 배선) |
| L5 Storage/indexing | 100 | IMPLEMENTED 12 + TODO |
| L6 RAG/rerank | 100 | IMPLEMENTED 4 + TODO |
| L7 KG-RAG | 100 | 거의 TODO/RISK(미구현) |
| L8 Clustering/rank | 100 | PARTIAL+TODO 중심 |
| L9 Supervisor/judge | 100 | IMPLEMENTED 다수 + TODO |
| L10 Orchestration | 100 | IMPLEMENTED 다수 + TODO |
| L11 Safety/legal | 100 | POLICY/IMPLEMENTED/TODO |
| L12 Monitoring | 100 | IMPLEMENTED+TODO |
| L13 Product surface | 100 | IMPLEMENTED 10 + TODO |
| L14 Commercialization | 100 | COMMERCIAL/TODO 중심 |
| **합계** | **1500** | IMPLEMENTED는 전부 코드 열람 근거 |

> 각 항목의 IMPLEMENTED 표기는 실제 코드 열람으로 검증됐다(파일 경로는 01·05~12 참조). 미구현은 TODO, 위험은 RISK, 정책 불변은 POLICY, 상업 직접영향은 COMMERCIAL, LLM 에이전트 활용은 AGENT_HINT로 표기했다.
