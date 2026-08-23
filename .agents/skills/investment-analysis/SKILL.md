---
name: investment-analysis
description: 기업 데이터·기대치·밸류에이션·최신 뉴스와 catalyst를 종합해 투자 메모와 thesis 변화를 판단한다. "지금 살 만한가", "지난 분석 이후 뭐가 달라졌어" 같은 질문에 사용.
---

# investment-analysis

BUY/SELL 생성기가 아니라 fact, market expectation, scenario의 차이와 지난 판단 이후 변화를 추적한다.

## "업데이트해줘" 실행 순서

1. 가격과 SEC filing을 갱신하고 업데이트 패키지를 만든다.

```bash
uv run thesis data fetch <TICKER>
uv run thesis data macro-fetch
uv run thesis analysis prepare <TICKER>
```

2. evidence의 expectations가 `MISSING` 또는 `STALE`이고 API key를 사용할 수 있으면 `data expectations` 실행 후 `analysis prepare`를 다시 실행한다.

```bash
uv run thesis data expectations <TICKER>
uv run thesis analysis prepare <TICKER>
```

3. Codex 웹 검색으로 최신 뉴스와 catalyst를 확인한다. 종합 투자 판단, 업데이트, 기업 비교에서는 기본 단계이며 Python이 웹 검색이나 LLM 호출을 수행하게 만들지 않는다.

- 이전 분석 이후 기간을 우선 검색한다. 이전 분석이 없으면 최근 7~14일과 다음 실적 이벤트를 확인하되, 오래된 구조적 이슈가 thesis에 중요하면 범위를 넓힌다.
- 출처 우선순위는 SEC·기업 IR/공식 발표·규제기관 같은 1차 자료, 그다음 신뢰할 수 있는 주요 보도다. 검색 결과의 제목이나 snippet만으로 결론 내리지 않고 실제 원문을 연다.
- 기존 thesis를 지지하는 자료와 반박하는 자료를 각각 찾는다. 반대 근거를 찾지 않은 상태에서 `CONFIRMED`라고 판정하지 않는다.
- 실적 분석에서는 숫자만 보지 않고 회사가 공개한 경우 segment, 주식보상, 희석주식수, 재고·매출채권·이연매출, GAAP/non-GAAP 조정 중 thesis에 중요한 항목을 원문에서 확인한다.
- 각 중요한 항목에 사건일/발행일, 출처 URL, `FACT` 또는 `LLM_INFERENCE` 성격을 붙인다. 상충하는 보도는 불확실성을 밝히고 확정 사실처럼 쓰지 않는다.
- 기사 전체를 저장하지 않는다. thesis, guidance, 실적, 제품 출시, 규제, 주요 고객/계약, 자금조달에 실질적인 영향을 주는 근거만 `input_snapshot_json`에 간결한 `news_evidence`로 남긴다.
- 날짜가 확정된 중요 미래 이벤트만 중복을 확인한 뒤 catalyst로 저장한다.

```bash
uv run thesis analysis save-catalyst <TICKER> \
  --event-date YYYY-MM-DD --event-type TYPE \
  --description DESCRIPTION --importance HIGH
```

`data news <TICKER>`는 웹 검색을 사용할 수 없을 때의 fallback 또는 후보 발굴용 보조 수단이다. 출력된 Finnhub 기사는 자동 저장되지 않으므로, 원문과 중요성을 검증하기 전에는 분석 근거나 catalyst로 취급하지 않는다.

4. 품질 게이트를 먼저 따른다.

- `INSUFFICIENT_EVIDENCE`: 판단과 저장을 중단하고 필요한 입력을 알려준다.
- `RESEARCH_ONLY`: 사실 정리와 추가 조사만 수행한다. 방향성 판단, 기대수익률, confidence, 분석 저장을 하지 않는다.
- `DECISION_READY`: 신선한 기대치와 측정 가능한 revision까지 확보된 경우에만 방향성 판단을 허용한다.
- `PARTIAL`: `cannot_conclude` 항목에 관해서는 결론을 내리지 않는다. `PARTIAL`이면서 `DECISION_READY`일 수는 있지만 누락 항목을 명시한다.
- `COMPLETE`: 모든 정량 섹션을 사용할 수 있다.

5. Codex가 다음을 정성적으로 판단한다.

- 시장 관점과 다른 근거가 없으면 `NO_VARIANT_PERCEPTION`이라고 쓴다.
- consensus와 다른 주장에는 `시장이 믿는 것 → 내가 다르게 보는 것 → 근거 → 확인 시점 → 틀렸음을 인정할 조건`을 모두 붙인다. 하나라도 없으면 투자 thesis가 아니라 조사 가설로 남긴다.
- 변동성, 순부채, valuation stretch, revision, concentration을 나열하되 근거 없는 단일 risk score를 만들지 않는다.
- macro는 `macro-context` Skill의 독립 축을 사용해 기업의 매출·마진·할인율·position sizing에 전달되는 경로만 설명한다. Fear & Greed를 내재가치나 단독 BUY/SELL 신호로 사용하지 않는다.
- catalyst는 확정 사실과 추론을 구분한다.
- 이전 thesis는 `CONFIRMED/WEAKENING/INVALIDATED/UNKNOWN` 중 하나로 설명하되 Python 계산값인 것처럼 표현하지 않는다.

### 포지션 관리와 매도 규칙

좋은 기업을 너무 일찍 익절하고 손실 포지션은 진입가에 매여 방치하는 비대칭을 피한다.

- 신규 매수, 이익 중인 보유, 손실 중인 보유를 구분한다. 보유 여부·평균단가·목표 보유기간을 모르면 이를 아는 것처럼 개인화하지 말고 조건부 계획을 제시한다.
- 보유정보는 저장된 포트폴리오 원장을 전제로 하지 않고 사용자가 현재 조사에 제공한 값을 사용한다.
- 매수 금액이나 비중을 묻는 경우에만 현재 수량·평균단가·투자 가능 자산·목표 보유기간·감당 가능한 손실 중 판단에 필요한 값만 묻는다. 비상자금과 가까운 시일의 필요자금은 투자 가능 자산에 포함하지 않는다.
- 종목·섹터 비중 상한은 사용자가 정한 한도일 때만 적용한다. 상한을 목표 비중이나 객관적 최적값으로 바꾸지 않고, 정보가 없으면 임의의 정밀 비중을 제시하지 않는다.
- 매도 판단은 진입가나 단순 수익률이 아니라 현재 가격에서의 forward 기대수익, thesis 상태, 포지션 비중, 대안의 기회비용으로 다시 계산한다. 본전 회복은 투자 근거가 아니다.
- 주가가 올랐다는 이유만으로 전량 익절하지 않는다. thesis가 `CONFIRMED`이고 기대수익이 충분하면 보유를 기본으로 하며, 기대수익 축소·과대 비중·확정 catalyst 직전의 비대칭이 있을 때만 일부 축소를 검토한다.
- 손실 중이어도 thesis가 유지되고 기대수익이 개선되었다는 근거가 있으면 자동 손절하지 않는다. 반대로 무효화 조건이 충족되면 손실 여부와 무관하게 `REDUCE/EXIT`를 명시하고 다음 이벤트까지 미루지 않는다.
- 가격 손절선은 사용자가 단기매매·레버리지·최대손실 한도를 지정한 경우의 risk-budget 도구로만 사용한다. 장기 현물 투자에는 사업·가이던스·마진·밸류에이션 무효화 조건과 재검토 날짜를 우선한다.
- 이익 보호에는 전량 매도보다 단계적 축소를 우선 검토한다. 남은 포지션을 계속 보유할 조건도 함께 적어 상승 여력을 기계적으로 잘라내지 않는다.
- 판단마다 `진입/추가매수 조건`, `유지 조건`, `일부 익절 조건`, `손절 또는 thesis exit 조건`, `시간 기반 재검토 이벤트`를 실행 가능한 형태로 제시한다. 근거 없는 정밀 가격선은 만들지 않고, 사용한 가격선은 valuation 또는 사용자의 risk budget과 연결한다.

6. 종합 업데이트 memo를 append한다. `input_snapshot_json`에는 판단에 사용한 정량 스냅샷과 중요한 `news_evidence`의 날짜·제목·URL·성격을 포함한다.

```bash
uv run thesis analysis save <TICKER> \
  --decision HOLD --confidence 0.6 --expected-return 0.08 \
  --expected-return-horizon-months 12 \
  --expected-return-method PROBABILITY_WEIGHTED_SCENARIO \
  --expected-return-basis PRICE_RETURN --price 200 \
  --thesis-json '[]' --variant-perception-json '{}' --invalidation-json '[]' \
  --model-name codex --model-version MODEL_VERSION \
  --prompt-version investment-analysis-v2 --input-snapshot-json '{}'
```

`expected-return`은 `expected-return-horizon-months` 동안의 누적 기대수익률이며 CLI가 연환산 값을 함께 저장한다. 방법은 `PROBABILITY_WEIGHTED_SCENARIO | BASE_CASE_TARGET | DCF_IRR | OTHER`, 기준은 배당 제외 `PRICE_RETURN` 또는 배당 포함 `TOTAL_RETURN` 중 하나다. 기간·방법·기준이 없으면 방향성 분석을 저장하지 않는다. 서로 다른 기간의 누적 수익률을 직접 비교하지 말고 연환산 값과 bear downside를 함께 본다.

`decision`은 `STRONG_BUY | ACCUMULATE | HOLD | WATCH | REDUCE | EXIT`. 저장된 숫자형 `confidence`는 예측 확률이 아니라 legacy 주관값이므로 사용자에게 확률처럼 제시하지 않는다. 최종 답변에서는 근거 품질을 `충분/부분적/결론 불가`로 표현한다. 숫자에는 기준일과 `FACT/ESTIMATE/MODEL_OUTPUT/LLM_INFERENCE/USER_ASSUMPTION` 성격을 명확히 표시한다.

최종 응답 순서는 `변경된 사실 → 시장 기대 변화 → 반대 근거 → 매크로 환경 변화와 기업 전달 경로 → 가격에 반영된 기대 → 기존 thesis 상태 → 주요 리스크 → 근거 품질 → 판단 → 포지션 관리(진입·유지·일부 익절·손절/thesis exit) → 무효화 조건 → 다음 확인 이벤트`로 고정한다. 웹에서 확인한 최신 사실에는 해당 문장 가까이에 원문 링크를 붙인다.
