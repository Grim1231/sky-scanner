# M5: 글로벌 항공사 크롤러 계획

## 목표

한국 출발 경유/환승 항공편을 커버하는 전세계 주요 허브 항공사 크롤러 구축.
L2 (직접 HTTP) 우선, 불가능한 경우 L3 (Playwright headless browser) 사용.

---

## 현재 완료된 크롤러 (M5 이전 포함)

### L1 메타검색
| # | 소스 | 방식 | 상태 |
|---|------|------|------|
| 1 | Google Flights | L1 Protobuf | 완료 |
| 2 | Kiwi Tequila | L2 API | 완료 (키 미보유) |

### 한국 LCC (7/7 완료)
| # | 항공사 | 코드 | 방식 | 바이패스 기법 |
|---|--------|------|------|---------------|
| 3 | 제주항공 | 7C | L2 | sec.jejuair.net JSON API |
| 4 | 이스타항공 | ZE | L2 | kraken.eastarjet.com (Navitaire) 세션 |
| 5 | 에어프레미아 | YP | L3 | Playwright CF bypass |
| 6 | 에어서울 | RS | L2 | primp TLS + searchFlightInfo.do |
| 7 | 진에어 | LJ | L2 | fare.jinair.com 공개 S3 버킷 |
| 8 | 티웨이항공 | TW | L2 | tagency.twayair.com (여행사 포털) |
| 9 | 에어부산 | BX | L2 | Naver Yeti UA CF 화이트리스트 |

### GDS
| # | 소스 | 방식 | 상태 |
|---|------|------|------|
| 10 | Amadeus | L2 SDK | 완료 (test 환경) |

---

## M5 신규 크롤러 (커밋 완료)

### L2 직접 크롤링 성공
| # | 항공사 | 코드 | 허브 | 방식 | 테스트 결과 | 커밋 |
|---|--------|------|------|------|-------------|------|
| 11 | LOT 폴란드항공 | LO | WAW | L2 primp — `watchlistPriceBoxesSearch.json` | Economy 1,011,900 KRW | 5f74566 |
| 12 | EVA 에바항공 | BR | TPE | L2 primp — `getBestPrices.ashx` 세션 | ~300일 최저가, 9,141 TWD | 5f74566 |
| 13 | Singapore Airlines | SQ | SIN | L2 httpx — NDC API (API key 인증) | recommendations 파싱 성공 | 7ff9416 |
| 14 | Air New Zealand | NZ | AKL | L2 primp — EveryMundo airTrfx Sputnik | AKL→NRT 5편, 604 NZD | 7ff9416 |
| 15 | Vietnam Airlines | VN | SGN/HAN | L2 primp — middleware API (schedule+fare) | SGN→ICN 18편, 10,874,000 VND | 510f8b7 |
| 16 | Philippine Airlines | PR | MNL | L2 httpx — flight status API (schedule only) | MNL→ICN 2편 | 510f8b7 |
| 17 | Hainan Airlines | HU | PEK | L2 httpx — fare-trends HMAC-SHA1 (국내선만) | PEK→HAK 136일, 199-4190 CNY | 510f8b7 |
| 18 | Ethiopian Airlines | ET | ADD | L2 primp — EveryMundo Sputnik (NZ와 동일) | ADD→DXB 5편, 72,195 ETB | — |
| 19 | Cathay Pacific | CX | HKG | L2 primp — timetable + histogram (Akamai) | health OK, 검색 406/302 | — |
| 20 | Malaysia Airlines | MH | KUL | L2 primp — AEM lowFares 엔드포인트 (인증 불필요) | KUL→SIN 153일, 260-357 MYR | — |

### 공식 API / L3 크롤러 (API 키 등록 또는 브라우저 필요)
| # | 항공사 | 코드 | 허브 | 방식 | 비고 | 커밋 |
|---|--------|------|------|------|------|------|
| 18 | Lufthansa Group | LH/LX/OS | FRA/ZRH/VIE | 공식 API (OAuth2) | developer.lufthansa.com 등록 필요 | 5f74566 |
| 19 | Air France-KLM | AF/KL | CDG/AMS | L3 Playwright GraphQL | 한국 IP → klm.co.kr 리다이렉트 문제 | 5f74566 |
| 20 | Turkish Airlines | TK | IST | L2 primp (GET만, POST 차단) | Akamai `_abck` 센서가 POST 차단 | 5f74566 |

### 탐색 실패 (참고용)
| 항공사 | 코드 | 이유 |
|--------|------|------|
| Garuda Indonesia | GA | `web-api.garuda-indonesia.com` 504 타임아웃, JS 번들에서 API 패턴 미발견 |
| Saudia | SV | Imperva WAF + CORS 차단, dapi.saudia.com JWT 세션 필요 → L3 필요 |

---

## 남은 작업 (Phase별)

### Phase A: L2 전환 (공식 API → 직접 크롤링)

#### A-1. Turkish Airlines (TK) — L2 전환 [최우선]
- **현황**: `/api/v1/availability/*` API 완전 노출, primp 접근 가능
- **동작 확인**: `booking/locations`, `nearest-airport`, `pax-type-codes`, `parameters`, `translations`
- **남은 과제**: `/api/v1/availability/cheapest-prices` POST body 형식 파악
  - Error-DS-30038 반환 = body 형식 불일치
  - Chrome DevTools에서 실제 검색 수행 → XHR body 캡처 필요
- **필요 헤더**: `x-platform: WEB`, `x-clientid: <uuid>`, `x-bfp: <hex>`, `x-country: int`
- **예상 난이도**: ★★☆ (API 구조 파악 완료, body만 확인하면 됨)

#### A-2. Air France/KLM (AF/KL) — GraphQL L2 전환
- **현황**: GraphQL `/gql/v1` persisted query 발견
- **남은 과제**: 검색 query의 `sha256Hash` 캡처
  - Chrome DevTools에서 KLM 검색 → GraphQL request 캡처
- **필요 헤더**: `afkl-travel-host: KL`, `afkl-travel-market`, `x-aviato-host`
- **예상 난이도**: ★★★ (persisted query hash + Akamai)

#### A-3. Lufthansa Group (LH/LX/OS) — L2 불가 → 공식 API 유지 또는 L3
- **현황**: AEM 웹 컴포넌트 기반, XHR 엔드포인트 없음
- **옵션 1**: 공식 API 키 등록 (무료 tier, flight-schedules 제공)
- **옵션 2**: L3 Playwright (어려움 — AEM 렌더링 + Cloudflare)
- **예상 난이도**: ★☆☆ (공식 API) / ★★★★ (L3)

### Phase B: 아시아 주요 허브 항공사

> 아시아 연구 결과 반영 (2026-02-15). PSS = Passenger Service System.

| 항공사 | 코드 | 허브 | 얼라이언스 | PSS | 안티봇 | 추천 방식 | 난이도 |
|--------|------|------|------------|-----|--------|-----------|--------|
| **Singapore Airlines** | SQ | SIN | Star | Amadeus Altea | 보통 | **~~L2 NDC API~~ 완료!** | ★☆☆ ✅ |
| ~~Garuda Indonesia~~ | GA | CGK | SkyTeam | Amadeus Altea | 낮음 | ~~L2 탐색~~ (504 타임아웃, Amadeus fallback) | ★★☆ ❌ |
| **Vietnam Airlines** | VN | SGN/HAN | SkyTeam | Amadeus Altea | 낮음 (Imperva) | **~~L2 탐색~~ 완료!** (middleware API) | ★★☆ ✅ |
| **Philippine Airlines** | PR | MNL | — | Amadeus Altea | 미확인 | **~~L2 탐색~~ 완료!** (flight status API, 스케줄만) | ★★☆ ✅ |
| **Malaysia Airlines** | MH | KUL | oneworld | Amadeus Altea | 보통 | **~~L2 탐색~~ 완료!** (AEM lowFares) | ★★☆ ✅ |
| **Cathay Pacific** | CX | HKG | oneworld | Amadeus Altea | 보통 | **L2 부분 완료** (health OK, search 406/302) | ★★★ ⚠️ |
| Thai Airways | TG | BKK | Star | Amadeus Altea | 높음 (403) | L3 Playwright | ★★★★ |
| JAL (일본항공) | JL | NRT/HND | oneworld | Amadeus Altea | 높음 | L3 Playwright | ★★★★ |
| **ANA (전일본공수)** | NH | NRT/HND | Star | Amadeus Altea | **Akamai Bot Manager (확인)** | L3 Playwright | ★★★★★ |
| China Eastern | MU | PVG | SkyTeam | **TravelSky** | Alibaba 안티봇 | L3 또는 Amadeus | ★★★★ |
| China Southern | CZ | CAN | SkyTeam | **TravelSky** | Alibaba 안티봇 | L3 또는 Amadeus | ★★★★ |
| **Hainan Airlines** | HU | PEK | — | **TravelSky** | 보통 | **~~L2 탐색~~ 완료!** (fare-trends HMAC-SHA1, 국내선만) | ★★☆ ✅ |
| **Ethiopian Airlines** | ET | ADD | Amadeus Altea | Akamai (허용적) | **~~L2 탐색~~ 완료!** (EveryMundo Sputnik, NZ와 동일 API) | ★★☆ ✅ |
| **Malaysia Airlines** | MH | KUL | Amadeus Altea | 보통 | **~~L2 탐색~~ 완료!** (AEM lowFares, 인증 불필요, 153일) | ★★☆ ✅ |
| **Cathay Pacific** | CX | HKG | Amadeus Altea | Akamai + PerimeterX | **L2 부분 완료** (health OK, 검색 406/302 — L3 필요) | ★★★ ⚠️ |

#### Singapore Airlines NDC API (핵심 발견!)
- **포털**: [developer.singaporeair.com](https://developer.singaporeair.com/)
- **무료 등록**, API 키 즉시 발급
- **제공 API**: AirShopping (검색), OfferPrice (가격), SeatAvailability, OrderCreate
- IATA NDC 표준 → 다른 NDC 항공사에도 패턴 재사용 가능

#### Cathay Pacific NDC API
- **포털**: [developers.cathaypacific.com](https://developers.cathaypacific.com/)
- OpenJaw t-Retail NDC 기반
- **trade partner 등록 필요** (여행사/어그리게이터)

### Phase C: 중동 허브 항공사

> 중동/미주 연구 결과 반영 (2026-02-15). 13개 중 11개가 Akamai 사용.

| 항공사 | 코드 | 허브 | PSS | 안티봇 | 추천 방식 | 난이도 |
|--------|------|------|-----|--------|-----------|--------|
| Turkish Airlines | TK | IST | TROYA (자체) | Akamai | **L2 (Phase A)** | ★★☆ |
| ~~Saudia~~ | SV | JED/RUH | Amadeus Altea | **Imperva** + CORS | ~~L2 탐색~~ (CORS 차단, L3 필요) | ★★★ ❌ |
| Emirates | EK | DXB | 자체 (AWS) | Akamai | L2 hard (developer.emirates.group 존재) | ★★★★ |
| Qatar Airways | QR | DOH | Amadeus Altea | Akamai (403) | L3 Playwright | ★★★★ |
| Etihad | EY | AUH | Amadeus Altea | Akamai (HTTP/2 연결 차단) | L3 극도 어려움 | ★★★★★ |

### Phase D: 미주/오세아니아 허브

| 항공사 | 코드 | 허브 | PSS | 안티봇 | 추천 방식 | 난이도 |
|--------|------|------|-----|--------|-----------|--------|
| **Air New Zealand** | NZ | AKL | Carina (자체) | **CloudFront (Akamai 없음!)** | **~~L2 탐색~~ 완료!** | ★★☆ ✅ |
| **Ethiopian Airlines** | ET | ADD | Amadeus Altea | Akamai (허용적) | **~~L2 탐색~~ 완료!** (EveryMundo Sputnik) | ★★☆ ✅ |
| Delta Air Lines | DL | ATL/DTW | Deltamatic (자체) | Akamai (444) | L2 hard (apiportal.delta.com 존재) | ★★★★ |
| LATAM Airlines | LA | SCL | Amadeus Altea | Akamai | L3 Playwright | ★★★★ |
| American Airlines | AA | DFW/MIA | Sabre | Akamai (403) | L3 Playwright | ★★★★★ |
| Qantas | QF | SYD | Amadeus Altea | Akamai (봇 쿠키 5개) | L3 Playwright | ★★★★★ |
| United Airlines | UA | SFO/EWR | SHARES (자체) | Akamai (HTTP/2 차단) | L3 극도 어려움 | ★★★★★ |
| Air Canada | AC | YYZ/YVR | Amadeus Altea | Akamai + **소송 전례** | ⚠️ 회피 권장 | ★★★★★ |

> ⚠️ Air Canada는 Seats.aero를 스크래핑으로 소송한 전례가 있어 직접 크롤링 회피 권장. Amadeus fallback 사용.

---

## 실행 우선순위

### 완료 ✅
1. ~~TK L2 전환~~: POST는 Akamai 차단, GET만 동작 → L2 부분 완료
2. ~~커밋~~: LOT, EVA Air, TK, LH, AF-KLM (5f74566)
3. ~~SQ NDC API~~: 크롤러 완성 (7ff9416)
4. ~~NZ L2 탐색~~: EveryMundo airTrfx API 발견, 크롤러 완성 (7ff9416)
5. ~~GA, SV 탐색~~: 둘 다 L2 불가 확인 (Amadeus fallback)

### 다음 실행
6. ~~**Phase B 탐색**: VN, PR, HU~~ 완료 (VN middleware + PR flight status + HU fare-trends)
7. ~~**Phase B 남은 대상**: ET, MH, CX~~ 완료 (ET Sputnik + MH AEM + CX 부분)
8. **CX 개선**: Cathay Pacific timetable 406 → query params 조정 또는 L3 Playwright
9. **AF/KLM 개선**: VPN/프록시 없이 L3 Playwright 안정화
8. **LH 공식 API**: developer.lufthansa.com 수동 등록
9. **TK 공식 API**: developer.turkishairlines.com 수동 등록 (L2 POST 차단 fallback)

### 중기 (2-4주)
8. **L3 프레임워크 구축**: Playwright 기반 범용 크롤러 베이스
9. **아시아 L3**: CX, TG, NH, JL
10. **중동 L3**: EK, QR
11. **ET, SV L2**: Ethiopian (Akamai 허용적) + Saudia (Imperva) 탐색

### 장기 (Amadeus fallback)
12. **미주 항공사**: UA, DL, AA, QF → Akamai 매우 강력, Amadeus production 키로 커버
13. **중국 항공사**: MU, CZ → Amadeus 또는 중국 OTA 경유
14. **AC 회피**: Air Canada → 소송 전례, Amadeus만 사용

---

## 기술 스택 정리

| 레벨 | 도구 | 용도 |
|------|------|------|
| L1 | Google Protobuf | 메타검색 (최대 커버리지) |
| L2 | primp (Chrome TLS) | 직접 HTTP API 호출 |
| L2 | httpx | 공식 API (OAuth2/API Key) |
| L3 | Playwright | headless browser (CF/Akamai bypass) |
| Fallback | Amadeus GDS | 400+ 항공사 (API 키 필요) |

## 안티봇 바이패스 기법 요약

| 기법 | 대상 WAF | 성공 사례 |
|------|----------|-----------|
| Naver Yeti UA | Cloudflare | Air Busan (BX) |
| primp TLS (chrome_131) | Cloudflare/Akamai | Air Seoul, LOT, EVA Air, T'way |
| 여행사 포털 우회 | Akamai | T'way (tagency.twayair.com) |
| 공개 S3/CDN | 없음 | Jin Air (fare.jinair.com) |
| Navitaire 세션 | 없음 | Eastar Jet (kraken.eastarjet.com) |
| Playwright headless | Cloudflare | Air Premia (YP) |
| GraphQL persisted query | Akamai | AF/KLM (진행 중) |
| Next.js API 리버싱 | Akamai | Turkish Airlines (진행 중) |
| 미들웨어 API 직접 호출 | Imperva 우회 | Vietnam Airlines (integration-middleware-website) |
| Flight status API | 없음 | Philippine Airlines (pal/flights/v1/status) |
| Mobile HMAC-SHA1 서명 | 없음 | Hainan Airlines (app.hnair.com fare-trends) |
| EveryMundo Sputnik API (공유 키) | Cloudflare | Ethiopian Airlines (NZ와 동일 em-api-key) |
| AEM Sling 서블릿 직접 호출 | Cloudflare | Malaysia Airlines (/bin/mh/revamp/lowFares) |
| Akamai 웜업 + API 호출 | Akamai | Cathay Pacific (timetable/histogram, 부분 동작) |

---

## 목표 커버리지

현재 **23개 크롤러** 운영 중 (L1 2 + Korean LCC 7 + GDS 1 + Global 13).
Amadeus fallback으로 400+ 항공사 추가 커버.
한국 출발 주요 경유 허브 (IST, DOH, SIN, HKG, NRT, FRA, CDG, AMS, BKK, TPE, WAW, KUL, ADD) 전부 포함.
