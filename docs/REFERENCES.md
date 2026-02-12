# 오픈소스 레퍼런스 분석

> `references/` 디렉토리에 클론된 4개 프로젝트 분석 요약

## 핵심 요약

| 프로젝트 | 스타 | 접근 방식 | 배울 점 |
|---|---|---|---|
| **fast-flights** | 667 | Protobuf + HTTP (브라우저 없이) | 가장 빠르고 안정적. Protobuf 디코딩이 핵심 |
| **flight-analysis** | 152 | Selenium + pandas | 다중 경로 조합, 캐싱, 분석 파이프라인 |
| **google-flights-scraper** | - | Playwright UI 자동화 | 쿠키/동의 처리, CLI, 탄소배출 데이터 |
| **flight-price-prediction** | - | Selenium + Random Forest ML | 55K 데이터 기반 가격 예측, MAE $62 달성 |

---

## 1. fast-flights (AWeirdDev/flights)

**경로:** `references/flights/`

### 핵심 발견

Google Flights는 내부적으로 **Protobuf** (Protocol Buffers)를 사용한다. URL의 `?tfs=` 파라미터가 Base64 인코딩된 Protobuf 메시지다. 이걸 역으로 구성하면 **브라우저 없이 HTTP 요청만으로** 항공편 데이터를 가져올 수 있다.

### 아키텍처

```
FlightData(출발지, 도착지, 날짜)
    ↓
Protobuf 직렬화 → Base64 인코딩
    ↓
HTTP GET google.com/travel/flights?tfs={encoded}
    ↓
HTML 파싱 (selectolax) → 구조화된 데이터
```

### 주목할 기술

- **primp**: Chrome 126을 흉내내는 HTTP 클라이언트 (TLS 핑거프린트 위장)
- **selectolax**: C 기반 HTML 파서 (BeautifulSoup보다 훨씬 빠름)
- **3단계 폴백**: HTTP → Playwright 로컬 → Bright Data 프록시
- **EU 쿠키 임베딩**: 동의 팝업 우회를 위한 기본 쿠키 설정

### 우리 프로젝트에 적용할 것

- Google Flights Protobuf 패턴을 그대로 활용 가능
- selectolax 도입 (파싱 성능 향상)
- 다단계 폴백 전략 채택
- primp 또는 유사한 TLS 위장 HTTP 클라이언트 사용

---

## 2. flight-analysis (celebi-pkg/flight-analysis)

**경로:** `references/flight-analysis/`

### 핵심 발견

다양한 **여행 패턴**을 코드로 표현하는 좋은 추상화를 보여준다.

### 지원하는 여행 유형

| 유형 | 예시 | 설명 |
|---|---|---|
| One-way | JFK → IST | 편도 |
| Round-trip | JFK ↔ IST | 왕복 |
| Chain-trip | JFK → IST → RDU → SFO | 다구간 (복귀 없음) |
| Perfect-chain | JFK → IST → CDG → JFK | 다구간 순환 |

### 주목할 패턴

```python
# Scrape 객체를 + 연산자로 결합
result = Scrape("JFK", "IST", "2026-04-15") + Scrape("IST", "CDG", "2026-04-20")
```

- pandas DataFrame으로 결과 반환 → DA가 바로 분석 가능
- SQLAlchemy로 DB 저장 지원
- 캐싱 시스템 내장

### 우리 프로젝트에 적용할 것

- 여행 유형 추상화 (편도/왕복/다구간)
- 검색 결과를 pandas DF로 출력하는 인터페이스 → DA 협업 용이
- 캐싱 전략 참고

---

## 3. google-flights-scraper (hugoglvs)

**경로:** `references/google-flights-scraper/`

### 핵심 발견

Playwright로 Google Flights UI를 직접 조작하는 방식. 가장 **사용자 행동에 가까운** 크롤링.

### 수집 데이터

- 출발/도착 시간 및 공항
- 항공사, 소요시간, 경유 횟수
- **CO2 배출량** 및 평균 대비 비교
- 가격 및 가격 유형
- 경유지 공항 상세

### 주목할 기술

- Click 라이브러리로 CLI 제공
- `slow_mo=100`으로 동적 콘텐츠 로딩 안정화
- headless 모드 지원 (서버 배포용)

### 우리 프로젝트에 적용할 것

- Playwright UI 자동화 패턴 (쿠키 동의, 날짜 선택기 조작)
- CO2 배출 데이터 수집 로직
- CLI 인터페이스 설계 (Click)

---

## 4. flight-price-prediction (MeshalAlamr)

**경로:** `references/flight-price-prediction/`

### 핵심 발견

Kayak 크롤링 → 55,363건 데이터 수집 → Random Forest로 **MAE $62** 달성. DA 팀원에게 가장 직접적인 레퍼런스.

### ML 피처

| 피처 | 타입 | 가격 상관관계 |
|---|---|---|
| 출발 공항 | Categorical | 중간 |
| 도착 공항 | Categorical | 중간 |
| 경유 횟수 | Numerical | 높음 |
| 항공사별 평균가 | Numerical | 높음 |
| 비행 시간 | Numerical | 높음 |

### 모델 성능

- **알고리즘**: Random Forest Regression
- **MAE**: $61.87
- **RMSE**: $201.02
- 학습 데이터: 55,363건 (4개 노선)

### 우리 프로젝트에 적용할 것

- 초기 가격 예측 모델의 베이스라인으로 활용
- 피처 엔지니어링 참고 (특히 항공사별 평균가)
- 데이터 수집 규모 기준 (최소 50K+ 필요)
- Kayak HTML 파싱 패턴 참고

---

## 종합: 우리 프로젝트에 채택할 전략

```
크롤링 계층:

Layer 1 (최우선): fast-flights 방식 — Protobuf + HTTP
  → Google Flights 데이터를 브라우저 없이 초고속 수집
  → primp/selectolax 활용

Layer 2 (보조): Playwright UI 자동화
  → 항공사 직접 사이트 크롤링 (Google Flights에 없는 가격)
  → 안티봇이 강한 사이트 대응

Layer 3 (폴백): API 연동
  → Kiwi.com Tequila, Duffel 등 어그리게이터 API
  → 크롤링 실패 시 대체 데이터

분석 계층:
  → flight-price-prediction의 RF 모델을 베이스라인으로
  → flight-analysis의 pandas 파이프라인 패턴 채택
  → 점진적으로 LSTM/GRU로 고도화
```
