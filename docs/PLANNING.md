# Sky Scanner - 기획 문서

> 전세계 주요 항공사 사이트를 크롤링하여 스카이스캐너보다 저렴한 항공권을 찾아주는 개인화 항공권 검색 서비스

## 1. 프로젝트 개요

### 1.1 비전

기존 메타서치 엔진(Skyscanner, Google Flights, Kayak)은 GDS/OTA 데이터에 의존하며, 항공사 직접 판매 가격이나 LCC 프로모션을 놓치는 경우가 많다. Sky Scanner는 항공사 웹사이트를 **직접 크롤링**하여 GDS에 노출되지 않는 숨겨진 저가 항공권까지 찾아내고, 단순 가격 비교를 넘어 **개인화된 조건**(좌석 넓이, 비행 시간대, 수하물 등)까지 반영한 최적의 항공권을 추천한다.

### 1.2 핵심 차별점

| 기존 서비스 | Sky Scanner |
|---|---|
| GDS/OTA 가격만 비교 | 항공사 직접 가격 크롤링 포함 |
| 가격 중심 정렬 | 개인화 조건 기반 최적화 |
| 고정된 검색 필터 | AI 기반 자연어 조건 입력 |
| 단순 가격 알림 | 최적 구매 타이밍 예측 |
| 동일 경로만 비교 | 대안 공항/경유지 자동 탐색 |

### 1.3 팀 역할

| 역할 | 담당 | 범위 |
|---|---|---|
| **Dev (Perry)** | 크롤링 로직, 인프라, 전체 서비스 개발 | 크롤러 엔진, API 서버, DB, 캐싱, 프론트엔드, 배포 |
| **DA (Data Analyst)** | 데이터 분석 기반 최적 알고리즘 탐색 | 가격 예측 모델, 최적 구매 시점 분석, 경로 최적화, 개인화 추천 알고리즘 |

---

## 2. 크롤링 대상 항공사 (60+)

### 2.1 데이터 소스 레이어 범례

```
L1 = Google Flights Protobuf (브라우저 없이 초고속)
L2 = Kiwi.com Tequila API (800+ 항공사, Google 누락분 커버)
L3 = 항공사 직접 크롤링 Playwright (어디에도 없는 항공사 + 직접 프로모션)
```

### 2.2 지역별 주요 항공사

#### 아시아-태평양

**동아시아 (풀서비스)**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| ANA (전일본공수) | ana.co.jp | 일본 | L1+L3 | Star Alliance, 34인치 피치 |
| JAL (일본항공) | jal.co.jp | 일본 | L1+L3 | Oneworld |
| 대한항공 | koreanair.com | 한국 | L1+L3 | SkyTeam |
| 아시아나항공 | flyasiana.com | 한국 | L1+L3 | Star Alliance |
| 중국국제항공 | airchina.com | 중국 | **L2+L3** | Star Alliance, **Google 누락** |
| 중국동방항공 | ceair.com | 중국 | **L2+L3** | SkyTeam, **Google 누락**, 일 2,473편 |
| 중국남방항공 | csair.com | 중국 | L1+L2 | 일 2,341편 |
| 캐세이퍼시픽 | cathaypacific.com | 홍콩 | L1 | Oneworld |

**동아시아 (LCC)**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 제주항공 | jejuair.net | 한국 | L1+L2 | |
| 티웨이항공 | twayair.com | 한국 | L1+L2 | |
| 진에어 | jinair.com | 한국 | L1+L2 | |
| 에어서울 | flyairseoul.com | 한국 | L2+L3 | |
| 피치항공 | flypeach.com | 일본 | **L2+L3** | **Google 누락 가능** |
| 춘추항공 | springairlines.com | 중국 | **L2+L3** | **Google 누락** |

**동남아시아**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 싱가포르항공 | singaporeair.com | 싱가포르 | L1 | 최고 평점, 34인치 피치 |
| 타이항공 | thaiairways.com | 태국 | **L2+L3** | Star Alliance, **Google 일부 누락** |
| 말레이시아항공 | malaysiaairlines.com | 말레이시아 | L1 | Oneworld |
| 베트남항공 | vietnamairlines.com | 베트남 | L1+L2 | SkyTeam |
| 가루다인도네시아 | garuda-indonesia.com | 인도네시아 | L1+L2 | SkyTeam |
| 필리핀항공 | philippineairlines.com | 필리핀 | **L2+L3** | **Google 누락** |
| 에어아시아 | airasia.com | 말레이시아 | **L2+L3** | LCC 1위, **Google 제한적** |
| 스쿠트 | flyscoot.com | 싱가포르 | L1+L2 | LCC |
| 비엣젯 | vietjetair.com | 베트남 | **L2+L3** | LCC, **Google 누락** |
| 세부퍼시픽 | cebupacificair.com | 필리핀 | L2 | LCC |

**남아시아**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 에어인디아 | airindia.com | 인도 | L1 | Star Alliance |
| IndiGo | goindigo.in | 인도 | **L2+L3** | 인도 국내 64% 점유율, **Google 제한적** |
| SpiceJet | spicejet.com | 인도 | L2 | LCC |

**오세아니아**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 콴타스 | qantas.com | 호주 | L1 | Oneworld |
| 버진오스트레일리아 | virginaustralia.com | 호주 | L1 | |
| 에어뉴질랜드 | airnewzealand.com | 뉴질랜드 | L1 | Star Alliance |

#### 유럽

**풀서비스**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 루프트한자 | lufthansa.com | 독일 | L1 | Star Alliance |
| 브리티시에어웨이즈 | britishairways.com | 영국 | L1 | Oneworld |
| 에어프랑스 | airfrance.com | 프랑스 | L1 | SkyTeam |
| KLM | klm.com | 네덜란드 | L1 | SkyTeam |
| 이베리아 | iberia.com | 스페인 | L1 | Oneworld |
| 터키항공 | turkishairlines.com | 튀르키예 | L1 | Star Alliance |
| TAP포르투갈 | flytap.com | 포르투갈 | L1 | Star Alliance |
| 에게안항공 | aegeanair.com | 그리스 | L1 | Star Alliance |
| 핀에어 | finnair.com | 핀란드 | L1 | Oneworld |
| SAS | flysas.com | 스웨덴 | L1 | SkyTeam |
| ITA항공 | ita-airways.com | 이탈리아 | L1 | SkyTeam |

**LCC**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 라이언에어 | ryanair.com | 아일랜드 | L1+L2 | 유럽 최대 LCC, 일 2,523편 |
| 이지젯 | easyjet.com | 영국 | L1+L2 | 유럽 2위 LCC |
| 위즈에어 | wizzair.com | 헝가리 | **L2+L3** | 62M 승객, **Google 누락** |
| 노르웨이에어 | norwegian.com | 노르웨이 | L1+L2 | |
| 부엘링 | vueling.com | 스페인 | **L2+L3** | 38M 승객, **Google 누락** |
| 트랜사비아 | transavia.com | 네덜란드 | **L2+L3** | 23M 승객, **Google 누락** |
| 유로윙스 | eurowings.com | 독일 | L1+L2 | |

#### 아메리카

**북미**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 아메리칸항공 | aa.com | 미국 | L1 | Oneworld, 일 4,563편 |
| 델타항공 | delta.com | 미국 | L1 | SkyTeam |
| 유나이티드항공 | united.com | 미국 | L1 | Star Alliance |
| 사우스웨스트 | southwest.com | 미국 | L1+L3 | LCC, 2024년 Google 진입, 직접 예매만 |
| 제트블루 | jetblue.com | 미국 | L1 | 32-34인치 피치 |
| 스피릿항공 | spirit.com | 미국 | L1+L2 | ULCC, 가격 불완전 |
| 프론티어항공 | flyfrontier.com | 미국 | L1+L2 | ULCC, NDC 전환 중 |
| 알래스카항공 | alaskaair.com | 미국 | L1 | Oneworld |
| Allegiant | allegiantair.com | 미국 | **L3 전용** | **어디에도 없음, 직접 크롤링 필수** |
| Avelo | aveloair.com | 미국 | **L3 전용** | **어디에도 없음** |
| Breeze | flybreeze.com | 미국 | **L3 전용** | **어디에도 없음** |
| 에어캐나다 | aircanada.com | 캐나다 | L1 | Star Alliance |
| 웨스트젯 | westjet.com | 캐나다 | L1 | |

**중남미**
| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| LATAM항공 | latamairlines.com | 칠레/브라질 | L1 | |
| 아비앙카 | avianca.com | 콜롬비아 | L1 | Star Alliance |
| 아에로멕시코 | aeromexico.com | 멕시코 | L1 | SkyTeam |
| 코파항공 | copaair.com | 파나마 | L1 | Star Alliance |
| 볼라리스 | volaris.com | 멕시코 | **L3 전용** | **Google에서 가격 철수** |
| JetSMART | jetsmart.com | 칠레 | **L2+L3** | **Google 누락** |
| GOL | voegol.com.br | 브라질 | L1+L2 | LCC |
| 아줄 | voeazul.com.br | 브라질 | L1+L2 | |

#### 중동

| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 에미레이트 | emirates.com | UAE | L1 | 34인치 이코노미 피치 |
| 카타르항공 | qatarairways.com | 카타르 | L1 | 글로벌 1위 평점 |
| 에티하드항공 | etihad.com | UAE | L1 | |
| 사우디아 | saudia.com | 사우디 | L1 | SkyTeam |
| 플라이두바이 | flydubai.com | UAE | L1+L2 | LCC |
| 에어아라비아 | airarabia.com | UAE | L2 | LCC |

#### 아프리카

| 항공사 | URL | 국가 | 소스 | 비고 |
|---|---|---|---|---|
| 에티오피아항공 | ethiopianairlines.com | 에티오피아 | L1 | Star Alliance, 아프리카 1위 |
| 남아프리카항공 | flysaa.com | 남아프리카 | L1+L2 | Star Alliance |
| 케냐항공 | kenya-airways.com | 케냐 | L1+L2 | SkyTeam |
| 이집트에어 | egyptair.com | 이집트 | L1 | Star Alliance |
| 로열에어모로코 | royalairmaroc.com | 모로코 | L1 | Oneworld |

---

## 3. 시스템 아키텍처

### 3.1 전체 구성도

```
┌─────────────────────────────────────────────────────────────────────┐
│                         사용자 인터페이스                              │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ 웹 앱    │  │ 모바일 (PWA) │  │ API Client  │  │ 알림 (Push) │  │
│  └────┬─────┘  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘  │
└───────┼───────────────┼────────────────┼────────────────┼──────────┘
        └───────────────┴────────────────┴────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │    API Gateway         │
                    │  (Rate Limit, Auth)    │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────┴───────┐   ┌──────────┴──────────┐   ┌───────┴────────┐
│ Search Service│   │ User Service        │   │ Alert Service  │
│ (검색/필터)   │   │ (인증/개인화 조건)  │   │ (가격 알림)    │
└───────┬───────┘   └──────────┬──────────┘   └───────┬────────┘
        │                      │                       │
        └──────────────────────┼───────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │   Data Layer        │
                    │  ┌────────────────┐ │
                    │  │ Redis Cache    │ │  ← L1: 핫 데이터 (TTL 5-15분)
                    │  │ (가격/좌석)    │ │
                    │  └────────────────┘ │
                    │  ┌────────────────┐ │
                    │  │ PostgreSQL     │ │  ← 항공편/가격 이력/사용자
                    │  │ (Main DB)      │ │
                    │  └────────────────┘ │
                    │  ┌────────────────┐ │
                    │  │ Elasticsearch  │ │  ← 검색 인덱스/자연어 쿼리
                    │  │ (Search)       │ │
                    │  └────────────────┘ │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌──────────────────────────────┐ ┌────────┴────────┐ ┌───────────┴──────────┐
│ 4-Layer Crawler Engine       │ │ DA Pipeline     │ │ Scheduler            │
│ (병렬 수집 엔진)             │ │ (분석 파이프라인)│ │ (크롤링 스케줄러)    │
│                              │ │                 │ │                      │
│ ┌──────────────────────────┐ │ │ ┌─────────────┐│ │ ┌──────────────────┐ │
│ │ L1: Google Flights       │ │ │ │ 가격 예측   ││ │ │ L1+L2: 5-15분    │ │
│ │     (Protobuf + primp)   │ │ │ │ 모델       ││ │ │ L3: 1-6시간      │ │
│ ├──────────────────────────┤ │ │ ├─────────────┤│ │ │ On-demand: 실시간│ │
│ │ L2: Kiwi.com Tequila API │ │ │ │ 경로 최적화 ││ │ └──────────────────┘ │
│ │     (REST, 800+ 항공사)  │ │ │ │ 알고리즘   ││ │                      │
│ ├──────────────────────────┤ │ │ ├─────────────┤│ └──────────────────────┘
│ │ L3: 항공사 직접 크롤링   │ │ │ │ 개인화     ││
│ │     (Playwright+Stealth) │ │ │ │ 추천 엔진  ││
│ ├──────────────────────────┤ │ │ └─────────────┘│
│ │ Data Merger              │ │ └────────────────┘
│ │ (중복제거, 정규화, 최저가)│ │
│ ├──────────────────────────┤ │
│ │ Proxy Pool (L3 전용)     │ │
│ └──────────────────────────┘ │
└──────────────────────────────┘
```

### 3.2 기술 스택

| 계층 | 기술 | 선정 이유 |
|---|---|---|
| **크롤러 L1** | Google Flights Protobuf + primp | 브라우저 없이 초고속 수집 (fast-flights 방식) |
| **크롤러 L2** | Kiwi.com Tequila API | Google에 없는 LCC/중국 항공사 커버 (800+) |
| **크롤러 L3** | Playwright (Python) | 직접 예매 전용 항공사 크롤링, 안티봇 우회 |
| **크롤러 L4** | Scrapy | 정적 데이터 대량 수집, 좌석 스펙 등 |
| **프록시** | Residential Proxy Pool | 안티봇 우회 필수 (L3용) |
| **태스크 큐** | Redis + Celery (또는 BullMQ) | 분산 크롤링 작업 관리 |
| **메시지 큐** | Kafka (또는 RabbitMQ) | 크롤링 결과 스트리밍 |
| **API 서버** | FastAPI (Python) | 비동기, 고성능, 타입 안전 |
| **DB** | PostgreSQL | 관계형 데이터, 가격 이력 |
| **캐시** | Redis | L1 캐시, 세션, 실시간 데이터 |
| **검색 엔진** | Elasticsearch | 항공편 검색, 자연어 쿼리 |
| **프론트엔드** | Next.js + TypeScript | SSR, SEO, 모던 UI |
| **인프라** | Docker + K8s (또는 ECS) | 컨테이너 오케스트레이션, 스케일링 |
| **모니터링** | Prometheus + Grafana | 크롤러 상태, API 메트릭 |
| **DA 환경** | Jupyter + Pandas + scikit-learn + PyTorch | 분석/모델링 |

### 3.3 크롤러 엔진 상세 — 4-Layer 병렬 수집

#### 데이터 소스별 커버리지 문제

Google Flights에는 다음 항공사 데이터가 **없거나 불완전**하다:

| 카테고리 | 누락 항공사 | 연간 승객 규모 | 대안 소스 |
|---|---|---|---|
| **중국 빅3 중 2개** | 중국국제항공, 중국동방항공 | 수억 명 | L2 (Kiwi API) + L3 (직접 크롤링) |
| **유럽 LCC** | 부엘링(38M), 트랜사비아(23M), 위즈에어(62M) | 1.2억+ | L2 (Kiwi API) |
| **미국 ULCC** | Allegiant, Avelo, Breeze | - | L3 (직접 크롤링 필수) |
| **동남아 LCC** | 비엣젯, 필리핀항공 | - | L2 (Kiwi API) + L3 |
| **중남미** | 볼라리스, JetSMART | - | L3 (직접 크롤링 필수) |
| **기타** | 타이항공(일부), IndiGo(일부) | - | L2 보완 |

> **결론:** 단일 소스로는 전세계를 커버할 수 없다. 4개 레이어를 **병렬로** 운영해야 한다.

#### 4-Layer 병렬 수집 아키텍처

```
                        ┌─────────────────┐
                        │   Scheduler     │
                        │  (노선별 최적   │
                        │   소스 라우팅)   │
                        └────────┬────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
    ┌────────────┴──┐  ┌────────┴────────┐  ┌───┴────────────┐
    │  L1: Google   │  │  L2: Kiwi.com   │  │  L3: 항공사    │
    │  Flights      │  │  Tequila API    │  │  직접 크롤링    │
    │  (Protobuf)   │  │  (REST API)     │  │  (Playwright)  │
    │               │  │                 │  │                │
    │ • 주요 FSC    │  │ • Google 누락   │  │ • 직접예매 전용 │
    │ • 일부 LCC    │  │   LCC 커버      │  │   항공사       │
    │ • 빠름/무료   │  │ • 800+ 항공사   │  │ • 가격 비교용  │
    │ • 안티봇 낮음 │  │ • 가상 인터라인 │  │ • 안티봇 대응  │
    └───────┬───────┘  └────────┬────────┘  └───────┬────────┘
            │                   │                    │
            └───────────────────┼────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │   Data Merger         │
                    │  (중복 제거, 정규화,  │
                    │   소스별 신뢰도 태깅) │
                    └───────────┬───────────┘
                                │
                         ┌──────┴──────┐
                         │ PostgreSQL  │
                         └─────────────┘
```

#### 소스별 항공사 라우팅 맵

```
항공사 → 최적 소스 매핑:

L1 전용 (Google Flights Protobuf):
  대한항공, 아시아나, ANA, JAL, 싱가포르항공, 캐세이퍼시픽,
  루프트한자, BA, 에어프랑스, KLM, 델타, 유나이티드, AA,
  에미레이트, 카타르, 에티하드 등 주요 FSC

L2 전용 (Kiwi.com API):
  위즈에어, 부엘링, 트랜사비아, 비엣젯, IndiGo,
  중국국제항공, 중국동방항공, 필리핀항공 등
  + 가상 인터라이닝 (다른 항공사 조합 경유)

L3 전용 (직접 크롤링 — 어디에도 없는 항공사):
  Allegiant, Avelo, Breeze (미국 ULCC)
  볼라리스, JetSMART (중남미)

L1 + L2 병렬 (교차 검증으로 최저가 확보):
  제주항공, 진에어, 에어아시아, 라이언에어, 이지젯,
  사우스웨스트, 스피릿, 프론티어 등 LCC

L1 + L3 병렬 (직접 가격이 더 쌀 수 있는 항공사):
  대한항공, 아시아나, ANA, JAL 등 한국/일본 FSC
  → 항공사 직접 사이트 전용 프로모션 포착
```

#### 안티봇 우회 전략 (L3 전용)

```
크롤링 요청 흐름 (L3: 항공사 직접 크롤링):

Scheduler → Task Queue → Worker Pool
                            │
                ┌───────────┴───────────┐
                │   Anti-Bot Layer      │
                │                       │
                │ 1. Residential Proxy  │  ← IP 로테이션
                │ 2. TLS Fingerprint    │  ← 브라우저 위장
                │    Randomization      │
                │ 3. User-Agent 랜덤화   │
                │ 4. Request Timing     │  ← 인간 행동 모방
                │    Variation          │
                │ 5. Cookie/Session     │  ← 세션 관리
                │ 6. CAPTCHA Solver     │  ← 필요시 (2captcha 등)
                │    Integration        │
                └───────────┬───────────┘
                            │
                    Airline Website
```

**주요 안티봇 시스템별 대응:**
- **Cloudflare**: TLS 핑거프린트 위장 + JS 챌린지 해결
- **DataDome**: 행동 분석 우회 (마우스 이동, 클릭 패턴 시뮬레이션)
- **PerimeterX/HUMAN**: 디바이스 핑거프린트 랜덤화
- **Akamai**: 엔터프라이즈급 — 가장 우회 난이도 높음

> **참고:** L1(Google Protobuf)과 L2(Kiwi API)는 안티봇 대응이 거의 불필요. 프록시 비용은 L3에만 집중.

#### 크롤링 우선순위 전략

```
Tier 1 (5-15분 간격): 인기 노선 상위 100개
  → L1 + L2 병렬 수집, L3는 1시간 간격
  → 예: ICN-NRT, ICN-BKK, ICN-LAX, ICN-CDG 등

Tier 2 (1-6시간 간격): 중간 수요 노선
  → L1 또는 L2 단일 소스 (최적 소스 선택)
  → 예: 주요 도시 간 직항 노선

Tier 3 (일 1회): 저수요/경유 노선
  → L2 (Kiwi 가상 인터라이닝 활용)
  → 대안 공항, 다중 경유 조합

Event-Driven: 사용자 검색 요청 시 실시간
  → 캐시 미스 시 L1 + L2 동시 요청 (먼저 오는 응답 반환, 나머지로 보완)
```

---

## 4. 데이터 모델

### 4.1 핵심 엔티티

```sql
-- 항공사
airlines
├── id (PK)
├── code (IATA 2자리: KE, OZ, AA ...)
├── name
├── type (FSC | LCC | ULCC)
├── alliance (Star | Oneworld | SkyTeam | None)
├── base_country
└── website_url

-- 공항
airports
├── id (PK)
├── code (IATA 3자리: ICN, NRT, LAX ...)
├── name
├── city
├── country
├── timezone
├── latitude
└── longitude

-- 항공편 (크롤링 결과)
flights
├── id (PK)
├── airline_id (FK)
├── flight_number
├── origin_airport_id (FK)
├── destination_airport_id (FK)
├── departure_time
├── arrival_time
├── duration_minutes
├── aircraft_type
├── cabin_class (ECONOMY | PREMIUM_ECONOMY | BUSINESS | FIRST)
├── crawled_at
└── source (GOOGLE_PROTOBUF | KIWI_API | DIRECT_CRAWL | GDS)

-- 가격 이력
prices
├── id (PK)
├── flight_id (FK)
├── price_amount
├── currency
├── fare_class (Y, M, H, Q, V, W ...)
├── includes_baggage (boolean)
├── includes_meal (boolean)
├── seat_selection_included (boolean)
├── crawled_at
└── booking_url

-- 좌석 정보
seat_specs
├── id (PK)
├── airline_id (FK)
├── aircraft_type
├── cabin_class
├── seat_pitch_inches
├── seat_width_inches
├── recline_degrees
├── has_power_outlet
├── has_usb
└── has_ife (개인 엔터테인먼트)

-- 사용자
users
├── id (PK)
├── email
├── name
└── created_at

-- 사용자 개인화 프로필
user_preferences
├── id (PK)
├── user_id (FK)
├── min_seat_pitch       -- "살이 쪄서 넓은 좌석" → min 32
├── min_seat_width       -- "살이 쪄서 넓은 좌석" → min 18
├── preferred_departure_time_start  -- "평일 밤 비행기" → 20:00
├── preferred_departure_time_end    -- "평일 밤 비행기" → 23:59
├── preferred_days (JSONB)          -- ["MON","TUE","WED","THU","FRI"]
├── max_layover_hours
├── max_stops
├── preferred_alliance
├── preferred_airlines (JSONB)
├── excluded_airlines (JSONB)
├── baggage_required (boolean)
├── meal_required (boolean)
├── priority (PRICE | TIME | COMFORT | BALANCED)
├── notes (text)        -- 자연어 추가 조건
└── updated_at

-- 검색 기록
search_history
├── id (PK)
├── user_id (FK)
├── origin
├── destination
├── departure_date
├── return_date (nullable, 편도면 NULL)
├── passengers
├── cabin_class
├── searched_at
└── results_count

-- 가격 알림
price_alerts
├── id (PK)
├── user_id (FK)
├── origin
├── destination
├── departure_date
├── return_date
├── target_price
├── current_best_price
├── is_active
├── last_notified_at
└── created_at
```

### 4.2 DA 분석용 테이블

```sql
-- 가격 예측 피처
price_features
├── id (PK)
├── route (origin-destination)
├── airline_id
├── departure_date
├── days_before_departure
├── day_of_week
├── month
├── is_holiday
├── demand_index        -- DA가 계산
├── competitor_price_avg
├── historical_avg_price
├── historical_min_price
├── seat_fill_rate      -- 좌석 점유율 추정
└── recorded_at

-- 최적 구매 시점 분석
booking_time_analysis
├── id (PK)
├── route
├── airline_id
├── optimal_days_before  -- DA 분석 결과
├── price_at_optimal
├── price_at_30days
├── price_at_14days
├── price_at_7days
├── price_at_1day
├── confidence_score
└── analyzed_at
```

---

## 5. 개인화 시스템

### 5.1 사용자 조건 매핑

사용자의 자연어 입력을 구조화된 조건으로 변환:

| 사용자 입력 예시 | 매핑되는 조건 |
|---|---|
| "살이 쪄서 넓은 좌석 원해" | `min_seat_width >= 18인치`, `min_seat_pitch >= 32인치`, 프리미엄 이코노미 우선 추천 |
| "직장인이라 평일 밤 비행기 원해" | `departure_time: 20:00-23:59`, `days: [MON-FRI]` |
| "아이 둘과 가는 가족여행" | `passengers: 2A+2C`, 직항 우선, 수하물 포함 필터 |
| "마일리지 적립 중요해" | `preferred_alliance` 기반 필터, 적립 마일 계산 |
| "환승 1시간이면 불안해" | `min_layover_hours >= 2` |
| "새벽 도착은 싫어" | `arrival_time: 06:00-23:00` |
| "짐이 많아" | `baggage_required: true`, 수하물 정책 비교 |
| "탄소 배출 적은 거" | 직항 우선, 신형 기종 우선 (A350, 787, A220) |

### 5.2 추천 점수 산정 (DA 영역)

각 항공편에 대해 **개인화 종합 점수** 계산:

```
Total Score = w1 × Price Score
            + w2 × Time Score
            + w3 × Comfort Score
            + w4 × Convenience Score
            + w5 × Reliability Score

where:
  Price Score      = (최저가 - 해당가격) / 가격범위  (0~1, 낮을수록 좋음)
  Time Score       = 선호 시간대 매칭도 (0~1)
  Comfort Score    = 좌석 스펙 매칭도 (0~1)
  Convenience Score= 경유 횟수, 수하물, 기내식 등 (0~1)
  Reliability Score= 정시 운항률, 항공사 평판 (0~1)

  w1~w5 = 사용자 priority에 따른 가중치 (합계 1.0)
    PRICE:    [0.5, 0.1, 0.1, 0.2, 0.1]
    TIME:     [0.2, 0.4, 0.1, 0.2, 0.1]
    COMFORT:  [0.15, 0.1, 0.45, 0.2, 0.1]
    BALANCED: [0.3, 0.2, 0.2, 0.2, 0.1]
```

---

## 6. DA 협업 영역

### 6.1 가격 예측 모델

**목표:** 특정 노선의 미래 가격 변동을 예측하여 "지금 사야 할지, 기다려야 할지" 추천

**접근 방법:**
1. **Phase 1** (베이스라인): Random Forest + XGBoost
   - 피처: 출발일까지 남은 일수, 요일, 월, 공휴일 여부, 수요 인덱스
   - 타겟: 가격
2. **Phase 2** (고도화): LSTM / GRU 시계열 모델
   - 가격 시퀀스 데이터 학습
   - 44개 의사결정 피처 활용
3. **Phase 3** (앙상블): 여러 모델 조합
   - Random Forest + XGBoost + LSTM 앙상블
   - 80%+ 예측 정확도 목표

**DA에게 제공할 데이터:**
- 노선별 일간 가격 이력 (최소 6개월)
- 좌석 클래스별 가격 분포
- 검색 빈도/수요 데이터
- 공휴일/이벤트 캘린더
- 경쟁 항공사 가격 데이터

### 6.2 최적 구매 시점 분석

**목표:** "이 노선은 출발 X일 전에 사는 게 가장 싸다"

**분석 항목:**
- 노선별/항공사별 가격 곡선 (출발일 대비)
- 요일별 가격 패턴 (화/수요일이 정말 싼지?)
- 시즌별 최적 구매 타이밍
- LCC vs FSC 가격 패턴 차이

### 6.3 경로 최적화 알고리즘

**목표:** 직항이 없거나 비쌀 때, 최적의 경유 조합 탐색

**알고리즘 옵션:**
- **A\* 알고리즘**: 휴리스틱 기반 최단 경로
- **다목적 최적화**: 가격 + 시간 + 편의성 Pareto 최적
- **가상 인터라이닝**: 제휴가 아닌 항공사 간 조합 (Kiwi.com 방식)
- **대안 공항 탐색**: 인근 공항 포함 검색 (예: ICN 대신 GMP, NRT 대신 HND)

### 6.4 개인화 추천 알고리즘

**목표:** 사용자 조건에 맞는 최적 항공편 랭킹

**접근 방법:**
- 협업 필터링: 유사 사용자 선호도 기반
- 컨텐츠 기반: 사용자 프로필 매칭
- 하이브리드: 위 둘 + 가격 예측 모델 결합

---

## 7. API 설계 (초안)

### 7.1 핵심 엔드포인트

```
# 검색
POST /api/v1/search/flights
  body: {
    origin: "ICN",
    destination: "NRT",
    departure_date: "2026-04-15",
    return_date: "2026-04-20",     // null이면 편도
    passengers: { adults: 2, children: 1, infants: 0 },
    cabin_class: "ECONOMY",
    preferences: {                 // 개인화 조건 (선택)
      min_seat_pitch: 32,
      departure_time_range: ["20:00", "23:59"],
      max_stops: 1,
      max_layover_hours: 3,
      baggage_required: true,
      priority: "BALANCED"
    }
  }

# 자연어 검색
POST /api/v1/search/natural
  body: {
    query: "다음주 금요일 밤에 도쿄 가는 넓은 좌석 저렴한 비행기"
  }

# 가격 추이
GET /api/v1/prices/history?route=ICN-NRT&days=90

# 가격 예측
GET /api/v1/prices/predict?route=ICN-NRT&date=2026-04-15

# 최적 구매 시점
GET /api/v1/prices/best-time?route=ICN-NRT&date=2026-04-15

# 가격 알림
POST /api/v1/alerts
  body: {
    origin: "ICN",
    destination: "NRT",
    departure_date: "2026-04-15",
    target_price: 150000
  }

# 사용자 프로필
GET  /api/v1/users/me/preferences
PUT  /api/v1/users/me/preferences
```

---

## 8. 개발 로드맵

### Phase 1: 기반 구축 (4주)

| 주차 | Dev (Perry) | DA |
|---|---|---|
| 1주 | 프로젝트 셋업, DB 스키마, 기본 API 구조 | 데이터 요구사항 정의, 분석 환경 구축 |
| 2주 | Playwright 크롤러 프로토타입 (항공사 3-5개) | 가격 데이터 EDA, 피처 엔지니어링 설계 |
| 3주 | 크롤러 안정화, 프록시 풀 구성, 스케줄러 | 베이스라인 가격 예측 모델 (Random Forest) |
| 4주 | Redis 캐싱, 검색 API 구현 | 최적 구매 시점 분석 v1 |

### Phase 2: 핵심 기능 (4주)

| 주차 | Dev (Perry) | DA |
|---|---|---|
| 5주 | 크롤러 확장 (20+ 항공사), 에러 핸들링 | 경로 최적화 알고리즘 v1 |
| 6주 | 개인화 조건 시스템, 필터/정렬 | 개인화 추천 점수 모델 |
| 7주 | 프론트엔드 MVP (검색, 결과, 필터) | XGBoost 모델 추가, 앙상블 테스트 |
| 8주 | 가격 알림 시스템, 이메일/푸시 | 모델 성능 평가, 하이퍼파라미터 튜닝 |

### Phase 3: 고도화 (4주)

| 주차 | Dev (Perry) | DA |
|---|---|---|
| 9주 | 크롤러 확장 (40+ 항공사), 자연어 검색 | LSTM/GRU 시계열 모델 |
| 10주 | 가상 인터라이닝 (다중 항공사 조합) | 다목적 최적화 (가격+시간+편의) |
| 11주 | 성능 최적화, 부하 테스트 | 이상 탐지 (가격 오류, 플래시 세일) |
| 12주 | 베타 출시, 모니터링 강화 | 모델 배포, A/B 테스트 설계 |

### Phase 4: 확장 (ongoing)

- 크롤러 60+ 항공사 확장
- 호텔/렌터카 연동
- 모바일 앱 (React Native / Flutter)
- 소셜 기능 (여행 공유, 그룹 검색)
- 마일리지 최적화 기능
- 탄소 배출 추적/오프셋

---

## 9. 데이터 소스 전략 — 4-Layer 병렬 수집

### 9.1 레이어별 역할과 병렬 운영

```
┌─────────────────────────────────────────────────────────────────┐
│                    병렬 수집 파이프라인                            │
├─────────┬──────────────┬────────────┬──────────────────────────┤
│  Layer  │ 소스          │ 커버리지   │ 역할                      │
├─────────┼──────────────┼────────────┼──────────────────────────┤
│  L1     │ Google       │ ~40개 FSC  │ 주요 항공사 초고속 수집    │
│         │ Flights      │ + 일부 LCC │ (Protobuf, 무료, 빠름)    │
│         │ Protobuf     │            │                          │
├─────────┼──────────────┼────────────┼──────────────────────────┤
│  L2     │ Kiwi.com     │ 800+       │ L1 누락분 커버 (중국,     │
│         │ Tequila API  │ 항공사     │ 유럽 LCC, 동남아 LCC)     │
│         │              │            │ + 가상 인터라이닝          │
├─────────┼──────────────┼────────────┼──────────────────────────┤
│  L3     │ 항공사 직접  │ 타겟 선별  │ 어디에도 없는 항공사 +     │
│         │ 크롤링       │ (20-30개)  │ 직접 프로모션 포착         │
│         │ (Playwright) │            │ (핵심 차별점)              │
├─────────┼──────────────┼────────────┼──────────────────────────┤
│  L4     │ GDS          │ 400+       │ 장기 확장용               │
│  (장기) │ (Travelport) │ + LCC 125  │ LCC 125개 포함            │
└─────────┴──────────────┴────────────┴──────────────────────────┘

병렬 실행:
  • L1 + L2: 항상 동시 실행 → 결과 머지 → 중복 제거 + 최저가 선택
  • L3: 타겟 항공사만 스케줄 기반 실행
  • On-demand: 사용자 검색 시 L1+L2 동시 요청, 먼저 온 응답 즉시 반환
```

### 9.2 소스 간 데이터 머징 전략

```
L1 결과 ──┐
           ├──→ Data Merger ──→ 정규화된 결과
L2 결과 ──┤      │
           │      ├── 중복 제거 (같은 편명+날짜+클래스)
L3 결과 ──┘      ├── 최저가 선택 (소스별 가격 비교)
                  ├── 소스 태깅 (source: L1|L2|L3)
                  └── 신뢰도 점수 (직접 크롤링 > API > 메타서치)
```

### 9.3 부가 데이터

```
부가 데이터:
  ├── SeatGuru → 좌석 스펙 크롤링 (Scrapy)
  ├── ICAO → 탄소 배출 데이터
  ├── OAG → 항공 스케줄 데이터
  └── 공항 API → 공항 정보
```

### 9.2 법적 고려사항

| 항목 | 현황 | 대응 |
|---|---|---|
| CFAA (미국) | HiQ vs LinkedIn 판례: 공개 데이터 크롤링은 CFAA 위반 아님 | 공개된 가격 정보만 수집 |
| EU GDPR | 웹 크롤링 자체는 금지 아님, 개인정보 수집 시 규제 | 개인정보 수집 안 함 (가격/스케줄만) |
| EU Database Directive | 상당한 투자가 들어간 DB 보호 | 전체 복제 아닌 선별적 수집 |
| 항공사 ToS | 대부분 자동 수집 금지 조항 | robots.txt 존중, 합리적 요청 빈도 |
| 한국 정보통신망법 | 정당한 접근 필요 | 공개된 정보만, 서버 부하 최소화 |

**권장사항:** 법률 자문 필수. 초기에는 API 기반으로 시작, 크롤링은 점진적으로 확대.

---

## 10. 캐싱 전략

```
요청 흐름:

User Request
    │
    ▼
[L1 Cache: Redis]  ← TTL 5-15분 (인기 노선)
    │ MISS
    ▼
[L2 Cache: Redis Cluster]  ← TTL 30-60분
    │ MISS
    ▼
[Database: PostgreSQL]  ← 가격 이력 전체
    │ NO RECENT DATA
    ▼
[On-Demand Crawl]  ← 실시간 크롤링 후 캐시 업데이트
    │
    ▼
Response + Cache Write (L1 + L2 + DB)
```

**데이터별 Freshness 요구사항:**

| 데이터 유형 | 갱신 주기 | 캐시 TTL |
|---|---|---|
| 인기 노선 가격 | 5-15분 | 5분 |
| 일반 노선 가격 | 1-6시간 | 30분 |
| 비인기 노선 가격 | 일 1회 | 6시간 |
| 좌석 잔여석 | 실시간 | 1분 |
| 항공 스케줄 | 일 1회 | 24시간 |
| 공항 정보 | 주 1회 | 7일 |
| 좌석 스펙 | 월 1회 | 30일 |

---

## 11. 모니터링 & 운영

### 11.1 핵심 메트릭

**크롤러 메트릭:**
- 성공률 (항공사별, 시간대별)
- 평균 크롤링 시간
- 안티봇 차단률
- 프록시 상태/비용

**서비스 메트릭:**
- API 응답 시간 (p50, p95, p99)
- 검색 결과 수
- 캐시 히트율
- 사용자 세션/검색 수

**비즈니스 메트릭:**
- Skyscanner 대비 저가 발견 비율
- 가격 예측 정확도
- 사용자 만족도 (추천 클릭률)
- 알림 전환율

### 11.2 알림 조건

- 크롤러 성공률 < 80%
- API p95 응답시간 > 3초
- 캐시 히트율 < 70%
- 프록시 잔여량 < 20%
- DB 디스크 사용량 > 80%

---

## 12. 비용 추정 (월간, MVP 기준)

| 항목 | 예상 비용 | 비고 |
|---|---|---|
| Residential Proxy | $200-500 | ~$5-15/GB, 초기 트래픽 |
| Cloud 서버 (크롤러) | $100-300 | 2-4 인스턴스 |
| Cloud 서버 (API/DB) | $50-150 | |
| Redis (Managed) | $30-50 | |
| PostgreSQL (Managed) | $30-50 | |
| 도메인/SSL | $20 | |
| 모니터링 | $0-50 | 무료 티어 활용 |
| **합계** | **$430-1,120/월** | |

---

## 부록 A: 항공 동맹 정리

```
Star Alliance (26개 항공사):
  유나이티드, 루프트한자, ANA, 싱가포르항공, 에어캐나다,
  아시아나, 터키항공, TAP, 에게안, 에어인디아,
  에티오피아항공, 남아프리카항공, 에어뉴질랜드 등
  → 1,300+ 목적지, 195개국

Oneworld (13개 항공사):
  아메리칸항공, 브리티시에어웨이즈, 콴타스, 캐세이퍼시픽,
  JAL, 이베리아, 핀에어, 알래스카항공,
  말레이시아항공, 로열에어모로코 등
  → 1,100+ 목적지

SkyTeam (19개 항공사):
  델타, 에어프랑스-KLM, 대한항공, 중국동방항공,
  아에로멕시코, 베트남항공, 가루다인도네시아,
  사우디아, 케냐항공, SAS, ITA항공 등
  → 1,150 목적지, 175개국
```

## 부록 B: 좌석 스펙 참고

| 항공사 | 이코노미 피치 | 이코노미 넓이 | 비고 |
|---|---|---|---|
| ANA | 34인치 | 17.2인치 | 장거리 전 기종 |
| 싱가포르항공 | 34인치 | 18인치 | |
| 에미레이트 (A380) | 34인치 | 18인치 | |
| 제트블루 | 32-34인치 | 17.8인치 | |
| 델타 | 31인치 | 17.2인치 | |
| 사우스웨스트 | 31.8인치 | 17인치 | |
| 라이언에어 | 30인치 | 17인치 | |
| 스피릿 | 28인치 | 17.75인치 | ULCC 최소 |

---

*최종 수정: 2026-02-13*
*작성자: Perry (Dev) + Claude AI*
