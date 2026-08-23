---
name: valuation
description: forward/trailing multiple, reverse DCF(현재가 implied growth), bear/base/bull 시나리오를 계산한다. "현재 가격에 얼마나 성장이 반영됐어", "밸류에이션 어때" 같은 질문에 사용.
---

# valuation

## 목적
Forward multiple로 상대가치를, reverse DCF로 "현재 가격이 요구하는 미래"를, scenario engine으로 bear/base/bull 결과를 계산한다 (원본 스펙 §13-15).

## 실행할 CLI 커맨드

### 1. 배수 (`valuation`)
```bash
uv run thesis valuation multiples <TICKER>
```
출력: `market_cap`, `enterprise_value`, `trailing_pe`, `forward_pe`(consensus 없으면 `null`), `ev_to_revenue_trailing`, `ev_to_revenue_forward`, `fcf_yield_trailing`.

과거 percentile 비교(원본 스펙 "5Y median과 비교")는 **구현하지 않음** — 여러 해에 걸친 forward consensus snapshot이 쌓여야 의미가 있는데 아직 그 정도 history가 없다. `revisions`처럼 snapshot이 쌓이면 이후 Phase에서 추가.

### 2. Reverse DCF (`reverse-dcf`)
```bash
uv run thesis valuation reverse-dcf <TICKER> [--discount-rate 0.09] [--terminal-growth 0.025] [--years 10]
```
출력: `implied_revenue_cagr` — 현재 시가총액+순부채(=EV)를 정당화하려면 매출이 몇 %로 성장해야 하는지, **현재 FCF margin을 그대로 유지한다는 가정 하에** 역산한 값. `fcf_margin_assumed`도 함께 반환(=trailing FCF/매출, 상수로 고정한 가정값). 이게 사용자의 "지금 가격에는 어느 정도 성장이 반영되어 있어?" 질문에 대한 직접적인 답이다.

Codex가 할 일: 이 `implied_revenue_cagr`를 `expectations`의 consensus 성장률, 그리고 Codex 자신의 base case 성장률과 나란히 놓고 비교(spec §14의 `PRICE IMPLIED vs CONSENSUS vs OUR BASE CASE`) — 이 비교 자체는 Python이 하지 않는다.

FCF margin이 0 이하인 종목(구조적 적자)은 이 모델이 의미가 없어 에러를 반환한다.

### 3. Scenario (`scenario`)
```bash
uv run thesis valuation scenario <TICKER> \
  --bear-growth 0.10 --bear-margin 0.35 --bear-prob 0.25 \
  --base-growth 0.20 --base-margin 0.40 --base-prob 0.50 \
  --bull-growth 0.30 --bull-margin 0.45 --bull-prob 0.25 \
  [--discount-rate 0.09] [--terminal-growth 0.025] [--years 10]
```

**중요: growth/margin/probability 숫자는 Codex(너)가 정한다.** Python은 그 가정으로 target_price를 계산할 뿐, bear/base/bull이 뭘 의미해야 하는지 스스로 판단하지 않는다 — `AGENTS.md`의 "Python은 판단 안 함" 원칙 그대로. 세 시나리오 확률의 합은 1.0이어야 한다(아니면 에러).

출력 (원본 스펙 §15 그대로):
```json
{
  "ticker": "NVDA",
  "bear": {"probability": 0.25, "revenue_growth": 0.10, "margin": 0.35, "target_price": 0},
  "base": {"probability": 0.50, "revenue_growth": 0.20, "margin": 0.40, "target_price": 0},
  "bull": {"probability": 0.25, "revenue_growth": 0.30, "margin": 0.45, "target_price": 0},
  "probability_weighted_value": 0
}
```

### 4. 단계형 DCF 민감도 (`sensitivity`)

```bash
uv run thesis valuation sensitivity <TICKER> \
  --growth 0.20 --mature-margin 0.30 \
  [--discount-rate 0.09] [--terminal-growth 0.025] \
  [--annual-dilution 0.01]
```

초기 매출 성장률은 terminal growth까지, 현재 FCF margin은 `mature-margin`까지 10년에 걸쳐 선형으로 변한다. 기준 성장률·할인율과 각각 위아래 한 단계의 3×3 target price 표를 반환한다. 입력은 `USER_ASSUMPTION`, 결과는 `MODEL_OUTPUT`이며 점추정 목표가격보다 가정 민감도를 확인하는 데 사용한다.

## DCF 모델 가정 (spec이 명시하지 않아 이 구현이 확정)
- `years`년(기본 10) explicit 구간 동안 매출이 매년 `growth`로 성장, FCF = 매출 × `fcf_margin`(구간 내내 고정).
- terminal value = 마지막 해 FCF × (1+`terminal_growth`) / (`discount_rate` - `terminal_growth`).
- 전부 `discount_rate`(기본 9%)로 현재가치 할인, 합산 = enterprise value.
- `discount_rate`는 반드시 `terminal_growth`보다 커야 한다.

`sensitivity`만 성장률과 마진이 선형으로 변하고, 선택한 `annual_dilution`만큼 미래 주식 수를 늘린다. 기존 `reverse-dcf`와 `scenario`의 고정 가정은 비교 가능성을 위해 유지한다.

## 의존 데이터
- 모든 계산은 SEC fundamentals가 필요하므로 최소 한 번 `data fetch`를 실행한다. `multiples`는 가격도 필요하다. `estimate_snapshots`는 forward 지표 계산에만 쓰이며 없으면 해당 필드가 `null`이다.

## 매크로와 할인율

금리 변화의 valuation 영향이나 bear/base/bull scenario를 묻는 경우 `uv run thesis data macro`로 기준금리, 10년 실질금리, 기대인플레이션, 신용·유동성 환경을 확인한다. snapshot이 없으면 `data macro-fetch`를 먼저 실행한다.

매크로 값으로 `discount_rate`를 자동 결정하지 않는다. 기본 9%는 모델 기본값일 뿐 현재 시장의 객관적 WACC가 아니다. 실질금리와 신용환경이 크게 변했으면 할인율 민감도를 여러 값으로 계산하고, 선택한 할인율은 `USER_ASSUMPTION` 또는 `LLM_INFERENCE`로 명시한다. Fear & Greed와 VIX는 내재가치의 현금흐름 또는 할인율 입력으로 직접 사용하지 않는다.
