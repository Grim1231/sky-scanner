# M5: 글로벌 항공사 크롤러

## 목표

한국 출발 경유/환승 항공편을 커버하는 전세계 주요 허브 항공사 크롤러 구축.
L2 (직접 HTTP) 우선, 불가능한 경우 L3 (Playwright headless browser) 사용.

---

## 전체 크롤러 현황 (2026-02-16 기준)

### E2E 테스트 결과: **28 passed, 1 xfailed (Kiwi), 0 failed**

### L1 메타검색 (2개)
| # | 소스 | 방식 | 상태 |
|---|------|------|------|
| 1 | Google Flights | L1 Protobuf | ✅ 완료 |
| 2 | Kiwi Tequila | L2 API | ⚠️ 키 미보유 (초대제) |

### 한국 LCC (7/7 완료)
| # | 항공사 | 코드 | 방식 | 바이패스 기법 | 테스트 |
|---|--------|------|------|---------------|--------|
| 3 | 제주항공 | 7C | L2 | sec.jejuair.net JSON API | ✅ |
| 4 | 이스타항공 | ZE | L2 | kraken.eastarjet.com (Navitaire) 세션 | ✅ |
| 5 | 에어프레미아 | YP | L2 | `/api/v1/low-fares` 월단위 청킹 | ✅ |
| 6 | 에어서울 | RS | Amadeus | CF WAF `/I/KO/` 완전 차단 → Amadeus GDS fallback | ✅ |
| 7 | 진에어 | LJ | L2 | fare.jinair.com 공개 S3 버킷 | ✅ |
| 8 | 티웨이항공 | TW | L2 | tagency.twayair.com (여행사 포털) | ✅ |
| 9 | 에어부산 | BX | L2 | Naver Yeti UA CF 화이트리스트 | ✅ |

### GDS (1개)
| # | 소스 | 방식 | 상태 |
|---|------|------|------|
| 10 | Amadeus | L2 SDK | ✅ 완료 (test 환경) |

### M5 글로벌 항공사 — L2 완료 (18개, NH/TG/SQ/AF/KL Sputnik 전환 포함)
| # | 항공사 | 코드 | 허브 | 방식 | 데이터 종류 | 테스트 |
|---|--------|------|------|------|-------------|--------|
| 11 | LOT 폴란드항공 | LO | WAW | L2 primp | 가격 캘린더 (KRW) | ✅ |
| 12 | EVA 에바항공 | BR | TPE | L2 primp | ~300일 최저가 (TWD) | ✅ |
| 13 | **Singapore Airlines** | SQ | SIN | **L2 Sputnik** | 500 fares, 44+ 목적지 (KRW) | ✅ |
| 14 | Air New Zealand | NZ | AKL | L2 Sputnik | 최저가 (NZD) | ✅ |
| 15 | Vietnam Airlines | VN | SGN/HAN | L2 primp middleware | 스케줄+운임 (VND) | ✅ |
| 16 | Philippine Airlines | PR | MNL | L2 httpx | 스케줄만 | ✅ |
| 17 | Hainan Airlines | HU | PEK | L2 httpx HMAC | 국내선 운임 (CNY) | ✅ |
| 18 | Ethiopian Airlines | ET | ADD | L2 Sputnik | 최저가 (USD) | ✅ |
| 19 | Cathay Pacific | CX | HKG | L2 primp | histogram+open-search (HKD) | ✅ |
| 20 | Malaysia Airlines | MH | KUL | L2 primp AEM | 153일 최저가 (MYR) | ✅ |
| 21 | Emirates | EK | DXB | L2 primp | 프로모션 운임 4 캐빈 (KRW) | ✅ |
| 22 | Lufthansa Group | LH/LX/OS | FRA/ZRH/VIE | L2 httpx 공식 API | OAuth2 스케줄 | ✅ |
| 23 | **Turkish Airlines** | TK | IST | **L2+L3 Playwright** | L3 폼 자동화 → cheapest-prices intercept | ✅ |
| 24 | JAL 일본항공 | JL | NRT/HND | L2 Sputnik | 최저가 (NZ/ET와 동일 패턴) | ✅ |
| 25 | **ANA 전일본공수** | NH | NRT/HND | **L2 Sputnik** | 495 fares, KRW 가격 (GMP↔HND) | ✅ |
| 26 | **Thai Airways** | TG | BKK | **L2 Sputnik + popular-fares** | Sputnik 500 + popular-fares 12 KRW | ✅ |
| 27 | **Air France-KLM** | AF/KL | CDG/AMS | **L2 Sputnik** | AF+KL 듀얼 tenant, 500 fares (EUR) | ✅ |
| 28 | SQ via Amadeus | SQ | SIN | Amadeus GDS | Amadeus fallback (코드셰어) | ✅ |

### L2/L3 실패 → Amadeus fallback (11개, 전체 검증 완료 ✅)
| 항공사 | 코드 | 실패 이유 | 테스트 노선 | Amadeus 결과 | 검증 |
|--------|------|-----------|------------|-------------|------|
| Qatar Airways | QR | Akamai WAF 403 | ICN→DOH | 39편 (QR 7편) | ✅ |
| Garuda Indonesia | GA | 504 타임아웃 | ICN→CGK | 50편 (GA 3편) | ✅ |
| Saudia | SV | Imperva + CORS | ICN→JED | 50편 (SV 2편) | ✅ |
| Etihad | EY | Akamai HTTP/2 차단 | ICN→AUH | 50편 (EY 3편) | ✅ |
| China Eastern | MU | TravelSky + Alibaba 봇 감지 | ICN→PVG | 50편 (MU 3편) | ✅ |
| China Southern | CZ | TravelSky + Alibaba 봇 감지 | ICN→CAN | 50편 (CZ 10편) | ✅ |
| Delta | DL | Akamai 444 | ICN→SEA | 46편 (코드셰어) | ✅ |
| American Airlines | AA | Akamai 403 | ICN→DFW | 43편 (코드셰어) | ✅ |
| United Airlines | UA | Akamai HTTP/2 차단 | ICN→SFO | 50편 (UA 2편) | ✅ |
| Qantas | QF | Akamai 봇 쿠키 5개 | ICN→SYD | 50편 (QF 2편) | ✅ |
| Air Canada | AC | Akamai + **소송 전례** | ICN→YVR | 42편 (AC 2편) | ✅ |

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
| `e72008f` | 02-15 | 계획 문서 전면 업데이트 | 1 |
| `59e1529` | 02-15 | JL Sputnik + AF/KL·TG·NH·QR L3 Playwright | ~25 |
| `a41e4f9` | 02-15 | L3 Playwright 실제 테스트 + 셀렉터 수정 | ~10 |
| `e79651e` | 02-16 | NH/TG/SQ Sputnik 전환, TK L3 Playwright, RS L3 인프라, E2E 테스트 | ~30 |
| `61b78ed` | 02-16 | AF/KLM Sputnik 전환 — L3 Playwright → L2 Sputnik 대체 | 7 |
| `dee60c1` | 02-16 | Air Premia L2 월단위 날짜 청킹 수정 | 3 |
| `2e01c50` | 02-16 | Air Seoul 테스트 Amadeus GDS로 통합 | 1 |

---

## 기술 상세

### L2 엔드포인트 레퍼런스

| 항공사 | 엔드포인트 | 인증 | 특이사항 |
|--------|-----------|------|----------|
| LO | `lot.com/api/lo/watchlistPriceBoxesSearch.json` | 없음 | primp 필요 |
| BR | `evaair.com/getBestPrices.ashx` | 세션 쿠키 | warm-up GET 필요 |
| SQ | ~~NDC API (직접 httpx)~~ → **Sputnik** | em-api-key | UAT 빈 데이터 → Sputnik 전환 |
| NZ | `openair-california.airtrfx.com/.../nz/fares/search` | em-api-key | EveryMundo Sputnik |
| ET | 위와 동일 URL, tenant=`et` | 동일 키 | NZ와 완전 동일 패턴 |
| JL | 위와 동일 URL, tenant=`jl` | 동일 키 | NZ/ET와 동일 패턴 |
| NH | 위와 동일 URL, tenant=`nh` | 동일 키 | 495 fares, KRW 가격 |
| TG | 위와 동일 URL, tenant=`tg` + popular-fares | 동일 키 | Sputnik 500 + popular-fares 12 |
| SQ | 위와 동일 URL, tenant=`sq` | 동일 키 | 500 fares, 44+ 목적지 |
| AF | 위와 동일 URL, tenant=`af` | 동일 키 | 500 fares, EUR 가격 |
| KL | 위와 동일 URL, tenant=`kl` | 동일 키 | 500 fares, EUR 가격 |
| VN | `www.vietnamairlines.com/api/integration-middleware-website/*` | 없음 | primp 필요 |
| PR | `api.philippineairlines.com/pal/flights/v1/status/*` | 없음 | 스케줄만 |
| HU | `app.hnair.com/app/fare-trends` | HMAC-SHA1 서명 | 국내선만 |
| CX | `book.cathaypacific.com/.../histogram` + `open-search` | 없음 | GET, 대문자 params |
| MH | `www.malaysiaairlines.com/bin/mh/revamp/lowFares` | 없음 | AEM Sling 서블릿 |
| EK | `www.emirates.com/service/featured-fares` | 없음 | primp warm-up |
| LH | `api.lufthansa.com/v1/operations/schedules/{o}/{d}/{date}` | OAuth2 | Client ID/Secret |
| TK (L3) | `turkishairlines.com/api/v1/availability/*` | 없음 | L2 POST 차단 → L3 Playwright 폼 자동화 |
| TK (공식) | `api.turkishairlines.com/getAvailability` | apikey+secret | 권한 요청 발송됨 |

### EveryMundo Sputnik API (8개 항공사 공유)
- URL: `openair-california.airtrfx.com/airfare-sputnik-service/v3/{tenant}/fares/search`
- Tenants: **nz**, **et**, **jl**, **nh**, **tg**, **sq**, **af**, **kl**
- API Key: `HeQpRjsFI5xlAaSx2onkjc1HTK0ukqA1IrVvd5fvaMhNtzLTxInTpeYB1MK93pah`
- POST body: `{currency, departureDaysInterval:{min,max}, routesLimit, faresLimit, faresPerRoute, origin}`
- 반환: airline, route, departureDate, totalPrice, currencyCode, fareClass
- 인증 불필요, primp Chrome 131 TLS 필요, ~500 entries/request

### TK L3 Playwright 기법
- `channel='chrome'` (시스템 Chrome) → Akamai TLS fingerprint 우회
- 쿠키 오버레이 `pointerEvents='none'` (React DOM 파괴 방지)
- react-calendar 자동 열림 감지 후 날짜 선택
- `/api/v1/availability/cheapest-prices` 응답 인터셉트
- ~66초 소요

### LH Group API 인증
- Client ID: `hh5urays7eppuv6hn6tx99fvx`
- Client Secret: `KjENp79k85`
- 무료 LH Public plan (5 calls/sec, 1000 calls/hour)
- OAuth2 token 36시간 유효, 60초 전 자동 갱신

### TK 공식 API
- 포털: `developer.apim.turkishairlines.com`
- 계정: `knsol2` / TOTP `GYYFEV3RIRVWGN3INNWGSYTDKQZUM6DU`
- 신규 계정 → 제품 목록 비어있음 → 지원팀에 권한 요청 이메일 발송 완료
- `CRAWLER_TK_USE_OFFICIAL_API=true` 시 공식 API 우선, 실패 시 L3 자동 폴백

### CX Histogram/Open-search
- Histogram: `GET book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/histogram`
  - Params: `ORIGIN`, `DESTINATION`, `SITE=CBEUCBEU`, `TYPE=MTH`, `LANGUAGE=GB`, `CABIN`
  - 월별 최저가 반환
- Open-search: `GET .../api/instant/open-search`
  - Params: `ORIGINS`, `SITE`, `LANGUAGE`
  - 84+ 목적지 일괄 반환

---

## 안티봇 바이패스 기법 요약

| 기법 | 대상 WAF | 성공 사례 |
|------|----------|-----------|
| Naver Yeti UA | Cloudflare | Air Busan (BX) |
| primp TLS (chrome_131) | Cloudflare/Akamai | LOT, EVA Air, T'way, VN, CX, MH, EK |
| 여행사 포털 우회 | Akamai | T'way (tagency.twayair.com) |
| 공개 S3/CDN | 없음 | Jin Air (fare.jinair.com) |
| Navitaire 세션 | 없음 | Eastar Jet (kraken.eastarjet.com) |
| Playwright cookie 추출 | Cloudflare | Air Premia (YP) |
| **EveryMundo Sputnik (공유 키)** | Cloudflare | **NZ, ET, JL, NH, TG, SQ, AF, KL** (8개) |
| 미들웨어 API 직접 호출 | Imperva 우회 | Vietnam Airlines |
| Flight status API | 없음 | Philippine Airlines |
| Mobile HMAC-SHA1 서명 | 없음 | Hainan Airlines |
| AEM Sling 서블릿 | Cloudflare | Malaysia Airlines |
| Akamai warm-up + API | Akamai | CX histogram, EK featured-fares |
| OAuth2 공식 API | 없음 | Lufthansa Group, TK (대기) |
| **Playwright 시스템 Chrome + 폼 자동화** | Akamai | **Turkish Airlines (TK)** |
| Playwright 폼 자동화 (차단됨) | Akamai | ❌ QR |

---

## 커버리지 요약

- **전체 커버 항공사**: 39개 (직접 L2/L3 27개 + Amadeus fallback 12개)
- **총 크롤러**: 29개 (L1 2 + Korean LCC 7 + GDS 1 + Global L2 18 + Amadeus fallback 1)
- **E2E 테스트**: 28 passed, 1 xfailed (Kiwi — 초대제 API key)
- **Sputnik 사용 항공사**: 8개 (NZ, ET, JL, NH, TG, SQ, AF, KL)
- **Amadeus fallback**: QR, RS, GA, SV, EY, MU, CZ, DL, AA, UA, QF, AC (12개, 전체 검증 완료)
- **한국 출발 주요 허브 커버리지**:
  IST ✅ DOH ✅ SIN ✅ HKG ✅ NRT ✅ FRA ✅ CDG ✅ AMS ✅ BKK ✅ TPE ✅ WAW ✅ KUL ✅ ADD ✅ DXB ✅
  CGK ✅ JED ✅ AUH ✅ PVG ✅ CAN ✅ SEA ✅ DFW ✅ SFO ✅ SYD ✅ YVR ✅
