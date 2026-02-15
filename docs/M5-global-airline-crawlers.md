# M5: 글로벌 항공사 크롤러

## 목표

한국 출발 경유/환승 항공편을 커버하는 전세계 주요 허브 항공사 크롤러 구축.
L2 (직접 HTTP) 우선, 불가능한 경우 L3 (Playwright headless browser) 사용.

---

## 전체 크롤러 현황 (2026-02-15 기준)

### L1 메타검색 (2개)
| # | 소스 | 방식 | 상태 |
|---|------|------|------|
| 1 | Google Flights | L1 Protobuf | ✅ 완료 |
| 2 | Kiwi Tequila | L2 API | ✅ 완료 (키 미보유) |

### 한국 LCC (7/7 완료)
| # | 항공사 | 코드 | 방식 | 바이패스 기법 |
|---|--------|------|------|---------------|
| 3 | 제주항공 | 7C | L2 | sec.jejuair.net JSON API |
| 4 | 이스타항공 | ZE | L2 | kraken.eastarjet.com (Navitaire) 세션 |
| 5 | 에어프레미아 | YP | L3 | Playwright CF bypass → cookie 추출 → httpx |
| 6 | 에어서울 | RS | L2 | primp TLS + searchFlightInfo.do |
| 7 | 진에어 | LJ | L2 | fare.jinair.com 공개 S3 버킷 |
| 8 | 티웨이항공 | TW | L2 | tagency.twayair.com (여행사 포털) |
| 9 | 에어부산 | BX | L2 | Naver Yeti UA CF 화이트리스트 |

### GDS (1개)
| # | 소스 | 방식 | 상태 |
|---|------|------|------|
| 10 | Amadeus | L2 SDK | ✅ 완료 (test 환경) |

### M5 글로벌 항공사 — L2 완료 (14개)
| # | 항공사 | 코드 | 허브 | 방식 | 데이터 종류 | 커밋 |
|---|--------|------|------|------|-------------|------|
| 11 | LOT 폴란드항공 | LO | WAW | L2 primp | 가격 캘린더 (KRW) | 5f74566 |
| 12 | EVA 에바항공 | BR | TPE | L2 primp | ~300일 최저가 (TWD) | 5f74566 |
| 13 | Singapore Airlines | SQ | SIN | L2 httpx NDC | 스케줄+추천 | 7ff9416 |
| 14 | Air New Zealand | NZ | AKL | L2 primp Sputnik | 최저가 (NZD) | 7ff9416 |
| 15 | Vietnam Airlines | VN | SGN/HAN | L2 primp middleware | 스케줄+운임 (VND) | 510f8b7 |
| 16 | Philippine Airlines | PR | MNL | L2 httpx | 스케줄만 | 510f8b7 |
| 17 | Hainan Airlines | HU | PEK | L2 httpx HMAC | 국내선 운임 (CNY) | 510f8b7 |
| 18 | Ethiopian Airlines | ET | ADD | L2 primp Sputnik | 최저가 (ETB) | c721448 |
| 19 | Cathay Pacific | CX | HKG | L2 primp | histogram+open-search (HKD) | 3cbb377 |
| 20 | Malaysia Airlines | MH | KUL | L2 primp AEM | 153일 최저가 (MYR) | c721448 |
| 21 | Emirates | EK | DXB | L2 primp | 프로모션 운임 4 캐빈 (KRW) | 3cbb377 |
| 22 | Lufthansa Group | LH/LX/OS | FRA/ZRH/VIE | L2 httpx 공식 API | OAuth2 스케줄 | 3cbb377 |
| 23 | Turkish Airlines | TK | IST | L2 primp + 공식 API 대기 | L2 가격+스케줄, 공식 API 듀얼모드 | 4ac5490 |
| 24 | JAL 일본항공 | JL | NRT/HND | L2 primp Sputnik | 최저가 (NZ/ET와 동일 패턴) | — (구현 중) |

### M5 L3 Playwright — 구현 필요
| # | 항공사 | 코드 | 허브 | L2 실패 이유 | L3 전략 | 상태 |
|---|--------|------|------|-------------|---------|------|
| 25 | Air France-KLM | AF/KL | CDG/AMS | GraphQL POST Akamai 차단 | Playwright로 검색 → DOM 파싱 | 🔧 구현 중 |
| 26 | Thai Airways | TG | BKK | SSR HTML, API 없음 | Playwright 검색 페이지 | 🔧 구현 중 |
| 27 | ANA 전일본공수 | NH | NRT/HND | api.ana.co.jp 401 인증 | Playwright 검색 페이지 | 🔧 구현 중 |
| 28 | Qatar Airways | QR | DOH | qoreservices 401 인증 | Playwright 검색 페이지 | 🔧 구현 중 |

### L2 탐색 실패 → Amadeus fallback
| 항공사 | 코드 | 실패 이유 | 대안 |
|--------|------|-----------|------|
| Garuda Indonesia | GA | 504 타임아웃 | Amadeus |
| Saudia | SV | Imperva + CORS | Amadeus |
| Etihad | EY | Akamai HTTP/2 차단 | Amadeus |
| China Eastern | MU | TravelSky + Alibaba 봇 감지 | Amadeus |
| China Southern | CZ | TravelSky + Alibaba 봇 감지 | Amadeus |
| Delta | DL | Akamai 444 | Amadeus |
| American Airlines | AA | Akamai 403 | Amadeus |
| United Airlines | UA | Akamai HTTP/2 차단 | Amadeus |
| Qantas | QF | Akamai 봇 쿠키 5개 | Amadeus |
| Air Canada | AC | Akamai + ⚠️ **소송 전례** | Amadeus만 |

---

## 커밋 히스토리

| 커밋 | 날짜 | 내용 | 파일 수 |
|------|------|------|---------|
| `5f74566` | 02-15 | LOT, EVA Air, TK L2, LH Group, AF-KLM 초기 | 19 |
| `7ff9416` | 02-15 | SQ NDC API + NZ airTrfx Sputnik | 10 |
| `510f8b7` | 02-15 | VN middleware + PR flight status + HU fare-trends | 12 |
| `c721448` | 02-15 | ET Sputnik + CX 초기 + MH AEM | 12 |
| `3cbb377` | 02-15 | LH API 수정 + CX histogram/open-search + EK L2 | 10 |
| `4ac5490` | 02-15 | TK 공식 API 듀얼모드 + DataSource.OFFICIAL_API | 7 |

---

## 기술 상세

### L2 엔드포인트 레퍼런스

| 항공사 | 엔드포인트 | 인증 | 특이사항 |
|--------|-----------|------|----------|
| LO | `lot.com/api/lo/watchlistPriceBoxesSearch.json` | 없음 | primp 필요 |
| BR | `evaair.com/getBestPrices.ashx` | 세션 쿠키 | warm-up GET 필요 |
| SQ | NDC API (직접 httpx) | API key | developer.singaporeair.com |
| NZ | `openair-california.airtrfx.com/.../nz/fares/search` | em-api-key | EveryMundo Sputnik |
| ET | 위와 동일 URL, tenant=`et` | 동일 키 | NZ와 완전 동일 패턴 |
| JL | 위와 동일 URL, tenant=`jl` | 동일 키 | NZ/ET와 동일 패턴 |
| VN | `www.vietnamairlines.com/api/integration-middleware-website/*` | 없음 | primp 필요 |
| PR | `api.philippineairlines.com/pal/flights/v1/status/*` | 없음 | 스케줄만 |
| HU | `app.hnair.com/app/fare-trends` | HMAC-SHA1 서명 | 국내선만 |
| CX | `book.cathaypacific.com/.../histogram` + `open-search` | 없음 | GET, 대문자 params |
| MH | `www.malaysiaairlines.com/bin/mh/revamp/lowFares` | 없음 | AEM Sling 서블릿 |
| EK | `www.emirates.com/service/featured-fares` | 없음 | primp warm-up |
| LH | `api.lufthansa.com/v1/operations/schedules/{o}/{d}/{date}` | OAuth2 | Client ID/Secret |
| TK (L2) | `turkishairlines.com/api/v1/availability/*` | 없음 | Akamai POST 차단 |
| TK (공식) | `api.turkishairlines.com/getAvailability` | apikey+secret | 권한 요청 발송됨 |

### LH Group API 인증
- Client ID: `hh5urays7eppuv6hn6tx99fvx`
- Client Secret: `KjENp79k85`
- 무료 LH Public plan (5 calls/sec, 1000 calls/hour)
- OAuth2 token 36시간 유효, 60초 전 자동 갱신

### TK 공식 API
- 포털: `developer.apim.turkishairlines.com`
- 계정: `knsol2` / TOTP `GYYFEV3RIRVWGN3INNWGSYTDKQZUM6DU`
- 신규 계정 → 제품 목록 비어있음 → 지원팀에 권한 요청 이메일 발송 완료
- `CRAWLER_TK_USE_OFFICIAL_API=true` 시 공식 API 우선, 실패 시 L2 자동 폴백

### EveryMundo Sputnik API (NZ/ET/JL 공유)
- URL: `openair-california.airtrfx.com/airfare-sputnik-service/v3/{tenant}/fares/search`
- API Key: `HeQpRjsFI5xlAaSx2onkjc1HTK0ukqA1IrVvd5fvaMhNtzLTxInTpeYB1MK93pah`
- POST body: `{currency, departureDaysInterval:{min,max}, routesLimit, faresLimit, faresPerRoute, origin}`
- 반환: airline, route, departureDate, totalPrice, currencyCode, fareClass

### CX Histogram/Open-search
- Histogram: `GET book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/histogram`
  - Params: `ORIGIN`, `DESTINATION`, `SITE=CBEUCBEU`, `TYPE=MTH`, `LANGUAGE=GB`, `CABIN`
  - 월별 최저가 반환
- Open-search: `GET .../api/instant/open-search`
  - Params: `ORIGINS`, `SITE`, `LANGUAGE`
  - 84+ 목적지 일괄 반환

---

## L3 Playwright 전략

### 공통 패턴 (Air Premia L3 참조)
1. Playwright Chromium headless → 검색 페이지 방문 → WAF challenge 해결
2. **전략 A (Cookie 추출)**: CF/Akamai challenge 해결 후 쿠키 추출 → httpx로 API 호출
3. **전략 B (DOM 파싱)**: 검색 폼 자동 입력 → 검색 실행 → 결과 DOM에서 데이터 추출

### 대상별 L3 전략

#### AF/KL (Air France-KLM) — 전략 B
- 검색 URL: `klm.com/search/offers` 또는 `airfrance.com/search/offers`
- SPA: React (Aviato framework)
- WAF: Akamai Bot Manager (POST 차단, HTTP/2 에러)
- 접근: Playwright로 검색 페이지 로드 → 검색 폼 입력 → GraphQL 자동 실행 → response intercept

#### TG (Thai Airways) — 전략 B
- 검색 URL: `thaiairways.com/en/booking/flight-search.page`
- SSR HTML 기반 (Amadeus OSCI)
- WAF: Akamai (403 intermittent)
- 접근: Playwright로 form submit → 결과 페이지 DOM 파싱

#### NH (ANA) — 전략 A or B
- 검색 URL: `ana.co.jp/ja/jp/book-plan/` or `aswbe-i.ana.co.jp`
- WAF: Akamai Bot Manager
- Flight status: `flics.ana.co.jp/fs/pc/search` (HTTP, no HTTPS)
- 접근: Playwright → cookie 추출 → booking API or DOM 파싱

#### QR (Qatar Airways) — 전략 B
- 검색 URL: `qatarairways.com/en/booking.html`
- SPA: Angular
- WAF: Akamai (403)
- 접근: Playwright로 검색 → response intercept (`qoreservices.qatarairways.com`)

---

## 안티봇 바이패스 기법 요약

| 기법 | 대상 WAF | 성공 사례 |
|------|----------|-----------|
| Naver Yeti UA | Cloudflare | Air Busan (BX) |
| primp TLS (chrome_131) | Cloudflare/Akamai | Air Seoul, LOT, EVA Air, T'way, VN, CX, MH, EK |
| 여행사 포털 우회 | Akamai | T'way (tagency.twayair.com) |
| 공개 S3/CDN | 없음 | Jin Air (fare.jinair.com) |
| Navitaire 세션 | 없음 | Eastar Jet (kraken.eastarjet.com) |
| Playwright cookie 추출 | Cloudflare | Air Premia (YP) |
| EveryMundo Sputnik (공유 키) | Cloudflare | NZ, ET, JL |
| 미들웨어 API 직접 호출 | Imperva 우회 | Vietnam Airlines |
| Flight status API | 없음 | Philippine Airlines |
| Mobile HMAC-SHA1 서명 | 없음 | Hainan Airlines |
| AEM Sling 서블릿 | Cloudflare | Malaysia Airlines |
| Akamai warm-up + API | Akamai | CX histogram, EK featured-fares |
| OAuth2 공식 API | 없음 | Lufthansa Group, TK (대기) |

---

## 커버리지 요약

- **총 크롤러**: 28개 (L1 2 + Korean LCC 7 + GDS 1 + Global L2 14 + Global L3 4)
- **L2 완료**: 24개 (10개 기존 + 14개 M5 신규)
- **L3 구현 중**: 4개 (AF/KL, TG, NH, QR)
- **Amadeus fallback**: GA, SV, EY, MU, CZ, DL, AA, UA, QF, AC (10개)
- **한국 출발 주요 허브 커버리지**:
  IST ✅ DOH 🔧 SIN ✅ HKG ✅ NRT ✅ FRA ✅ CDG 🔧 AMS 🔧 BKK 🔧 TPE ✅ WAW ✅ KUL ✅ ADD ✅ DXB ✅
