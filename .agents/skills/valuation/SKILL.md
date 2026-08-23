---
name: valuation
description: forward/trailing multiple, reverse DCF와 bear/base/bull 시나리오로 가격에 반영된 기대와 가치 범위를 판단한다. "현재 가격에 얼마나 성장이 반영됐어", "밸류에이션 어때" 같은 질문에 사용.
---

# valuation

상대 배수, 가격에 내재된 기대, 가정별 가치 범위를 구분한다. 점추정 목표가격보다 어떤 성장·margin·할인율이 결과를 만드는지 보여준다.

```bash
uv run thesis valuation multiples <TICKER>
uv run thesis valuation reverse-dcf <TICKER> [OPTIONS]
uv run thesis valuation scenario <TICKER> [OPTIONS]
uv run thesis valuation sensitivity <TICKER> [OPTIONS]
```

모든 계산은 SEC fundamentals가 필요하므로 없으면 `data fetch`를 먼저 실행한다. `multiples`와 `scenario`는 신선한 가격도 필요하다. 컨센서스가 없으면 forward 필드는 `null`이며 trailing과 섞어 표현하지 않는다.

## 판단 규칙

- reverse DCF의 implied revenue CAGR은 목표가격이 아니라 현재 가격의 대략적인 hurdle이다. 컨센서스와 독립적인 base case가 있으면 같은 기간·기준으로 나란히 비교한다.
- scenario의 growth, mature FCF margin, probability와 dilution은 `USER_ASSUMPTION` 또는 근거가 기록된 `LLM_INFERENCE`다. 최근 최고 성장률·margin을 장기 가정으로 복사하지 않는다.
- 컨센서스가 명시하는 기간까지만 anchor로 사용하고 이후에는 산업 성숙도와 경쟁을 반영해 fade한다.
- DCF upside/downside를 모델 기간의 보유수익률이나 연환산 수익률로 표현하지 않는다. probability-weighted value도 시장 consensus 목표가격이 아니다.
- terminal value 비중이 75%를 넘거나 결과가 할인율에 크게 흔들리면 목표가격보다 민감도와 가정 취약성을 먼저 제시한다.
- trailing FCF가 음수이거나 운전자본·일회성 항목으로 크게 왜곡되면 계산을 중단하고 정상화 근거부터 확보한다.

reverse DCF, scenario 또는 sensitivity를 실제로 실행하거나 계산을 설명할 때만 [DCF 모델 명세](references/dcf-model.md)를 읽는다.

은행·보험에는 일반 기업 DCF를 사용하지 않고 자본·ROE·P/B를 우선한다. REIT는 AFFO와 NAV, 원자재 기업은 mid-cycle 가격과 NAV를 우선한다.

## 한국 종목

현재 valuation CLI는 SEC fundamentals 전용이므로 6자리 한국 종목에 실행하지 않는다. `korea_stock.get_valuation`의 고정 멀티플 모델도 사용하지 않는다. canonical DART snapshot과 결정론적 adapter가 추가되기 전에는 시세·재무 사실만 정리하고 정밀 가치 범위나 기대수익률을 만들지 않는다.

## 매크로와 할인율

금리 변화나 scenario calibration이 질문에 중요할 때만 저장된 macro snapshot을 확인하고, 없거나 stale이면 `data macro-fetch`를 실행한다. 기본 9%는 객관적 WACC가 아니라 모델 기본값이다. 실질금리와 신용환경 변화가 크면 여러 할인율로 민감도를 계산하고 선택값의 성격을 표시한다. Fear & Greed와 VIX는 DCF 입력으로 직접 사용하지 않는다.
