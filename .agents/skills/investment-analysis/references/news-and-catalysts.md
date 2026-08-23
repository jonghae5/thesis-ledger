# 뉴스와 catalyst 조사

종합 업데이트, 최신 뉴스, catalyst 또는 실적 이후 변화가 질문에 포함될 때만 이 문서를 읽는다.

Codex가 직접 웹에서 이전 분석 이후의 자료를 우선 확인한다. 이전 분석이 없으면 최근 7~14일과 다음 실적 이벤트부터 보되, thesis에 중요한 구조적 이슈는 필요한 만큼 범위를 넓힌다. Python CLI가 웹 검색이나 LLM 호출을 수행하게 만들지 않는다.

- SEC·기업 IR·공식 발표·규제기관 등 1차 자료를 우선하고 주요 보도를 보조로 사용한다. 검색 결과 제목이나 snippet만으로 결론 내리지 않는다.
- 기존 thesis를 지지하는 근거와 반박하는 근거를 모두 찾는다. 반대 근거를 확인하지 않은 채 `CONFIRMED`로 판정하지 않는다.
- 실적에서는 중요한 경우 segment, 주식보상, 희석주식수, 재고·매출채권·이연매출과 GAAP/non-GAAP 조정을 원문에서 확인한다.
- 중요한 근거마다 사건일 또는 발행일, 원문 URL, `FACT` 또는 `LLM_INFERENCE`를 붙인다. 상충하는 자료는 불확실성을 남긴다.
- 기사 전문은 저장하지 않는다. thesis, guidance, 실적, 제품, 규제, 주요 계약 또는 자금조달에 실질적인 근거만 `input_snapshot_json.news_evidence`에 요약한다.
- 날짜가 확정된 중요한 미래 이벤트만 기존 항목과 중복을 확인한 뒤 catalyst로 저장한다.

```bash
uv run thesis analysis save-catalyst <TICKER> \
  --event-date YYYY-MM-DD --event-type TYPE \
  --description DESCRIPTION --importance HIGH
```

`data news <TICKER>`는 웹 검색을 사용할 수 없을 때 후보를 찾는 fallback이다. 원문과 중요성을 검증하기 전에는 분석 근거나 catalyst로 취급하지 않는다.
