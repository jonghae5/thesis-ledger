---
name: company-data
description: 가격·모멘텀과 SEC 재무 데이터를 수집하고 해석한다. "가격 어때", "매출/마진 어때", "재무상태 어때" 같은 질문에 사용.
---

# company-data

가격과 SEC filing 기반 재무 데이터를 한 흐름으로 다룬다. 데이터가 없거나 오래됐으면 먼저 수집한다.

```bash
uv run thesis data fetch <TICKER>
uv run thesis data market <TICKER>
uv run thesis data fundamentals <TICKER> [--as-of YYYY-MM-DD]
uv run thesis data evidence <TICKER>
uv run thesis data compare <TICKER_A> <TICKER_B> [TICKER_C...]
```

`fetch`는 가격과 SEC point-in-time snapshot만 저장한다. 컨센서스는 별도 API와 snapshot 주기가 있으므로 `expectations` Skill이 담당한다.

해석 시 가격 기준일과 filing date를 함께 밝힌다. `market`의 momentum/volatility/200일선 거리와 `fundamentals`의 성장률/FCF margin/net debt를 사실과 모델 계산으로 구분한다. `fundamentals.ttm`이 `TTM_DERIVED`이면 최근 연간 실적에 이후 분기를 전년 동기와 교체한 값이며, 필요한 분기 fact가 없으면 해당 필드는 `null`이다. 데이터가 없거나 stale이면 추정으로 채우지 않는다.

`evidence`는 market/fundamentals/expectations/revisions/valuation/implied expectations/macro/guidance/catalysts를 한 JSON으로 묶는다. `can_research=true`이면 사실 정리와 비교는 가능하다. 방향성 투자 판단은 신선한 기대치와 측정 가능한 revision까지 확보되어 `can_decide=true`일 때만 허용한다. macro가 없거나 stale이면 macro-sensitive scenario calibration은 제한한다. `compare`는 동일 필드를 나란히 보여줄 뿐 종합점수나 자동 순위를 만들지 않는다.
