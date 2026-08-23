---
name: business-quality
description: 사업 경제성·경쟁우위·재투자·이익의 질·자본배분·경영진 실행력을 평가한다. "좋은 사업인가", "moat가 있나", "ROIC·현금흐름의 질·자본배분이 어떤가" 같은 질문에 사용하며 가격·valuation·BUY/SELL은 판단하지 않는다.
---

# business-quality

현재 실적의 좋고 나쁨을 넘어 그 경제성과 성장이 지속 가능한지 판단한다. `company-data`가 수집한 point-in-time 재무 사실과 결정론적 quality 입력을 재사용한다.

```bash
uv run thesis data quality <TICKER> [--as-of YYYY-MM-DD]
uv run thesis data compare <TICKER> <PEER_A> [PEER_B...]
```

`quality`는 여러 연도의 margin, 성장, capex intensity, 현금전환, 주식수 변화와 순부채를 점수 없이 반환한다. `coverage.warnings`와 `unavailable_dimensions`를 먼저 확인하고, 계산되지 않은 ROIC·SBC·운전자본·M&A 지표를 추정으로 채우지 않는다.

재무 snapshot이 없거나 오래됐으면 `company-data` 기준에 따라 먼저 갱신한다. 최신 10-K·10-Q·8-K, proxy statement, 기업 IR처럼 정형 데이터에 없는 근거는 Codex가 원문을 직접 확인한다. 웹에서 확인한 중요한 사실에는 날짜와 원문 링크를 붙인다.

## 역할 경계

- 매출·margin·FCF·부채·주식수의 수집과 `data quality`의 결정론적 계산은 Python이 담당한다.
- `business-quality`는 그 숫자와 공시가 사업의 경제성, 지속성, 재투자 여력을 무엇을 의미하는지 해석한다.
- 컨센서스·revision·guidance는 `expectations`, 가격에 반영된 기대와 가치 범위는 `valuation`이 담당한다.
- 종합 투자 판단과 thesis 변화는 `investment-analysis`가 담당한다. 이 Skill은 BUY/SELL, 목표가격, 기대수익률 또는 포지션 비중을 만들지 않는다.

## 판단 규칙

- 한 분기나 높은 margin 하나만으로 moat를 주장하지 않는다. 가능한 경우 여러 해와 한 경기 국면 이상의 지속성, 경쟁사 대비 차이, 그 차이를 만든 사업 메커니즘을 함께 확인한다.
- ROIC, incremental return, cash conversion처럼 정의에 따라 달라지는 계산은 입력과 정의를 밝힌다. 필요한 항목이 없으면 정밀 수치나 방향을 추정하지 않는다.
- 회사가 제시한 조정지표와 KPI는 `FACT`가 아니라 회사 정의의 reported metric임을 밝히고, 정의 변경·누락·GAAP 조정을 확인한다.
- 높은 성장률을 재투자 runway로, 높은 시장점유율을 경쟁우위로 자동 해석하지 않는다. 가격, 보조금, 경기, 인수, 공급 부족 같은 대체 설명을 확인한다.
- 경영진 평가는 발언의 인상보다 과거 목표 대비 실행, 자본배분 결과, 보상 구조와 주주 희석을 우선한다.
- 같은 정의와 기간으로 비교할 수 있을 때만 peer를 나란히 본다. 자동 순위나 단일 quality score를 만들지 않는다.
- 숫자는 기준일과 `FACT | MODEL_OUTPUT | LLM_INFERENCE`를 구분한다. 정성적 quality 판정은 항상 `LLM_INFERENCE`다.

전체 사업의 질을 평가할 때는 [평가 프레임](references/assessment-framework.md)을 읽는다. 좁은 질문에는 해당 축만 확인하고 전체 프레임이나 종합 결론으로 확장하지 않는다.

## 답변

이전 평가가 있으면 먼저 무엇이 좋아졌고 나빠졌는지 설명한다. 질문에 필요한 각 축은 `STRONG | MIXED | WEAK | INSUFFICIENT`로 표현하고, 핵심 근거·중요한 반대 근거·악화 또는 확인 조건을 붙인다. 축별 판정을 합산하거나 하나의 종합점수로 변환하지 않는다.

산업 구조상 일반 지표가 맞지 않는 은행·보험·REIT·원자재·바이오는 업종별 핵심 driver를 우선한다. 필요한 업종 근거가 없으면 일반기업 지표로 대신 결론 내리지 않고 `INSUFFICIENT`로 제한한다.
