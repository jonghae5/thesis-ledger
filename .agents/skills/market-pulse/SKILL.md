---
name: market-pulse
description: 최신 기업 뉴스·공식 발표·catalyst와 Reddit retail sentiment를 조사해 사실, bull/bear narrative, 관심도 변화를 분리한다. "최근 뉴스 뭐야", "Reddit 분위기 어때", "민심이 바뀌었어?" 같은 질문에 사용하며 종합 투자 판단이나 valuation은 만들지 않는다.
---

# market-pulse

뉴스의 사실성과 Reddit의 시장 심리를 같은 점수로 합치지 않고 각각 독립된 근거 축으로 조사한다. Python CLI가 웹 검색이나 LLM 분석을 수행하게 만들지 않는다.

## 모드 선택

질문에 필요한 모드만 사용한다.

- 최신 뉴스·공식 발표·catalyst가 핵심이면 [뉴스와 catalyst](references/news-catalysts.md)만 읽는다.
- Reddit 분위기·민심·bull/bear 논거·관심도 변화가 핵심이면 [Reddit sentiment](references/reddit-sentiment.md)만 읽는다.
- `market pulse`, 뉴스와 민심의 괴리, Reddit 주장의 사실 검증을 요청하면 두 문서를 모두 읽고 마지막에 reality check를 수행한다.

회사명과 ticker가 중의적이면 검색 전에 상장사와 주요 별칭을 확인한다. 모든 조사에서 기준 시각과 실제 확인한 기간을 밝힌다.

## 근거 역할

- 공식 발표·SEC·규제기관·기업 IR에서 확인한 사건은 날짜와 원문이 있을 때 `FACT`다.
- 보도는 원사건을 찾는 단서 또는 보조 근거다. 검색 snippet만으로 사실을 확정하지 않는다.
- Reddit sentiment, narrative cluster, discussion momentum은 표본을 해석한 `LLM_INFERENCE`다. Reddit 게시물에 적힌 재무·계약·규제 주장은 별도 원문 확인 전에는 `FACT`가 아니다.
- sentiment와 mention volume을 구분한다. 강한 확신의 소수 글을 폭넓은 합의로, 검색 결과가 많은 것을 bullish sentiment로 바꾸지 않는다.
- 단일 종합 sentiment/risk score를 만들지 않는다. 방향성 label은 근거가 충분할 때만 정성적으로 사용한다.

이 Skill은 BUY/SELL, 목표가격, 기대수익률, 포지션 비중을 만들지 않는다. 행동 판단이나 thesis 변화는 `investment-analysis`가 이 결과를 supplemental evidence로 사용해 판단한다. Reddit 분위기만으로 `can_decide=true`가 되거나 기존 thesis가 `CONFIRMED`되지는 않는다.

## 출력

질문에 직접 필요한 항목만 쓰되 다음 구분을 유지한다.

1. 기준 시각·검색 범위·근거 품질
2. 확인된 뉴스와 catalyst (`FACT`)
3. Reddit sentiment와 discussion momentum (`LLM_INFERENCE`)
4. bull/bear narrative와 핵심 disagreement
5. reality check: Reddit 주장 중 확인됨·반박됨·미확인
6. 분석에 실제 사용한 뉴스 원문과 Reddit thread·comment URL, 중요한 한계

뉴스만 또는 Reddit만 요청한 경우 비어 있는 축을 형식적으로 추가하지 않는다. 최신 사실과 결론에 영향을 준 Reddit 근거에는 해당 문장 가까이에 직접 링크를 붙인다. Reddit은 검색 결과 페이지나 subreddit 목록이 아니라 개별 thread URL을 사용하고, 특정 댓글의 논거를 인용했으면 해당 comment permalink도 제공한다. 검색 결과가 부족하거나 날짜·engagement를 검증할 수 없으면 `INSUFFICIENT` 또는 `UNKNOWN`이라고 쓰고 추정치로 채우지 않는다.

v1은 웹 검색 기반 일회성 조사다. Reddit 원문·댓글 전문을 저장하거나 일별 sentiment 시계열을 만들지 않는다. 전체 댓글 tree, 정확한 `top/new/hot`, 대량 수집, 일별 비교 저장이 반복적으로 필요해질 때만 Reddit API 또는 MCP 확장을 검토한다.
