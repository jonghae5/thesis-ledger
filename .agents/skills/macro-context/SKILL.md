---
name: macro-context
description: 금리·인플레이션·고용·신용·금융환경·VIX·Fear & Greed를 수집하고 기업과 투자 판단에 전달되는 영향을 해석한다. "매크로 환경 어때", "공포지수 어때", "금리 변화가 이 종목에 어떤 영향이야" 같은 질문에 사용.
---

# macro-context

거시지표를 독립 축으로 유지해 기업 scenario와 위험 예산 판단에 입력을 제공한다. 매크로만으로 비중, 단일 risk score 또는 BUY/SELL을 만들지 않는다.

```bash
uv run thesis data macro-fetch
uv run thesis data macro [--as-of YYYY-MM-DD]
```

`macro-fetch`는 FRED의 기준금리·실질금리·10Y/2Y 금리차·Core PCE YoY·10년 기대인플레이션·실업률·신규실업수당·Sahm rule·HY OAS·NFCI·VIX·무역가중 달러와 CNN Fear & Greed를 append-only snapshot으로 저장한다. FRED 값에는 가능한 경우 최근 5년 percentile을 함께 계산한다. 일부 provider가 실패하면 저장 가능한 데이터는 보존하고 `PARTIAL`로 표시한다.

해석 순서:

1. 각 값의 `observation_date`, `snapshot_at`, `source_type`, `transformation`을 확인한다. 서로 발표주기가 다른 지표를 같은 시점의 사실처럼 표현하지 않는다.
2. `rates`, `inflation`, `growth_labor`, `credit_liquidity`, `sentiment_stress`, `currency`를 따로 설명한다. 충돌하는 신호를 종합점수로 감추지 않는다.
3. 기업 질문에서는 해당 변화가 매출, margin, 자금조달, 할인율 중 어디로 전달되는지 설명한다. 연결 근거가 없으면 일반 시장 배경으로만 둔다.
4. Fear & Greed는 투자자의 실제 위험선호와 포지셔닝이 반영된 보조 증거로 사용하되 VIX·momentum·credit과 중복될 수 있음을 밝힌다. 극단적 공포는 저평가, 극단적 탐욕은 고평가를 뜻하지 않는다.
5. 저장된 snapshot이 없는 과거 날짜는 현재 데이터로 소급해 채우지 않는다. `MISSING`/`PARTIAL`이면 결론 범위를 제한한다.

종합 투자 판단과 사용자가 제공한 현재 보유정보·손실 한도의 영향은 `investment-analysis`, 할인율·scenario 계산은 `valuation` Skill과 함께 사용한다.
