# Reddit sentiment 조사

Reddit의 최근 투자자 분위기, narrative, disagreement 또는 discussion momentum이 질문에 포함될 때 읽는다.

## 검색 구성

웹 검색은 Reddit 전용 검색 묶음과 사실 검증용 검색 묶음을 분리한다.

Reddit 묶음은 가능한 도구에서 domain filter를 `reddit.com`으로 제한한다. OpenAI Responses API를 직접 구성하는 환경이면 `web_search`에 다음과 동등한 설정을 사용한다.

```json
{
  "type": "web_search",
  "filters": {"allowed_domains": ["reddit.com"]},
  "search_context_size": "high"
}
```

domain filter를 지원하지 않는 환경에서는 각 query에 `site:reddit.com`을 넣고, 결과 URL의 host가 실제 Reddit인지 확인한다. `search_context_size: high`는 더 많은 세부 문맥을 제공할 뿐 글 수·댓글 수·인용 수를 보장하지 않는다.

검색어는 ticker 하나에 의존하지 말고 회사명·제품명·상장사 별칭을 조합한다. 예:

- `<TICKER> stock Reddit`
- `<COMPANY> stock bull bear`
- `<TICKER> site:reddit.com/r/stocks`
- `<TICKER> site:reddit.com/r/investing`
- `<TICKER> site:reddit.com/r/wallstreetbets`
- `<TICKER> site:reddit.com/r/ValueInvesting`
- 회사 관련 subreddit이 확인되면 해당 subreddit query

ticker가 일상 단어나 다른 자산의 symbol과 겹치면 회사명·거래소·`stock`을 함께 넣어 오탐을 제거한다. 회사 제품 사용자 불만과 주식 thesis를 구분한다.

## 시간과 표본

기본 관측 구간은 최근 7일이며 최근 24시간을 별도로 본다. 사용자가 다른 기간을 지정하면 그 기간을 따른다.

- 가능한 경우 서로 독립된 thread를 여러 개 열고 실제 게시 시각, subreddit, 본문과 대표 댓글을 확인한다.
- 동일 기사 링크를 반복 공유한 글, crosspost, 복제된 문구는 독립 narrative로 중복 집계하지 않는다.
- 검색 결과가 최신순·전체 표본이라고 가정하지 않는다. 실제 Reddit의 `top/new/hot` 정렬을 제어했다고 표현하지 않는다.
- 검색 snippet만 잡히거나 원문·댓글을 열 수 없으면 접근 가능한 내용의 범위를 밝힌다.
- score·댓글 수가 보이고 같은 시점에 비교 가능할 때만 engagement를 보조 가중치로 사용한다. 보이지 않는 수치를 추정하지 않는다.
- 고 engagement thread 하나가 전체 subreddit 또는 retail investor 전체를 대표한다고 단정하지 않는다.

확인한 thread마다 가능한 범위에서 `게시 시각 | subreddit | 제목 | direct URL | 보이는 score·댓글 수 | post 입장 | 댓글의 주요 반론`을 메모한다. 작성자 이름이나 개인 정보는 분석에 필요하지 않으면 재노출하지 않는다.

## 해석

먼저 thread별 주장을 추출한 뒤 유사한 논거를 narrative로 묶는다.

- bullish narrative
- bearish narrative
- 가까운 catalyst와 기대
- 반복되는 risk
- 같은 사실에 대한 해석 차이
- post와 댓글 사이의 disagreement

sentiment는 근거가 충분할 때 `BULLISH | MILDLY_BULLISH | MIXED | MILDLY_BEARISH | BEARISH` 중 하나로 요약하고 반드시 `LLM_INFERENCE`라고 표시한다. 표본이 적거나 한쪽 subreddit에 치우치면 `INSUFFICIENT`를 사용한다. 긍정·부정 단어를 세어 기계적인 숫자 점수를 만들지 않는다.

discussion momentum은 최근 24시간과 그 이전 6일의 관측 결과를 비교해 `RISING | STABLE | FALLING | UNKNOWN`으로 표현한다. 검색으로 확인한 thread 수와 engagement 방향이 모두 비교 가능할 때만 방향을 부여한다. mention volume이 증가해도 sentiment 방향이 같다고 추론하지 않는다.

## Reality check

Reddit 묶음이 끝난 뒤에만, 투자 판단에 중요한 주장을 Reddit 밖의 출처로 검증한다. 이 검색은 Reddit domain filter를 제거한다.

- 실적·guidance·계약·규제·제품 발표는 기업 IR, SEC, 규제기관 등 1차 자료를 우선한다.
- 가격 움직임의 원인을 Reddit consensus로 확정하지 않는다.
- 검증 결과를 `CONFIRMED_FACT | CONTRADICTED | UNVERIFIED`로 나누고, 사실과 해석을 섞지 않는다.
- Reddit에서 새롭고 투자에 중요한 반대 논거가 발견되면 종합 판단에서 누락하지 않되, 그 존재 자체를 진실의 증거로 사용하지 않는다.

## URL 출력 계약

- 최종 결론이나 narrative cluster에 실제 영향을 준 thread는 모두 개별 게시물 direct URL을 붙인다. 검색 결과 페이지, Reddit 홈, subreddit 목록 URL로 대체하지 않는다.
- 특정 댓글을 근거로 disagreement나 반론을 설명하면 thread URL과 함께 해당 comment permalink를 붙인다.
- 같은 narrative를 반복하는 중복 thread는 모두 나열하지 않고 대표 링크를 선택하되, `확인한 thread 수`와 `링크한 대표 thread 수`를 구분해 밝힌다.
- 접근할 수 없는 URL, 삭제된 글, 날짜를 확인할 수 없는 글은 상태를 표시하고 핵심 결론의 단독 근거로 사용하지 않는다.
- 게시물·댓글을 길게 복제하지 않고 핵심 논지만 요약한다.
