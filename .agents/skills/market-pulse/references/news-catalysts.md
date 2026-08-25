# 뉴스와 catalyst 조사

최신 뉴스·공식 발표·catalyst가 질문에 포함될 때 읽는다.

## 범위와 출처

이전 분석 이후의 자료를 우선 확인한다. 이전 분석이 없으면 최근 7~14일과 다음 실적 이벤트부터 보되, thesis에 중요한 구조적 이슈는 필요한 만큼 범위를 넓힌다.

- SEC·기업 IR·공식 발표·규제기관 등 1차 자료를 우선하고 주요 보도를 보조로 사용한다.
- 검색 결과 제목이나 snippet을 최종 근거로 쓰지 않고 실제 원문을 연다.
- 보도일과 사건 발생일이 다르면 둘을 구분한다. 오래된 사건을 재보도한 글을 새 catalyst로 세지 않는다.
- 기존 thesis를 지지하는 근거와 반박하는 근거를 모두 찾는다. 반대 근거를 확인하지 않은 채 긍정적으로 요약하지 않는다.
- 실적에서는 중요한 경우 segment, 주식보상, 희석주식수, 재고·매출채권·이연매출과 GAAP/non-GAAP 조정을 원문에서 확인한다.
- 중요한 근거마다 사건일 또는 발행일, 원문 URL, `FACT` 또는 `LLM_INFERENCE`를 붙인다. 상충하는 자료는 불확실성을 남긴다.

기사 전문은 저장하지 않는다. thesis, guidance, 실적, 제품, 규제, 주요 계약 또는 자금조달에 실질적인 내용만 요약한다. `uv run thesis data news <TICKER>`는 웹 검색을 사용할 수 없을 때 후보를 찾는 fallback이며, 원문과 중요성을 검증하기 전에는 분석 근거나 catalyst로 취급하지 않는다.

## Catalyst 저장

사용자가 종합 업데이트나 기록을 요청했고 `investment-analysis`가 저장을 진행할 때만, 날짜가 확정된 중요한 미래 이벤트를 기존 항목과 중복 확인 후 저장한다. 이 좁은 조사만으로 자동 저장하지 않는다.

```bash
uv run thesis analysis save-catalyst <TICKER> \
  --event-date YYYY-MM-DD --event-type TYPE \
  --description DESCRIPTION --importance HIGH
```
