---
name: company-data
description: 가격·모멘텀과 SEC 또는 DART 재무 데이터를 수집하고 해석한다. "가격 어때", "매출/마진 어때", "재무상태 어때" 같은 질문에 사용.
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

## 한국 종목

6자리 종목코드이거나 회사명이 KOSPI·KOSDAQ 상장사로 확인되면 `korea_stock` MCP를 사용한다. 이름만 주어졌거나 종목코드가 불확실하면 `search_company`로 먼저 확인하고, 질문 범위에 따라 `get_quote`, `get_financials`, `get_risk_flags`만 호출한다. `get_risk_flags`의 `disclosure_days`는 기본 30일로 제한하고 더 긴 기간은 질문에 필요할 때만 사용한다.

MCP의 원천 시세·재무 숫자는 응답의 기준일과 `data_source`가 확인될 때 `FACT`, 비율·성장률·risk flag는 결정론적 `MODEL_OUTPUT`으로 구분한다. `get_financials`는 현재 개별 재무 숫자의 실제 filing date와 접수번호를 제공하지 않으므로 `fundamental_snapshots`에 저장하거나 point-in-time/as-of 근거로 사용하지 않는다. MCP에는 포트폴리오 수량·평균단가·자산 같은 개인 정보를 보내지 않는다.

해석 시 가격 기준일과 filing date를 함께 밝힌다. `market`의 momentum/volatility/200일선 거리와 `fundamentals`의 성장률/FCF margin/net debt를 사실과 모델 계산으로 구분한다. `fundamentals.ttm`이 `TTM_DERIVED`이면 최근 연간 실적에 이후 분기를 전년 동기와 교체한 값이며, 필요한 분기 fact가 없으면 해당 필드는 `null`이다. 데이터가 없거나 stale이면 추정으로 채우지 않는다.

`evidence`는 다른 분석 축까지 함께 확인해야 할 때만 사용한다. 좁은 가격·재무 질문을 방향성 투자 판단으로 확장하지 않는다. `compare`는 동일 필드를 나란히 보여줄 뿐 종합점수나 자동 순위를 만들지 않는다.

사업 경제성·경쟁우위·재투자·이익의 질·자본배분의 지속성을 묻는 질문은 `business-quality`가 이 Skill의 point-in-time 숫자를 재사용해 해석한다. 높은 성장률·margin·FCF만으로 이 Skill에서 moat나 좋은 사업을 판정하지 않는다.
