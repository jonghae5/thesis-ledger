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

`data fetch`는 가격과 SEC point-in-time 재무만 갱신한다. 컨센서스는 Alpha Vantage 키가 있을 때 별도로 저장한다.

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
analysis prepare
    ↓
품질 게이트 확인
    ↓
Codex가 변경점/thesis/risk 판단
    ↓
analysis save
```

CLI 자체는 LLM을 호출하지 않는다. 터미널에서 `analysis prepare`를 실행하면 Codex가 읽을 근거 패키지만 만들어진다.

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
uv run thesis analysis prepare NVDA
```

`prepare` 결과의 `status`가 `READY`인지 확인한 뒤 Codex에게 메모 작성을 요청한다.

### 기존 종목 업데이트

```bash
uv run thesis data fetch NVDA
uv run thesis analysis prepare NVDA
```

`prepare`는 다음을 한 JSON으로 반환한다.

- `previous_analysis`: 직전 thesis와 판단
- `changes_since_previous`: 당시 이후 가격·EPS·매출 컨센서스 변화
- `evidence`: 현재 시장·재무·기대·밸류에이션·guidance·catalyst
- `status`: `READY` 또는 `INSUFFICIENT_EVIDENCE`

컨센서스가 `MISSING` 또는 `STALE`이면 다음 순서로 갱신한다. Alpha Vantage가 quota나 일시 오류로 실패하면 yfinance로 자동 전환하며, 두 provider가 모두 실패하면 마지막 정상 snapshot을 `STALE`로 반환한다.

```bash
uv run thesis data expectations NVDA
uv run thesis analysis prepare NVDA
```

### 여러 기업 비교

각 종목을 먼저 수집한 뒤 비교한다.

```bash
uv run thesis data fetch NVDA
uv run thesis data fetch AMD
uv run thesis data fetch AVGO
uv run thesis data compare NVDA AMD AVGO
```

`compare`는 성장률, FCF margin, 순부채, momentum, 변동성, revision, multiple, implied growth를 같은 필드로 나란히 보여준다. 임의의 종합점수나 자동 순위는 만들지 않는다.

### 주간 포트폴리오 점검

```bash
uv run thesis data fetch NVDA
uv run thesis data fetch AAPL
uv run thesis data fetch SPY
uv run thesis portfolio show
```

SPY 가격이 저장되어 있고 최신이면 포트폴리오 beta도 계산한다.

## Evidence 품질 해석

```bash
uv run thesis data evidence NVDA
```

`evidence`는 저장된 데이터를 읽어 다음 섹션을 만든다.

- `market`: 가격, momentum, volatility, 52주 고점·200일선 거리
- `fundamentals`: 매출 성장, FCF margin, 순부채, 희석
- `expectations`: 최근 EPS·매출 컨센서스
- `revisions`: 7/30/90일 revision
- `valuation`: trailing/forward multiple과 FCF yield
- `implied_expectations`: reverse DCF implied revenue CAGR
- `guidance`: 최근 저장된 경영진 guidance
- `catalysts`: 오늘 이후 저장된 이벤트
- `macro`: 기준금리, 실질금리, 금리차, 인플레이션·기대인플레이션, 고용, 신용, NFCI, VIX, Fear & Greed, 달러

품질 필드 의미:

| 값 | 의미 | 행동 |
|---|---|---|
| `COMPLETE` | 모든 분석 섹션과 변화 판단이 사용 가능 | 전체 분석 가능 |
| `PARTIAL` | 조사 가능하지만 일부 결론이 제한됨 | `analysis_mode`와 `cannot_conclude`를 확인 |
| `INSUFFICIENT` | 가격·재무·valuation 같은 핵심 입력 부족 | 투자 결론을 만들지 않고 데이터부터 수집 |

추가 필드:

- `analysis_mode`: `DECISION_READY`, `RESEARCH_ONLY`, `INSUFFICIENT`
- `can_research`: 가격·재무·valuation으로 사실 조사와 정리가 가능한지 여부
- `can_decide`: 신선한 컨센서스와 측정 가능한 revision까지 있어 방향성 판단이 가능한지 여부
- `can_analyze`: 하위 호환 필드이며 `can_decide`와 동일
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
uv run thesis portfolio --help
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

외부 API를 호출하지 않고 현재 DB의 분석 재료를 하나의 품질 판정 JSON으로 구성한다. 조사 핵심 입력도 없어 `can_research=false`이면 exit code `1`이다. `RESEARCH_ONLY`는 정상 출력하되 방향성 판단과 `analysis save`를 허용하지 않는다.

#### Peer 비교

```bash
uv run thesis data compare NVDA AMD
uv run thesis data compare NVDA AMD AVGO --max-price-age-days 14
```

최소 두 개의 서로 다른 ticker가 필요하다. 모든 종목이 분석 불가능하면 exit code `1`; 일부만 부족하면 `PARTIAL`과 경고를 반환한다.

#### Catalyst 조회

```bash
uv run thesis data catalysts NVDA
```

수동 저장 catalyst와 Alpha Vantage earnings calendar를 병합한다. 같은 날짜의 수동 earnings event가 자동수집 항목보다 우선한다.

#### 뉴스

```bash
uv run thesis data news NVDA
uv run thesis data news NVDA --days 14
```

Finnhub 최근 뉴스를 반환한다. `--days`는 1~30이다. 자동으로 catalyst를 판정하거나 저장하지 않는다.

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
  --bull-growth 0.30 --bull-margin 0.45 --bull-prob 0.25
```

세 확률의 합은 `1.0`이어야 한다. growth, margin, probability는 사용자 또는 Codex의 가정이며 Python이 자동 추정하지 않는다. 결과의 probability-weighted value를 객관적 적정가치처럼 사용하면 안 된다.

#### 단계형 DCF 민감도

```bash
uv run thesis valuation sensitivity NVDA \
  --growth 0.20 --mature-margin 0.35 --annual-dilution 0.005
```

초기 성장률은 terminal growth까지, 현재 FCF margin은 지정한 mature margin까지 선형으로 변한다. 성장률과 할인율을 각각 세 값으로 나눈 3×3 표를 반환하며, 모든 입력은 사용자 가정이다.

### Analysis

#### 업데이트 준비

```bash
uv run thesis analysis prepare NVDA
uv run thesis analysis prepare NVDA --max-price-age-days 14
```

직전 분석, 이후 변화, 현재 evidence를 하나로 합친다. 외부 API는 호출하지 않는다. 핵심 데이터가 부족하면 `INSUFFICIENT_EVIDENCE`와 exit code `1`을 반환한다.

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

#### Guidance 저장

```bash
uv run thesis analysis save-guidance NVDA \
  --revenue-low 43000000000 \
  --revenue-high 45000000000 \
  --margin-guidance 0.72 \
  --capex-guidance 5000000000 \
  --source-filing 10-Q \
  --source-date 2026-08-20
```

Codex 또는 사용자가 filing에서 추출한 guidance를 저장하고 직전 snapshot 대비 `FIRST_SNAPSHOT`, `RAISED`, `MAINTAINED`, `LOWERED`, `UNKNOWN`을 반환한다. Python은 filing 문장을 자동 해석하지 않는다.

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
  --model-name codex \
  --model-version MODEL_VERSION \
  --prompt-version investment-analysis-v1 \
  --input-snapshot-json '{"price_as_of":"2026-08-21"}' \
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

재현성 확인을 위해 `model-name`, `model-version`, `prompt-version`, `input-snapshot-json`을 함께 제공하는 것을 권장한다. 빠지면 저장은 되지만 `audit_complete=false`가 반환되고 `doctor`가 경고할 수 있다.

### Portfolio

개인별 비중 판단이 필요하면 예시 파일을 복사해 투자 원칙을 기록한다.

```bash
cp config/investor-policy.example.json config/investor-policy.json
```

투자기간·비상자금·최대 종목 및 섹터 비중·허용 drawdown만 기록한다. 이 값은 강제 최적값이 아니라 `USER_ASSUMPTION` 상한으로 사용된다.

#### 보유종목 등록 또는 갱신

```bash
uv run thesis portfolio add NVDA \
  --shares 10 \
  --avg-cost 150 \
  --opened-at 2026-01-15 \
  --sector Semiconductors
```

같은 ticker를 다시 등록하면 기존 row가 새 값으로 교체된다. 추가매수 lot이나 거래원장을 자동 계산하지 않으므로 사용자가 새 shares와 평균단가를 계산해야 한다.

#### 보유종목 삭제

```bash
uv run thesis portfolio remove NVDA
```

보유 row만 삭제하며 가격·재무·분석 이력은 삭제하지 않는다.

#### 포트폴리오 조회

```bash
uv run thesis portfolio show
uv run thesis portfolio show --max-price-age-days 14
```

계산 항목:

- 종목별 market value, cost basis, 미실현 수익률, weight
- sector exposure와 최대 보유 비중
- 공통 가격 이력이 충분할 때 volatility와 max drawdown
- concentration HHI와 effective number of positions
- 종목 간 correlation
- SPY 데이터가 있을 때 beta

모든 보유종목의 최신 가격이 필요하다. 현금, 환율, 세금, 수수료, 배당, 거래 lot, 옵션, 공매도는 지원하지 않는다.

### Doctor

```bash
uv run thesis doctor
uv run thesis doctor --max-price-age-days 14
```

다음을 검사한다.

- 상용 데이터 provider 라이선스 선언
- 보유종목 가격 freshness
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

### `INSUFFICIENT_EVIDENCE`

출력의 `quality.missing`과 각 section의 `message`를 확인한다. 일반적으로 먼저 다음을 실행한다.

```bash
uv run thesis data fetch TICKER
uv run thesis data expectations TICKER   # API key가 있을 때
uv run thesis analysis prepare TICKER
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
