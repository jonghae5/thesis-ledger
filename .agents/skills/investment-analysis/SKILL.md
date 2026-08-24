---
name: investment-analysis
description: 기업 데이터·기대치·밸류에이션·최신 뉴스와 catalyst를 종합해 투자 메모와 thesis 변화를 판단한다. "지금 살 만한가", "지난 분석 이후 뭐가 달라졌어" 같은 질문에 사용.
---

# investment-analysis

BUY/SELL 생성기가 아니라 fact, market expectation, scenario의 차이와 지난 판단 이후 변화를 추적한다.

## 한국 종목 조사 경로

6자리 종목코드이거나 KOSPI·KOSDAQ 회사로 확인되면 미국 종목용 `data fetch`와 `analysis prepare` 대신 `korea_stock` MCP의 `search_company`, `get_quote`, `get_financials`, `get_risk_flags`를 사용한다. 최근 공시는 기본 30일로 제한하고 접수일·접수번호·DART 원문 링크를 중요한 사건의 `FACT` 근거로 사용한다.

이 MCP는 컨센서스·revision을 제공하지 않고 연간 재무에 실제 filing date를 붙이지 않으므로 현재 한국 종목은 `can_research=true`, `can_decide=false` 범위다. `investment_analysis`나 `fundamental_snapshots`에 저장하지 않고, 방향성 판단·기대수익률·confidence를 만들지 않는다. 최신 뉴스와 catalyst는 필요한 경우 뉴스 reference에 따라 별도 확인하며, 포트폴리오 수량·평균단가·자산 같은 개인 정보는 MCP에 전달하지 않는다.

최근 증권사 전망·목표주가·투자의견 또는 리포트 원문이 질문에 중요하면 `korea-research-reports` Skill로 최근 30일 자료를 확인한다. 이는 supplemental evidence이며, 일부 검색 리포트를 시장 전체 컨센서스 anchor로 바꾸거나 `can_decide=true`의 근거로 사용하지 않는다.

## "업데이트해줘" 실행 순서

1. 가격과 SEC filing을 갱신하고 이전 분석을 포함하지 않은 현재 evidence로 품질을 먼저 확인한다. 독립 판단을 작성하기 전에는 `analysis prepare`, `analysis latest`, `analysis history`로 이전 결론을 읽지 않는다.

```bash
uv run thesis data fetch <TICKER>
uv run thesis analysis prepare-current <TICKER>
```

macro가 없거나 stale이고 질문의 결론에 중요할 때만 `data macro-fetch` 후 prepare를 다시 실행한다.

2. `expectation_anchors`가 비어 있으면 근거를 보강한다. API key를 사용할 수 있으면 expectations를 갱신한다. 비교 가능한 최신 경영진 guidance가 원문에 있으면 `expectations` Skill의 기준대로 저장한다. 어떤 경로도 확보되지 않으면 `can_decide=false`를 유지한다.

```bash
uv run thesis data expectations <TICKER>
uv run thesis analysis prepare-current <TICKER>
```

3. 종합 업데이트, 최신 뉴스, catalyst 또는 실적 이후 변화를 다룰 때는 [뉴스와 catalyst 조사](references/news-and-catalysts.md)를 읽고 웹 원문을 확인한다. 좁은 재무·valuation 질문에는 이 절차를 자동으로 확장하지 않는다.

4. 필요한 현재 근거가 준비되면 immutable evidence bundle을 만들고, 이전 thesis를 보지 않은 상태에서 현재의 기대 대비 차이·valuation·반대 근거·무효화 조건을 먼저 작성한다.

```bash
uv run thesis analysis prepare-current <TICKER> --freeze
```

그 후 반환된 `bundle_id`로만 이전 분석을 공개해 독립 판단과 비교한다. 이전 결론은 현재 판단의 출발점이 아니라 `CONFIRMED | WEAKENING | INVALIDATED | UNKNOWN` 비교 대상이다.

```bash
uv run thesis analysis compare-prior <TICKER> --evidence-bundle-id BUNDLE_ID
```

5. `evidence.quality`의 세 축만 사용한다.

- `completeness`: 전체 입력의 완전성인 `COMPLETE/PARTIAL/INSUFFICIENT`. 판단 허용 여부로 사용하지 않는다.
- `can_research`: false면 판단과 저장을 중단하고 필요한 핵심 입력을 알린다.
- `can_decide`: false면 사실 정리만 수행하고 방향성 판단·기대수익률·confidence·분석 저장을 하지 않는다.

`can_decide`는 `CONSENSUS_REVISION` 또는 `GUIDANCE_VS_PRICE_IMPLIED`처럼 `expectation_anchors`에 검증 가능한 경로가 있을 때만 true다. `cannot_conclude`에 든 항목은 다른 축이 충분해도 결론 내리지 않는다.

6. Codex가 다음을 정성적으로 판단한다.

- 시장 관점과 다른 근거가 없으면 `NO_VARIANT_PERCEPTION`이라고 쓴다.
- consensus와 다른 주장에는 `시장이 믿는 것 → 내가 다르게 보는 것 → 근거 → 확인 시점 → 틀렸음을 인정할 조건`을 모두 붙인다. 하나라도 없으면 투자 thesis가 아니라 조사 가설로 남긴다.
- 장기 thesis가 사업의 지속성에 의존하면 `business-quality` Skill로 사업 경제성·경쟁우위·재투자·이익의 질·자본배분 중 중요한 축을 확인한다. quality 판정을 가격 매력도나 BUY/SELL로 바꾸지 않고 종합 판단의 독립 근거로 사용한다.
- 변동성, 순부채, valuation stretch, revision, concentration을 나열하되 근거 없는 단일 risk score를 만들지 않는다.
- macro는 `macro-context` Skill의 독립 축을 사용해 기업의 매출·마진·할인율·position sizing에 전달되는 경로만 설명한다. Fear & Greed를 내재가치나 단독 BUY/SELL 신호로 사용하지 않는다.
- catalyst는 확정 사실과 추론을 구분한다.
- 이전 thesis는 `CONFIRMED/WEAKENING/INVALIDATED/UNKNOWN` 중 하나로 설명하되 Python 계산값인 것처럼 표현하지 않는다.

보유·추가매수·매도·손절·익절·비중 질문이면 [포지션 관리](references/position-management.md)를 읽는다. 일반 기업 분석에서는 사용자 보유정보를 요구하거나 포지션 조언으로 자동 확장하지 않는다.

7. 사용자가 종합 업데이트나 thesis 기록을 요청했고 `can_decide=true`일 때만 memo를 append한다. 좁은 질문이나 `can_decide=false` 조사 결과는 저장하지 않는다. `evidence_bundle_id`는 독립 판단에 사용한 frozen bundle을 가리킨다. `input_snapshot_json`에는 bundle 밖에서 확인한 중요한 `news_evidence`의 날짜·제목·URL·성격만 supplemental evidence로 포함한다.

```bash
uv run thesis analysis save <TICKER> \
  --decision HOLD --confidence 0.6 --expected-return 0.08 \
  --expected-return-horizon-months 12 \
  --expected-return-method PROBABILITY_WEIGHTED_SCENARIO \
  --expected-return-basis PRICE_RETURN --price 200 \
  --thesis-json '[]' --variant-perception-json '{}' --invalidation-json '[]' \
  --evidence-bundle-id BUNDLE_ID \
  --model-name codex --model-version MODEL_VERSION \
  --prompt-version investment-analysis-v3 --input-snapshot-json '{}'
```

`expected-return`은 `expected-return-horizon-months` 동안의 누적 기대수익률이며 CLI가 연환산 값을 함께 저장한다. 방법은 `PROBABILITY_WEIGHTED_SCENARIO | BASE_CASE_TARGET | DCF_IRR | OTHER`, 기준은 배당 제외 `PRICE_RETURN` 또는 배당 포함 `TOTAL_RETURN` 중 하나다. 기간·방법·기준이 없으면 방향성 분석을 저장하지 않는다. 서로 다른 기간의 누적 수익률을 직접 비교하지 말고 연환산 값과 bear downside를 함께 본다.

`decision`은 `STRONG_BUY | ACCUMULATE | HOLD | WATCH | REDUCE | EXIT`. 저장된 숫자형 `confidence`는 예측 확률이 아니라 legacy 주관값이므로 사용자에게 확률처럼 제시하지 않는다. 최종 답변에서는 근거 품질을 `충분/부분적/결론 불가`로 표현한다. 숫자에는 기준일과 `FACT/ESTIMATE/MODEL_OUTPUT/LLM_INFERENCE/USER_ASSUMPTION` 성격을 명확히 표시한다.

답변은 질문에 직접 필요한 축만 사용한다. 신규 매수·추가매수·보유·축소·매도처럼 행동 판단을 요청하면 [투자 조언 출력 계약](references/advice-contract.md)을 읽고 적용한다.

- 전체 업데이트: 변경된 사실 → 기대 변화 → 중요한 business quality 변화 → 반대 근거 → 가격에 반영된 기대 → thesis 상태 → 판단·리스크 → 무효화 조건 → 다음 이벤트. Quality가 thesis에 중요하지 않거나 새 근거가 없으면 형식적으로 추가하지 않는다.
- 지금 살 만한지: 기대 대비 차이 → valuation과 bear downside → 판단 → 진입 및 재검토 조건.
- 하락 원인: 확인된 사건 → 기대치 변화 → thesis 영향 → 다음 확인점. 원인이 확인되지 않으면 추정이라고 밝힌다.
- 매도 여부: 현재 forward 기대수익 → thesis·무효화 상태 → 유지/축소/exit 조건. 포지션 reference를 함께 적용한다.
- 좁은 질문: 해당 축만 답하고 종합 memo 형식을 강제하지 않는다.

모든 답변에서 근거 품질과 중요한 반대 근거를 생략하지 않는다. 웹에서 확인한 최신 사실에는 해당 문장 가까이에 원문 링크를 붙인다.
