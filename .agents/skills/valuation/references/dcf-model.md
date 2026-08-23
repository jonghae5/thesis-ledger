# DCF 모델 명세

reverse DCF, scenario 또는 sensitivity를 실행하거나 결과의 계산 구조를 설명할 때 사용한다.

## Reverse DCF

```bash
uv run thesis valuation reverse-dcf <TICKER> \
  [--discount-rate 0.09] [--terminal-growth 0.025] [--years 10]
```

현재 시가총액과 순부채로 enterprise value를 구하고, 현재 trailing FCF margin이 유지된다는 가정 아래 이를 정당화하는 `implied_revenue_cagr`를 역산한다. FCF margin이 0 이하이면 모델이 유효하지 않아 중단한다.

## Scenario

```bash
uv run thesis valuation scenario <TICKER> \
  --bear-growth N --bear-margin N --bear-prob N \
  --base-growth N --base-margin N --base-prob N \
  --bull-growth N --bull-margin N --bull-prob N \
  --annual-dilution N [--discount-rate N] [--terminal-growth N] [--years N]
```

각 case의 `growth`는 첫해 매출 성장률이고 terminal growth까지 선형으로 낮아진다. `margin`은 마지막 해 정상화 FCF margin이며 현재 trailing margin에서 선형으로 이동한다. 희석주식수는 `annual-dilution`만큼 매년 증가하고 세 확률의 합은 1이어야 한다.

각 case는 target price와 현재가 대비 DCF upside/downside, terminal value 비중, 마지막 해 매출·FCF와 누적 희석률을 반환한다. 전체 결과에는 probability-weighted value가 포함된다.

## Sensitivity

```bash
uv run thesis valuation sensitivity <TICKER> \
  --growth N --mature-margin N \
  [--discount-rate N] [--terminal-growth N] [--annual-dilution N]
```

기준 성장률과 할인율의 위아래 한 단계로 3×3 target price 표를 만든다. 입력은 `USER_ASSUMPTION`, 결과는 `MODEL_OUTPUT`이다.

## 공통 계산

- 성장률은 terminal growth까지, FCF margin은 mature margin까지 모델 기간에 걸쳐 선형으로 변한다.
- terminal value는 마지막 해 FCF에 Gordon growth를 적용한다.
- 명시된 discount rate로 현금흐름과 terminal value를 현재가치로 할인해 enterprise value를 계산한다.
- discount rate는 terminal growth보다 커야 한다.
- reverse DCF만 현재 FCF margin과 고정 성장률을 유지하는 단순 모델이다.
