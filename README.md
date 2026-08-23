# ThesisLedger

Codex 기반 개인 투자 리서치·판단 기록 시스템이다.

- Python CLI는 가격·SEC 재무·컨센서스를 수집하고 결정론적 계산과 이력 저장을 담당한다.
- Codex는 근거를 해석하고 thesis, variant perception, 리스크, 최종 투자 메모를 작성한다.
- 자동매매나 주문 실행 기능은 없다.
- 모든 CLI 출력은 한 줄 JSON이며, 자동화 가능한 실패는 exit code `1`을 반환한다.

## 가장 빠른 시작

### 1. 설치

필요한 환경은 Python 3.10 이상과 `uv`다.

```bash
cd /home/jonghae5/thesis-ledger
uv sync
cp .env.example .env
```

`.env`를 열어 최소한 `SEC_CONTACT_EMAIL`을 실제 연락 가능한 주소로 바꾼다.

```dotenv
SEC_CONTACT_EMAIL=your-name@your-domain.com
ALPHA_VANTAGE_API_KEY=
FINNHUB_API_KEY=
THESIS_LEDGER_USAGE=personal
LICENSED_DATA_PROVIDERS=
```

### 2. 첫 데이터 수집

```bash
uv run thesis data fetch NVDA
uv run thesis data evidence NVDA
```

`data fetch`는 가격과 SEC point-in-time 재무만 갱신한다. 기본 손익·현금흐름 외에 ROIC 입력, SBC·자사주 매입, 운전자본, goodwill·인수 현금흐름, 이자비용과 실제 사용한 SEC concept도 저장한다. 컨센서스는 Alpha Vantage 키가 있을 때 별도로 저장한다.

```bash
uv run thesis data expectations NVDA
uv run thesis data evidence NVDA
```

### 3. Codex에서 사용

이 저장소를 작업 디렉터리로 열고 자연어로 요청하는 방식이 기본 사용법이다.

```text
NVDA 업데이트해줘.
지난 NVDA 분석 이후 무엇이 바뀌었어?
NVDA와 AMD를 비교해줘.
내 포트폴리오에서 가장 위험한 종목을 근거와 함께 알려줘.
NVDA 현재 가격에는 어느 정도 성장이 반영되어 있어?
```

Codex는 `.agents/skills`의 지침을 읽고 필요한 CLI만 실행한다. 일반적인 종합 업데이트 흐름은 다음과 같다.

```text
data fetch
    ↓
analysis prepare-current --freeze
    ↓
Codex가 이전 결론 없이 현재 상태 판단
    ↓
analysis compare-prior
    ↓
Codex가 thesis 변화를 판단하고 analysis save
```

### 한국 주식 MCP

이 저장소를 trusted project로 연 Codex 클라이언트는 `.codex/config.toml`의 원격 `korea_stock` MCP를 통해 KOSPI·KOSDAQ 종목 검색, KRX 시세, DART 연간 재무와 공시 risk flag를 조회할 수 있다. 새 설정을 읽으려면 Codex CLI·IDE·데스크톱 클라이언트에서 새 세션을 시작하거나 해당 클라이언트를 재시작한다.

한국 종목 데이터는 현재 외부 조사 근거로만 사용한다. MCP 연간 재무에는 각 숫자의 실제 filing date가 없고 컨센서스·revision도 제공되지 않으므로 `fundamental_snapshots`나 `investment_analysis`에 저장하지 않으며 방향성 판단을 만들지 않는다. MCP에는 종목코드 외의 보유수량·평균단가·자산 같은 개인 정보를 보내지 않는다.

CLI 자체는 LLM을 호출하지 않는다. 터미널에서 `analysis prepare-current`를 실행하면 Codex가 읽을 현재 근거 패키지만 만들어진다.

## 환경변수

| 변수 | 필수 여부 | 용도 |
|---|---:|---|
| `SEC_CONTACT_EMAIL` | 필수 | SEC User-Agent 정책에 사용할 연락처 |
| `ALPHA_VANTAGE_API_KEY` | 선택 | 컨센서스, 실적 surprise, earnings calendar |
| `FINNHUB_API_KEY` | 선택 | 최근 기업 뉴스 |
| `THESIS_LEDGER_USAGE` | 선택 | `personal` 또는 `commercial`; 기본 `personal` |
| `LICENSED_DATA_PROVIDERS` | 상용 사용 시 | 상용 라이선스를 확인한 provider 목록 |

선택 API 키가 없으면 관련 기능만 `SKIPPED` 또는 `MISSING`으로 표시된다. 가격·SEC 재무 기능은 계속 사용할 수 있다.

상용 모드 예시:

```dotenv
THESIS_LEDGER_USAGE=commercial
LICENSED_DATA_PROVIDERS=alpha_vantage,finnhub
```

상용 모드에서 라이선스가 기록되지 않은 Yahoo Finance, Alpha Vantage, Finnhub 호출은 차단된다. 이 설정은 라이선스를 대신하지 않으며 실제 데이터 계약은 사용자가 확인해야 한다.

## 권장 워크플로

### 신규 종목 분석

```bash
uv run thesis data fetch NVDA
uv run thesis data expectations NVDA       # API key가 있을 때
uv run thesis analysis prepare-current NVDA --freeze
```

`prepare-current`의 quality gate를 확인한 뒤 Codex가 이전 결론 없이 현재 상태를 먼저 평가한다.

### 기존 종목 업데이트

```bash
uv run thesis data fetch NVDA
uv run thesis analysis prepare-current NVDA --freeze
uv run thesis analysis compare-prior NVDA --evidence-bundle-id BUNDLE_ID
```

`prepare-current`는 이전 결론을 제외한 현재 evidence와 immutable bundle ID를 반환한다. 독립 평가가 끝난 후 `compare-prior`가 다음을 반환한다.

- `previous_analysis`: 직전 thesis와 판단
- `changes_since_previous`: 당시 이후 가격·EPS·매출 컨센서스 변화
- `evidence`: 현재 시장·재무·기대·밸류에이션·guidance·catalyst

실행 가능 범위는 `evidence.quality.can_research`와 `can_decide`로 확인한다.

컨센서스가 `MISSING` 또는 `STALE`이면 다음 순서로 갱신한다. Alpha Vantage가 quota나 일시 오류로 실패하면 yfinance로 자동 전환하며, 두 provider가 모두 실패하면 마지막 정상 snapshot을 `STALE`로 반환한다.

```bash
uv run thesis data expectations NVDA
uv run thesis analysis prepare-current NVDA --freeze
```

### 여러 기업 비교

각 종목을 먼저 수집한 뒤 비교한다.

```bash
uv run thesis data fetch NVDA
uv run thesis data fetch AMD
uv run thesis data fetch AVGO
uv run thesis data compare NVDA AMD AVGO
```

`compare`는 성장률, 장기 margin·주식수 변화, FCF, 순부채, momentum, 변동성, revision, multiple, implied growth를 같은 필드로 나란히 보여준다. 임의의 종합점수나 자동 순위는 만들지 않는다.

## Evidence 품질 해석

```bash
uv run thesis data evidence NVDA
```

`evidence`는 저장된 데이터를 읽어 다음 섹션을 만든다.

- `market`: 가격, momentum, volatility, 52주 고점·200일선 거리
- `fundamentals`: 매출 성장, FCF margin, 순부채, 희석
- `business_quality`: 여러 연도의 margin 안정성, ROIC·재투자, 현금전환, SBC·자사주 매입, 운전자본, M&A 의존도와 재무 회복력 입력
- `expectations`: 최근 EPS·매출 컨센서스
- `revisions`: 7/30/90일 revision
- `valuation`: trailing/forward multiple과 FCF yield
- `implied_expectations`: reverse DCF implied revenue CAGR
- `guidance`: 최근 저장된 경영진 guidance
- `catalysts`: 오늘 이후 저장된 이벤트
- `macro`: 기준금리, 실질금리, 금리차, 인플레이션·기대인플레이션, 고용, 신용, NFCI, VIX, Fear & Greed, 달러

`quality`는 세 종류만 사용한다.

| 필드 | 값 | 의미 |
|---|---|---|
| `completeness` | `COMPLETE/PARTIAL/INSUFFICIENT` | 전체 입력의 완전성 |
| `can_research` | boolean | 가격·재무·valuation으로 사실 조사와 정리가 가능한지 |
| `can_decide` | boolean | 검증 가능한 expectation anchor가 있어 방향성 판단이 가능한지 |

`COMPLETE/PARTIAL`은 판단 허용 상태가 아니다. 실제 허용 여부는 boolean을 사용한다. `expectation_anchors`에는 사용 가능한 `CONSENSUS_REVISION` 또는 `GUIDANCE_VS_PRICE_IMPLIED` 경로가 표시된다.

진단 필드:

- `missing`: 없거나 오래된 섹션
- `cannot_conclude`: 현재 데이터로 결론 내리면 안 되는 항목
- `warnings`: catalyst/guidance 부족, 지표 결측 등
- `provenance`: source, 원문 URL, 수집 시점

가격은 기본 7일 freshness 제한이 있다. 컨센서스 snapshot은 2일이 지나면 `STALE`로 표시된다.

매크로 데이터는 `uv run thesis data macro-fetch`로 append-only snapshot을 저장하고 `uv run thesis data macro [--as-of YYYY-MM-DD]`로 조회한다. 핵심 지표가 없으면 기업 분석 자체는 가능하지만 품질은 `PARTIAL`이며 macro-sensitive scenario calibration을 결론 내리지 않는다. Fear & Greed는 위험선호 보조 증거로만 사용하고 내재가치나 단독 매매 신호로 사용하지 않는다.

## 전체 CLI 명령

언제든 다음 명령으로 실제 옵션을 확인할 수 있다.

```bash
uv run thesis --help
uv run thesis data --help
uv run thesis valuation --help
uv run thesis analysis --help
```

### Data

#### 워치리스트 seed

```bash
uv run thesis data seed
```

NVDA, AAPL, AMD, META, GOOGL을 `companies` 테이블에 등록한다. 데이터를 자동으로 가져오지는 않는다.

#### 가격·SEC 재무 수집

```bash
uv run thesis data fetch NVDA
```

- Yahoo Finance 가격 약 400일치를 저장한다.
- SEC company facts를 filing date/accession별 snapshot으로 저장한다.
- SEC가 보고한 경우 ROIC 입력, SBC·자사주 매입, 운전자본, goodwill·인수 현금흐름, 이자비용과 선택된 XBRL concept를 함께 저장한다.
- 가격 또는 SEC 수집이 실패하면 exit code `1`이다.
- 컨센서스는 수집하지 않는다.

#### 시장 지표

```bash
uv run thesis data market NVDA
uv run thesis data market NVDA --max-price-age-days 14
```

1/3/6/12개월 momentum, 20/60일 연환산 volatility, 52주 고점 거리, 200일선 거리 등을 계산한다.

#### 매크로·시장 심리 snapshot

```bash
uv run thesis data macro-fetch
uv run thesis data macro
uv run thesis data macro --as-of 2026-08-23
```

`macro-fetch`는 FRED의 기준금리, 실질금리, 금리차, Core PCE YoY, 기대인플레이션, 고용, Sahm rule, HY OAS, NFCI, VIX, 달러와 CNN Fear & Greed를 실제 호출해 append-only snapshot으로 저장한다. FRED 지표는 가능한 경우 최근 5년 percentile을 계산한다. 여러 FRED 시리즈는 응답 주기가 다르므로 각 시리즈를 개별 호출하며, 일부 provider가 실패해도 성공한 snapshot은 보존한다.

`macro`는 저장 데이터만 읽고 외부 API를 호출하지 않는다. 축별 값·변화·발표일·수집일·stale 상태를 반환하며 단일 macro/risk score를 만들지 않는다. `--as-of`는 그 날짜까지 실제로 저장돼 있던 snapshot만 사용하며 현재 값을 과거로 소급하지 않는다. Fear & Greed는 위험선호와 포지셔닝의 보조 증거이지 내재가치나 단독 BUY/SELL 신호가 아니다.

#### 재무 지표

```bash
uv run thesis data fundamentals NVDA
uv run thesis data fundamentals NVDA --as-of 2026-06-30
```

`--as-of`를 사용하면 그 날짜까지 공개된 filing만 사용한다. 과거 시점 이후 제출된 재무를 소급해 사용하지 않는다.

출력의 `ttm`은 최근 연간 10-K에 이후 10-Q 분기를 더하고 전년 동기 분기를 빼서 계산한다. 필요한 SEC fact가 없으면 추정하지 않고 해당 필드를 `null`로 둔다. valuation은 revenue·FCF·순이익이 모두 계산된 경우 `TTM_DERIVED`, 아니면 `ANNUAL_FALLBACK`을 사용한다.

#### Business-quality 입력

```bash
uv run thesis data quality NVDA
uv run thesis data quality NVDA --as-of 2026-06-30
```

canonical 연간 filing에서 gross·operating·FCF margin의 수준과 변동, 매출·주식수 CAGR, incremental operating margin, ROIC, capex intensity, 현금전환, SBC·자사주 매입, 운전자본, goodwill·인수 현금흐름과 순부채/이자보상배율을 계산한다. 원천 숫자는 `history[].facts`, 계산값은 `history[].model_outputs`와 축별 요약에 분리한다.

단일 quality score나 moat 판정은 만들지 않는다. `coverage.metric_availability`는 각 계산값을 `AVAILABLE/MISSING`으로 따로 표시한다. product/geographic segment와 부채 만기는 Companyfacts만으로 신뢰성 있게 정규화하지 않아 `unavailable_dimensions`의 원문 확인 대상으로 남긴다. `--as-of`는 해당 날짜까지 실제 제출된 filing만 사용한다. 기존 DB는 migration 후 `data fetch`를 다시 실행해야 새 필드가 채워진다.

#### 컨센서스 snapshot

```bash
uv run thesis data expectations NVDA
uv run thesis data expectations NVDA --period next
```

`--period`는 `current` 또는 `next`를 사용한다. 호출할 때마다 선택된 회계연도의 EPS·매출 추정치를 append-only snapshot으로 저장한다.

#### 컨센서스 revision

```bash
uv run thesis data revisions NVDA
uv run thesis data revisions NVDA --fiscal-period 2027-01-31
```

서로 다른 날짜에 저장한 snapshot이 필요하다. 같은 날 반복 호출해도 7/30/90일 기준 과거 snapshot이 없으면 revision 값은 `null`이다.

#### 실적 surprise

```bash
uv run thesis data earnings-surprise NVDA
```

Alpha Vantage의 실제 EPS와 예상 EPS로 최근 surprise와 hit rate를 계산한다. DB에는 저장하지 않는다.

#### 통합 evidence

```bash
uv run thesis data evidence NVDA
uv run thesis data evidence NVDA --max-price-age-days 14
```

외부 API를 호출하지 않고 현재 DB의 분석 재료를 하나의 품질 판정 JSON으로 구성한다. 조사 핵심 입력도 없어 `can_research=false`이면 exit code `1`이다. `can_decide=false`이면 사실 조사는 가능하지만 방향성 판단과 `analysis save`를 허용하지 않는다.

#### Peer 비교

```bash
uv run thesis data compare NVDA AMD
uv run thesis data compare NVDA AMD AVGO --max-price-age-days 14
```

최소 두 개의 서로 다른 ticker가 필요하다. 모든 종목에서 `can_research=false`이면 exit code `1`; 일부만 부족하면 경고를 반환한다.

#### Catalyst 조회

```bash
uv run thesis data catalysts NVDA
```

수동 저장 catalyst와 Alpha Vantage earnings calendar를 병합한다. 같은 날짜의 수동 earnings event가 자동수집 항목보다 우선한다.

#### 뉴스

```bash
uv run thesis data news NVDA
uv run thesis data news NVDA --days 14
uv run thesis data news NVDA --days 14 --limit 20
```

Finnhub 최근 뉴스 후보를 기본 20건 반환한다. `--days`는 1~30, `--limit`은 1~100이다. 자동으로 catalyst를 판정하거나 저장하지 않으며 원문 검증 전에는 분석 근거로 사용하지 않는다.

### Valuation

#### Multiple

```bash
uv run thesis valuation multiples NVDA
```

시가총액, enterprise value, trailing/forward P/E, EV/revenue, trailing FCF yield를 계산한다. 저장된 컨센서스가 없으면 forward 필드는 `null`이다.

#### Reverse DCF

```bash
uv run thesis valuation reverse-dcf NVDA
uv run thesis valuation reverse-dcf NVDA \
  --discount-rate 0.10 --terminal-growth 0.025 --years 10
```

현재 enterprise value를 정당화하는 implied revenue CAGR을 역산한다. 명시 구간 동안 현재 trailing FCF margin이 유지된다는 단순화된 모델이다. FCF margin이 0 이하이면 계산하지 않는다.

#### Bear/Base/Bull scenario

```bash
uv run thesis valuation scenario NVDA \
  --bear-growth 0.10 --bear-margin 0.35 --bear-prob 0.25 \
  --base-growth 0.20 --base-margin 0.40 --base-prob 0.50 \
  --bull-growth 0.30 --bull-margin 0.45 --bull-prob 0.25 \
  --annual-dilution 0.01
```

세 확률의 합은 `1.0`이어야 한다. growth는 첫해 성장률이며 terminal growth까지 낮아지고, margin은 마지막 explicit year의 정상화 FCF margin이다. 현재 FCF margin에서 정상화 margin까지 선형으로 이동하며 연간 희석도 반영한다. 각 case는 terminal-value 비중, 마지막 해 매출·FCF, 누적 희석률, 현재가 대비 DCF upside/downside를 반환한다. DCF 현재가치의 upside를 10년 보유수익률로 해석하면 안 된다.

#### 단계형 DCF 민감도

```bash
uv run thesis valuation sensitivity NVDA \
  --growth 0.20 --mature-margin 0.35 --annual-dilution 0.005
```

초기 성장률은 terminal growth까지, 현재 FCF margin은 지정한 mature margin까지 선형으로 변한다. 성장률과 할인율을 각각 세 값으로 나눈 3×3 표를 반환하며, 모든 입력은 사용자 가정이다.

### Analysis

#### 업데이트 준비

```bash
uv run thesis analysis prepare-current NVDA
uv run thesis analysis prepare-current NVDA --freeze
uv run thesis analysis compare-prior NVDA --evidence-bundle-id BUNDLE_ID
uv run thesis analysis prepare NVDA
uv run thesis analysis prepare NVDA --max-price-age-days 14
```

`prepare-current`는 이전 분석을 노출하지 않으며 `--freeze`를 사용하면 현재 evidence와 SHA-256 hash를 append-only bundle로 저장한다. 현재 상태를 독립 평가한 후에만 `compare-prior`로 직전 분석과 이후 변화를 확인한다. 기존 `prepare`는 호환성을 위해 세 항목을 한 번에 반환한다. 외부 API는 호출하지 않으며 `evidence.quality.can_research=false`이면 exit code `1`을 반환한다.

#### 최근 분석과 이력

```bash
uv run thesis analysis latest NVDA
uv run thesis analysis history NVDA
uv run thesis analysis history NVDA --limit 50
```

분석 이력은 최신순이다. `latest`에 기록이 없으면 `NO_HISTORY`를 반환한다.

#### 특정 날짜 이후 변화

```bash
uv run thesis analysis change-since NVDA --since-date 2026-07-01
uv run thesis analysis change-since NVDA \
  --since-date 2026-07-01 --fiscal-period 2027-01-31
```

해당 날짜 전후의 가격·EPS 컨센서스·매출 컨센서스 변화를 계산한다. 그 날짜 이전에 저장된 데이터가 없으면 당시 값과 변화율은 `null`이다.

#### Guidance 원문 후보 찾기

```bash
uv run thesis data guidance-sources NVDA
uv run thesis data guidance-sources NVDA --days 730 --limit 12
```

SEC 제출 목록에서 최근 Item 2.02 8-K의 filing index와 primary document URL을 반환한다. 결과는 `CANDIDATE_SOURCE`이며 숫자를 추출하거나 `guidance_snapshots`에 저장하지 않는다. Codex 또는 사용자가 filing index의 earnings release 원문을 확인해 기간·범위·통화·단위를 정규화한 뒤 아래 명령으로 저장한다.

#### Guidance 저장

```bash
uv run thesis analysis save-guidance NVDA \
  --revenue-low 43000000000 \
  --revenue-high 45000000000 \
  --margin-guidance 0.72 \
  --capex-guidance 5000000000 \
  --fiscal-period FY2027 \
  --guidance-scope FULL_YEAR \
  --currency USD \
  --value-unit ONES \
  --source-filing 10-Q \
  --source-date 2026-08-20
```

Codex 또는 사용자가 원문에서 확인한 guidance를 저장한다. 회계기간·범위·통화·단위가 모두 같은 직전 snapshot만 비교해 `FIRST_SNAPSHOT`, `RAISED`, `MAINTAINED`, `LOWERED`, `UNKNOWN`을 반환한다. 기존 snapshot은 있지만 동일 기준의 snapshot이 없으면 `NOT_COMPARABLE`을 반환한다. Python은 filing 문장을 자동 해석하지 않는다.

#### Catalyst 저장

```bash
uv run thesis analysis save-catalyst NVDA \
  --event-date 2026-11-19 \
  --event-type earnings \
  --description "FY27 Q3 earnings" \
  --importance HIGH
```

`--importance`는 `HIGH`, `MED`, `LOW` 중 하나다. 확정된 사실과 예상 이벤트를 description에서 구분한다.

#### 투자 메모 저장

```bash
uv run thesis analysis save NVDA \
  --decision HOLD \
  --confidence 0.60 \
  --expected-return 0.08 \
  --expected-return-horizon-months 12 \
  --expected-return-method PROBABILITY_WEIGHTED_SCENARIO \
  --expected-return-basis PRICE_RETURN \
  --price 214.72 \
  --thesis-json '["AI accelerator demand remains strong"]' \
  --variant-perception-json '{"market_view":"growth normalizes","our_view":"revision remains positive"}' \
  --invalidation-json '["Two consecutive revenue estimate cuts"]' \
  --bull-value 260 \
  --base-value 230 \
  --bear-value 170 \
  --evidence-bundle-id BUNDLE_ID \
  --model-name codex \
  --model-version MODEL_VERSION \
  --prompt-version investment-analysis-v3 \
  --input-snapshot-json '{"news_evidence":[]}' \
  --assumptions-json '["discount_rate=0.09"]'
```

허용 decision:

- `STRONG_BUY`
- `ACCUMULATE`
- `HOLD`
- `WATCH`
- `REDUCE`
- `EXIT`

`expected-return`은 지정한 horizon의 누적 기대수익률이다. `expected-return-horizon-months`는 양의 정수이며, CLI가 비교용 연환산 수익률을 계산해 함께 저장한다. 방법은 `PROBABILITY_WEIGHTED_SCENARIO`, `BASE_CASE_TARGET`, `DCF_IRR`, `OTHER` 중 하나이고 기준은 `PRICE_RETURN` 또는 배당을 포함한 `TOTAL_RETURN`이다.

`confidence`는 0~1이다. `thesis-json`과 `invalidation-json`은 JSON 배열, `variant-perception-json`과 `input-snapshot-json`은 JSON 객체, `assumptions-json`은 JSON 배열이어야 한다. 저장은 append-only다.

재현성 확인을 위해 `prepare-current --freeze`가 반환한 `evidence-bundle-id`와 `model-name`, `model-version`, `prompt-version`을 함께 제공한다. CLI는 저장 가격이 frozen evidence의 가격과 같은지 검증한다. `input-snapshot-json`은 bundle 밖에서 확인한 뉴스 같은 supplemental evidence만 담는다. bundle 없이 저장하는 기존 경로는 호환되지만 metadata가 빠지면 `audit_complete=false`가 반환되고 `doctor`가 경고할 수 있다.

### 보유정보와 비중 판단

보유종목 원장이나 투자자 정책 파일은 저장하지 않는다. 종목 조사나 비중 판단이 필요할 때 현재 수량·평균단가·투자 가능 자산·목표 보유기간·감당 가능한 손실을 필요한 범위에서 Codex에 제공하면 해당 분석에서만 사용한다. 사용자가 제시한 종목·섹터 한도는 `USER_ASSUMPTION` 상한이며 목표 비중이나 객관적 최적값으로 취급하지 않는다.

### Doctor

```bash
uv run thesis doctor
```

다음을 검사한다.

- 상용 데이터 provider 라이선스 선언
- SEC point-in-time snapshot 존재 여부
- 저장된 투자 메모의 재현성 metadata 누락

결과는 `PASS`, `WARN`, `FAIL` 중 하나다. `FAIL`일 때 exit code `1`이다.

## 데이터와 파일 위치

| 경로 | 내용 |
|---|---|
| `data/thesis-ledger.duckdb` | 가격, filing snapshot, 컨센서스, 분석, 보유종목 |
| `data/raw_cache/` | provider 원본 응답 TTL cache |
| `.agents/skills/` | Codex가 읽는 투자 분석 방법론 |
| `.claude/skills` | 같은 Skill을 가리키는 Claude 호환 symlink |

Git에서 `.env`, DuckDB, raw cache는 제외된다. `estimate_snapshots`, `guidance_snapshots`, `investment_analysis`는 과거 판단을 보존하기 위해 append-only다.

## 자주 발생하는 문제

### `SEC_CONTACT_EMAIL not set`

`.env`에 실제 이메일을 설정한다.

```dotenv
SEC_CONTACT_EMAIL=your-name@your-domain.com
```

### `ALPHA_VANTAGE_API_KEY not set`

yfinance가 컨센서스 fallback으로 동작하고, 실적 surprise와 earnings calendar는 Finnhub를 거쳐 yfinance로 전환한다. 모든 provider가 실패하면 마지막 정상 snapshot은 `STALE`로 유지되고 해당 결론은 `PARTIAL` evidence에서 제외된다.

### `FINNHUB_API_KEY not set`

뉴스 없이 분석을 계속할 수 있다. 최신 사건 확인이 중요한 경우에만 키를 설정한다.

### `stored price ... is stale`

```bash
uv run thesis data fetch NVDA
```

주말·장기 휴장 때문에 7일 제한이 불편하면 읽기 명령에서 `--max-price-age-days`를 조정한다.

### `no stored fundamentals`

```bash
uv run thesis data fetch NVDA
```

SEC에 없는 해외 기업이나 ticker mapping 실패 종목은 현재 provider로 분석할 수 없을 수 있다.

### Revision 값이 모두 `null`

서로 다른 날짜에 컨센서스 snapshot을 쌓아야 한다.

```bash
uv run thesis data expectations NVDA
# 며칠 뒤 다시 실행
uv run thesis data expectations NVDA
uv run thesis data revisions NVDA
```

### `can_research=false`

출력의 `quality.missing`과 각 section의 `message`를 확인한다. 일반적으로 먼저 다음을 실행한다.

```bash
uv run thesis data fetch TICKER
uv run thesis data expectations TICKER   # API key가 있을 때
uv run thesis analysis prepare-current TICKER
```

## 테스트

```bash
uv run pytest -q
```

실제 DB와 설정 상태 점검:

```bash
uv run thesis doctor
```

## 범위와 주의사항

이 프로젝트는 리서치 보조 도구다. 투자수익을 보장하지 않으며 다음 기능을 제공하지 않는다.

- 주문 실행과 브로커 연동
- 고객 자금 운용과 컴플라이언스
- 세금·수수료·현금·환율을 포함한 완전한 거래원장
- ML 가격 예측과 자동매매
- 근거 없는 종합 risk score

실제 자금 투입 전에는 원문 filing, 데이터 라이선스, 계산 가정, 계좌 리스크를 별도로 확인해야 한다.
