# Sky Scanner - 실행 로드맵

> PLANNING.md의 전략을 구체적인 실행 계획으로 전환

## 마일스톤 개요

```
M0 (1주)   프로젝트 부트스트랩
M1 (3주)   크롤러 MVP — L1(Google) + L2(Kiwi) 병렬 수집
M2 (3주)   API + 검색 서비스 + Data Merger
M3 (2주)   개인화 시스템
M4 (2주)   프론트엔드 MVP
M5 (2주)   L3(직접 크롤링) 확장 + 안정화
M6 (ongoing) L4(GDS) + 고도화 + 스케일링
```

---

## M0: 프로젝트 부트스트랩 (Week 1)

### Dev (Perry)

- [ ] 모노레포 구조 셋업
  ```
  sky-scanner/
  ├── apps/
  │   ├── api/              # FastAPI 서버
  │   ├── crawler/           # 크롤러 엔진
  │   ├── scheduler/         # 크롤링 스케줄러
  │   └── web/               # Next.js 프론트엔드
  ├── packages/
  │   ├── core/              # 공유 모델/스키마
  │   ├── db/                # DB 마이그레이션/모델
  │   └── ml/                # DA 모델 패키지
  ├── scripts/               # 유틸리티 스크립트
  ├── data/                  # 시드 데이터 (공항, 항공사)
  ├── docs/                  # 문서
  ├── references/            # 레퍼런스 프로젝트
  └── docker-compose.yml
  ```
- [ ] Python 환경 구성 (pyproject.toml, uv/poetry)
- [ ] Docker Compose: PostgreSQL + Redis + (Elasticsearch는 M2에서)
- [ ] DB 스키마 v1 작성 + 마이그레이션 (Alembic)
- [ ] 시드 데이터 준비
  - 공항 코드/좌표 (IATA 기준 ~1,000개)
  - 항공사 정보 (IATA 코드, 동맹, 타입)
  - 좌석 스펙 (SeatGuru 기반)
- [ ] CI/CD 파이프라인 (GitHub Actions)
- [ ] `.gitignore`, `CLAUDE.md`, 린터/포매터 설정

### DA

- [ ] 분석 환경 구축 (Jupyter + 필수 패키지)
- [ ] 데이터 요구사항 문서 작성
- [ ] flight-price-prediction 레퍼런스 코드 리뷰
- [ ] 피처 엔지니어링 초안 설계

### 완료 기준

- `docker compose up`으로 PostgreSQL + Redis 구동
- DB 스키마 마이그레이션 성공
- 공항/항공사 시드 데이터 로딩 확인
- DA가 Jupyter에서 DB 연결 가능

---

## M1: 크롤러 MVP — L1 + L2 병렬 수집 (Week 2-4)

> **핵심 변경:** Google Flights 단일 소스가 아닌, L1(Google) + L2(Kiwi) 병렬 구조로 시작.
> Google에 없는 중국 빅3, 위즈에어(62M), 부엘링(38M), 비엣젯 등을 M1부터 커버.

### Week 2: L1(Google Flights Protobuf) + L2(Kiwi API) 동시 구현

**L1: Google Flights Protobuf 크롤러**
- [ ] fast-flights 레퍼런스를 기반으로 커스텀 크롤러 구현
  - Protobuf 메시지 구성 (출발지/도착지/날짜/인원)
  - Base64 인코딩 + HTTP 요청
  - HTML 파싱 (selectolax)
- [ ] primp 또는 curl_cffi로 TLS 핑거프린트 위장
- [ ] Playwright 폴백 (Protobuf 실패 시)

**L2: Kiwi.com Tequila API 연동**
- [ ] Kiwi.com Tequila API 키 발급 + SDK 셋업
- [ ] 검색 API 연동 (search/flights)
  - 편도/왕복/다구간 지원
  - 가상 인터라이닝 옵션 활성화
- [ ] L2 전용 항공사 확인 (Google 누락분 실제 커버 여부 검증)
  - 중국국제항공, 중국동방항공
  - 위즈에어, 부엘링, 트랜사비아
  - 비엣젯, 필리핀항공, 에어아시아, IndiGo

**공통**
- [ ] 기본 데이터 모델 (Flight, Price, Route) — 소스 구분 필드 포함
- [ ] 크롤링 결과 → PostgreSQL 저장 파이프라인

### Week 3: Data Merger + 스케줄러

- [ ] **Data Merger 구현**
  - L1 + L2 결과 정규화 (항공편명, 시간, 가격 통일 포맷)
  - 중복 제거 (같은 편명+날짜+클래스 → 최저가 선택)
  - 소스 태깅 (source: GOOGLE_PROTOBUF | KIWI_API)
  - 소스별 신뢰도 점수
- [ ] **항공사-소스 라우팅 테이블** 구현
  - 항공사별 최적 소스 자동 선택
  - L1 전용 / L2 전용 / L1+L2 병렬 분류
- [ ] Celery + Redis 태스크 큐 구성
- [ ] 크롤링 스케줄러 (L1, L2 병렬 실행)
  - 인기 노선: L1 + L2 동시 (5-15분 간격)
  - 일반 노선: 최적 단일 소스 (1-6시간)
- [ ] 에러 핸들링 + 재시도 로직 (소스별 독립 재시도)

### Week 4: 안정화 + 커버리지 검증

- [ ] L1+L2 커버리지 갭 분석
  - 실제로 양쪽 다 누락되는 항공사 식별 → L3 대상 목록 확정
- [ ] Rate Limiting (소스별 독립 관리)
  - L1: 자체 제한 (IP 기반)
  - L2: Kiwi API Rate Limit 준수
- [ ] 크롤링 결과 검증 (가격 이상치 탐지)
- [ ] L1-L2 교차 검증 (같은 항공편의 소스별 가격 차이 분석)
- [ ] 로깅 + 모니터링 (소스별 성공률, 응답시간, 커버리지)
- [ ] Residential Proxy 풀 연동 (L1 폴백용, L3 준비)

### DA (병렬 진행)

- [ ] 수집 데이터 EDA (L1 vs L2 소스별 데이터 품질 비교)
- [ ] 가격 분포, 시계열 패턴 분석
- [ ] 소스별 가격 차이 분석 (같은 편에 대한 L1 vs L2 가격 비교)
- [ ] 베이스라인 가격 예측 모델 (Random Forest)
- [ ] 피처 중요도 분석

### 완료 기준

- L1(Google) + L2(Kiwi) 병렬 수집으로 **100+ 항공사** 커버
- Google 누락 항공사(위즈에어, 중국동방 등) L2로 수집 확인
- Data Merger 동작: 같은 노선에 대한 L1+L2 결과 머지 + 최저가 선택
- 크롤링 성공률 > 90% (소스별 독립 측정)
- 가격 데이터 일 10,000건+ 축적
- DA: 소스별 가격 비교 리포트 + 베이스라인 모델 MAE 확인

---

## M2: API + 검색 서비스 + Data Merger (Week 5-7)

### Week 5: FastAPI 기본 구조

- [ ] FastAPI 프로젝트 셋업
- [ ] 핵심 엔드포인트 구현
  - `POST /api/v1/search/flights` (기본 검색)
  - `GET /api/v1/prices/history` (가격 추이)
  - `GET /api/v1/airports/search` (공항 자동완성)
  - `GET /api/v1/airlines` (항공사 목록 + 소스 레이어 정보)
- [ ] Redis 캐싱 레이어
  - 검색 결과 캐시 (TTL 5분)
  - Stale-While-Revalidate 패턴
- [ ] 요청/응답 스키마 (Pydantic v2)

### Week 6: 검색 고도화 + 병렬 소스 통합

- [ ] 복합 필터링 (경유, 시간대, 항공사, 가격 범위)
- [ ] 정렬 옵션 (가격순, 시간순, 추천순)
- [ ] 왕복/편도/다구간 검색 지원
- [ ] **On-demand 병렬 수집** (캐시 미스 시)
  - L1 + L2 동시 요청 → 먼저 온 응답 즉시 반환
  - 나머지 응답은 비동기로 머지 + 캐시 업데이트
  - 소스별 타임아웃 독립 관리
- [ ] 대안 공항 자동 포함 (ICN↔GMP, NRT↔HND 등)
- [ ] 검색 결과에 데이터 소스 표시 (가격 출처 투명성)

### Week 7: 인증 + 사용자 시스템

- [ ] 사용자 인증 (JWT)
- [ ] 사용자 프로필 CRUD
- [ ] 검색 히스토리 저장
- [ ] API Rate Limiting (사용자별)
- [ ] API 문서 (OpenAPI/Swagger 자동 생성)

### DA (병렬 진행)

- [ ] XGBoost 모델 추가
- [ ] 앙상블 모델 테스트 (RF + XGBoost)
- [ ] 최적 구매 시점 분석 v1 (노선별 가격 곡선)
- [ ] 추천 점수 알고리즘 초안

### 완료 기준

- API로 항공편 검색 + 결과 반환 (< 2초 응답)
- 캐시 히트율 > 60%
- 사용자 회원가입/로그인/프로필 관리 동작
- DA: 앙상블 모델 성능 > 베이스라인

---

## M3: 개인화 시스템 (Week 8-9)

### Week 8: 개인화 조건 엔진

- [ ] 사용자 선호도 프로필 시스템
  - 좌석 스펙 조건 (피치/넓이 최소값)
  - 시간대 선호 (출발/도착 시간 범위)
  - 요일 선호
  - 경유 조건 (최대 횟수, 최대 시간)
  - 수하물/기내식/좌석선택 필요 여부
- [ ] 좌석 스펙 DB 구축 (항공사/기종별)
- [ ] 개인화 필터 → 검색 쿼리 변환 로직

### Week 9: 추천 + 자연어 검색

- [ ] 추천 점수 시스템 통합 (DA 알고리즘 연동)
  - 가격 + 시간 + 편의성 + 신뢰도 가중합
  - 사용자 priority에 따른 가중치 조정
- [ ] 자연어 조건 파싱 (LLM API 활용)
  - "살이 쪄서 넓은 좌석" → min_seat_width >= 18
  - "평일 밤 비행기" → departure_time 20:00-23:59, days MON-FRI
- [ ] `POST /api/v1/search/natural` 엔드포인트
- [ ] 가격 예측 엔드포인트 통합
  - `GET /api/v1/prices/predict`
  - `GET /api/v1/prices/best-time`

### DA (병렬 진행)

- [ ] 개인화 추천 점수 알고리즘 최종화
- [ ] 가중치 최적화 (사용자 클릭 데이터 기반 — 초기는 휴리스틱)
- [ ] 경로 최적화 알고리즘 v1 (A* 기반)

### 완료 기준

- 개인화 조건 설정 후 검색 결과 필터링/정렬 동작
- 자연어 입력 → 구조화된 검색 변환 성공률 > 80%
- 추천 점수가 검색 결과에 반영됨
- 가격 예측 API 응답 확인

---

## M4: 프론트엔드 MVP (Week 10-11) ✅ 완료

### 기술 스택
- Next.js 16 (App Router) + TypeScript + Tailwind CSS 4 + shadcn/ui
- Zustand (인증 상태) + recharts (차트) + nuqs (URL 상태)
- 58개 파일 (48 TSX + 10 TS), ~5,300 LoC

### Week 10: 핵심 UI ✅

- [x] Next.js 프로젝트 셋업 (App Router, TypeScript, Tailwind, shadcn/ui 18개 컴포넌트)
- [x] 검색 페이지
  - 출발지/도착지 자동완성 (공항 코드 + 도시명, debounced)
  - 날짜 선택기 (편도/왕복)
  - 인원 선택 (성인/아동/유아)
  - 좌석 클래스 선택 (Economy/Premium Economy/Business/First)
  - 자연어 검색 바 (`POST /search/natural`)
- [x] 검색 결과 페이지
  - 항공편 카드 (가격, 시간, 항공사, 경유, 예약 링크)
  - 필터 사이드바 (항공사 체크박스, 가격 범위)
  - 정렬 옵션 (추천순, 가격순, 시간순)
  - 추천 점수 뱃지 (M3 ML 스코어링)
  - 가격 분석 페이지 링크
- [x] 반응형 디자인 (모바일 햄버거 메뉴, 수직 폼 배치)

### Week 11: 부가 기능 UI ✅

- [x] 사용자 프로필 / 개인화 설정 페이지 (선호도: 좌석, 경유, 동맹, 우선순위)
- [x] 가격 추이 차트 (recharts AreaChart — min/max/avg 가격)
- [x] 가격 예측 표시 (BUY_NOW/WAIT/NEUTRAL + 신뢰도)
- [x] 최적 구매 시점 카드 (타이밍 인디케이터)
- [x] 검색 히스토리 (페이지네이션, 클릭 시 재검색)
- [x] 로그인/회원가입 (JWT 자동 갱신, localStorage persist)

### 완료 기준 ✅

- [x] 검색 → 결과 → 개인화 필터 전체 플로우 동작
- [x] 모바일/데스크톱 반응형
- [x] `next build` + ESLint + TypeScript 모두 통과
- [x] Auth guard: 미인증 시 /login 리다이렉트

---

## M5: L2 확장(항공사 API 리버스 엔지니어링) + L3(Playwright) + 안정화 (Week 12-14)

> **핵심:** M1-M4는 L1(Google)+L2(Kiwi)로 100+ 항공사 커버. M5에서:
> 1. **L2 확장** — Google에 없는 한국/아시아 LCC 항공사 API를 리버스 엔지니어링하여 직접 크롤링
> 2. **L3(Playwright)** — API가 없는 항공사는 브라우저 자동화로 크롤링
> 3. **가격 알림 + 운영 안정화**
>
> **이미 완료:** 제주항공(7C) L2 크롤러 — `sec.jejuair.net` lowest-fare calendar API 리버스 엔지니어링 성공

### Week 12: L2 확장 — 한국/아시아 LCC API 리버스 엔지니어링

> **방법론:** Chrome DevTools로 항공사 웹사이트의 내부 JSON API를 발견하고,
> 인증 없이 호출 가능한 엔드포인트를 찾아 Python httpx 클라이언트로 구현.
> 제주항공에서 검증된 패턴(`sec.xxx.net` + `Channel-Code` 헤더)을 다른 항공사에 적용.

**L2-A: Navitaire PSS 기반 항공사 (제주항공과 동일 패턴 예상)**
- [x] 제주항공 (7C) — ✅ 완료 (`searchlowestFareCalendar.json`, 52개 취항지)
- [x] 이스타항공 (ZE) — ✅ 완료 (`kraken.eastarjet.com` dotRez API, 28개 취항지, 세션 필요→자동 생성)
- [ ] 에어프레미아 (YP) — ⚠️ Cloudflare JS Challenge가 `/api/v1/low-fares`, `/api/v1/fares` 차단. 노선 API(`/api/v1/airports`, `/api/v1/airport-regions`)는 오픈. ICN→9개 노선(NRT,HKG,DAD,BKK,IAD,HNL,SFO,LAX,EWR). **→ L3 전환 필요**

**L2-B: 기타 한국 LCC — ⚠️ 전부 L3 전환 필요 (Cloudflare/Akamai 차단)**
- [ ] 티웨이항공 (TW) — Akamai Bot Detection, Spring Boot 403 (CSRF), 서버 렌더링. **→ L3**
- [ ] 진에어 (LJ) — Cloudflare Turnstile CAPTCHA (가장 공격적 차단). **→ L3**
- [ ] 에어부산 (BX) — Cloudflare challenge loop, `/web/bookingApi/` 존재하나 403. **→ L3**
- [ ] 에어서울 (RS) — Cloudflare 403 (홈페이지 자체가 차단). **→ L3**

**L2-C: 아시아 LCC (Google Flights 미커버 또는 부분 커버)**
- [ ] Peach Aviation (MM) — 일본, ANA 자회사
- [ ] VietJet Air (VJ) — 베트남
- [ ] Cebu Pacific (5J) — 필리핀
- [ ] Spring Airlines (9C) — 중국

**구현 패턴 (제주항공 기준 표준화):**
```
apps/crawler/src/sky_scanner_crawler/{airline_name}/
├── __init__.py
├── client.py            # httpx AsyncClient (해당 항공사 API 엔드포인트)
├── response_parser.py   # API 응답 → NormalizedFlight 변환
└── crawler.py           # {Airline}Crawler(BaseCrawler)
```

**각 항공사 리버스 엔지니어링 절차:**
1. Chrome DevTools로 예약 페이지 접속 → Network 탭에서 XHR/fetch 요청 캡처
2. 최저가 캘린더 / 운임 조회 JSON API 엔드포인트 식별
3. 필수 헤더 확인 (Channel-Code, Origin, Referer 등)
4. 인증 필요 여부 테스트 (쿠키 없이 호출)
5. Python httpx 클라이언트 구현 + retry 로직
6. CLI 명령어 추가 (`crawl-{airline}`)
7. 헬스체크 등록

### Week 13: L3 Playwright 직접 크롤링 (API 없는 항공사용)

> **L2 리버스 엔지니어링이 불가능한 경우** (Akamai/CloudFlare WAF 차단, 세션 필수 등)
> Playwright 브라우저 자동화로 폴백.

**L3 Tier 1: L2 리버스 엔지니어링 실패한 한국 LCC**
- [ ] L2-B/C에서 API 발견 실패한 항공사 → Playwright 크롤러로 전환
- [ ] Playwright 기반 BaseBrowserCrawler 구현
  - 검색 폼 자동 입력 → 결과 HTML 파싱
  - Anti-bot 우회 (stealth mode, fingerprint randomization)

**L3 Tier 2: 직접 프로모션 포착용 (한국/일본 FSC)**
- [ ] 대한항공, 아시아나 직접 크롤링 (L1과 가격 비교)
- [ ] ANA, JAL 직접 크롤링
- [ ] L1 vs L3 가격 차이 분석 → 직접 사이트가 더 싼 케이스 확인

**L3 Tier 3: 글로벌 ULCC (Google/Kiwi 완전 누락)**
- [ ] Allegiant, Avelo, Breeze (미국 ULCC)
- [ ] 볼라리스 (멕시코), JetSMART (칠레)

**공통**
- [ ] 항공사별 파서 모듈화 (팩토리 패턴)
- [ ] Residential Proxy 풀 본격 운영
- [ ] 안티봇 대응 매핑 (항공사별: Akamai, CloudFlare, PerimeterX 등)
- [ ] L2+L3 결과 → Data Merger 통합 (L1+L2+L3 머지)

### Week 14: 가격 알림 + 운영 + 가격 예측 고도화

**가격 알림 시스템**
- [ ] 목표 가격 이하 시 이메일/푸시 알림
- [ ] Celery Beat 기반 주기적 확인
- [ ] L2/L3 전용 항공사 포함 (제주항공 최저가 알림 등)

**가격 예측 고도화 (다중 소스 데이터 활용)**
- [ ] 제주항공 등 직접 크롤링 데이터로 heuristic 예측 정확도 향상
- [ ] L1(Google) vs L2(항공사 직접) 가격 차이 패턴 분석
- [ ] 항공사별 가격 변동 주기 분석 (LCC vs FSC)
- [ ] "언제 사야 저렴한가" 추천 로직 개선
  - 현재: 7일/30일 이동평균 기반 heuristic
  - 개선: 항공사별 가격 곡선 학습 + 출발일까지 남은 기간별 가격 패턴

**운영 대시보드**
- [ ] 소스별(L1/L2/L3) 크롤러 상태 모니터링
- [ ] 항공사별 성공률 + 소스별 커버리지
- [ ] 가격 데이터 품질 메트릭
- [ ] 부하 테스트 + 성능 최적화

### DA (병렬 진행)

- [ ] LSTM/GRU 시계열 모델 개발 (다중 소스 가격 데이터)
- [ ] 3-소스 데이터 통합 분석 (L1 vs L2-direct vs L3 가격 패턴)
- [ ] 항공사별 가격 변동 모델링 (LCC는 출발일 가까워질수록 급등하는 패턴)
- [ ] 이상 탐지 (가격 오류, 플래시 세일 감지)
- [ ] A/B 테스트 프레임워크 설계

### 완료 기준

- L2 리버스 엔지니어링으로 **한국 LCC 5개+** 직접 가격 수집
- L1+L2+L3 합산 **150+ 항공사** 커버
- 제주항공/티웨이 등 Google에 없는 항공사 가격 비교 가능
- 가격 알림 이메일 발송 확인
- 크롤러 성공률 > 85% (소스별 독립 측정)
- 전체 시스템 24시간 무중단 운영 테스트

---

## M6: L4(GDS) + 고도화 + 스케일링 (Week 14+)

### 기능 확장

- [ ] **L4: GDS 연동** (Travelport — LCC 125개 포함)
  - L1+L2+L3로 커버 못하는 나머지 항공사 보완
  - 4-Layer 완성: L1+L2+L3+L4 전체 병렬 운영
- [ ] Duffel API 추가 연동 (NDC 지원 항공사 보완)
- [ ] 마일리지 적립 계산 기능
- [ ] 탄소 배출 표시 + 친환경 옵션 필터
- [ ] 다국어 지원 (한/영/일)
- [ ] PWA (Progressive Web App) 변환

### 인프라 스케일링

- [ ] Kubernetes 배포 (또는 ECS)
- [ ] 크롤러 수평 확장 (워커 오토스케일링)
- [ ] DB 읽기 복제본
- [ ] CDN 구성

### DA 고도화

- [ ] 앙상블 모델 프로덕션 배포
- [ ] 실시간 가격 예측 서빙 (모델 서버)
- [ ] 사용자 행동 데이터 기반 추천 개선
- [ ] 수요 예측 모델

---

## 기술 부채 관리

각 마일스톤 완료 후 1-2일 기술 부채 정리 시간 확보:

- 테스트 커버리지 확인 (목표: > 70%)
- 코드 리뷰 + 리팩토링
- 문서 업데이트
- 의존성 업데이트
- 보안 취약점 스캔

---

## 리스크 & 대응

| 리스크 | 확률 | 영향 | 대응 |
|---|---|---|---|
| Google Flights Protobuf 구조 변경 | 중 | **중** | L2(Kiwi)가 즉시 대체, Playwright 폴백도 준비 |
| Kiwi.com API 정책/가격 변경 | 중 | 중 | Duffel API 대안 준비, L1+L3로 보완 |
| 항공사 안티봇 강화 (L3) | 높 | 중 | 프록시 다변화, L1+L2로 커버되면 L3 우선도 하향 |
| 프록시 비용 초과 | 중 | 중 | L3는 타겟 항공사만 선별, L1+L2는 프록시 불필요 |
| 소스 간 데이터 불일치 | 높 | 중 | Data Merger에서 교차 검증, 신뢰도 점수 기반 선택 |
| 항공사 법적 경고 | 낮 | 높 | L3만 해당, 법률 자문, robots.txt 존중 |
| DA 모델 정확도 미달 | 중 | 중 | 다중 소스 데이터로 피처 다양화, 앙상블 |
| 크롤링 데이터 품질 저하 | 중 | 중 | 소스 간 교차 검증으로 이상치 탐지 정확도 향상 |

---

## DA 협업 인터페이스

### Dev → DA 제공물

| 제공물 | 형태 | 갱신 주기 |
|---|---|---|
| 가격 이력 데이터 | PostgreSQL `prices` 테이블 | 실시간 |
| 검색 로그 | PostgreSQL `search_history` 테이블 | 실시간 |
| 좌석 스펙 | PostgreSQL `seat_specs` 테이블 | 월 1회 |
| 공항/항공사 메타 | PostgreSQL 시드 테이블 | 필요시 |
| Jupyter 접근 | JupyterHub or 로컬 DB 연결 | 상시 |

### DA → Dev 제공물

| 제공물 | 형태 | 통합 방식 |
|---|---|---|
| 가격 예측 모델 | pickle/joblib 파일 | `packages/ml/` 에 배치, API에서 로딩 |
| 추천 점수 함수 | Python 함수/클래스 | `packages/ml/scoring.py` |
| 최적 구매 시점 | DB 테이블 or API | `booking_time_analysis` 테이블 |
| 경로 최적화 | Python 함수 | `packages/ml/routing.py` |
| 피처 파이프라인 | Python 스크립트 | Celery task로 스케줄링 |

### 협업 규칙

1. **브랜치 전략**: `main` ← `dev` ← `feature/*` (Perry), `da/*` (DA)
2. **모델 버전 관리**: `packages/ml/models/v{N}/` 디렉토리
3. **인터페이스 계약**: `packages/core/schemas/` 에 공유 스키마 정의
4. **주간 싱크**: 매주 1회 진행 상황 + 다음 주 계획 공유
5. **데이터 요청**: DA가 새 피처/데이터 필요 시 GitHub Issue로 요청

---

*최종 수정: 2026-02-13*
