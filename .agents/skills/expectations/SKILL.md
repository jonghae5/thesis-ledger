---
name: expectations
description: 컨센서스·revision·실적 surprise·경영진 guidance를 수집하고 비교한다. "시장 기대치 어때", "추정치 바뀌었어" 같은 질문에 사용.
---

# expectations

시장의 기대 수준과 그 변화 방향을 한 흐름에서 다룬다.

```bash
uv run thesis data expectations <TICKER> [--period current|next]
uv run thesis data revisions <TICKER> [--fiscal-period YYYY-MM-DD]
uv run thesis data earnings-surprise <TICKER>
uv run thesis data guidance-sources <TICKER> [--days N] [--limit N]
uv run thesis analysis save-guidance <TICKER> \
  --revenue-low N --revenue-high N --fiscal-period FY2027 \
  --guidance-scope FULL_YEAR --currency USD --value-unit MILLIONS \
  --source-filing 10-Q --source-date YYYY-MM-DD
```

`expectations`는 Alpha Vantage를 먼저 사용하고 실패하면 yfinance로 전환한다. 모두 실패했지만 저장된 snapshot이 있으면 새 행을 만들지 않고 `STALE`로 반환한다. 실적 surprise와 earnings calendar는 Alpha Vantage → Finnhub → yfinance 순서로 전환한다. provider별 성공·실패는 `provider_attempts`와 provenance에서 확인한다.

한국 종목용 `korea_stock` MCP는 컨센서스, estimate revision, earnings surprise, guidance snapshot을 제공하지 않는다. 6자리 한국 종목에 미국 종목용 provider나 CLI를 억지로 적용하지 않고 해당 기대치 축을 `MISSING`으로 명시한다. 최근 증권사별 전망과 목표주가 원문이 질문에 필요하면 `korea-research-reports` Skill을 사용하되, 검색된 일부 리포트를 시장 전체 컨센서스나 동종 provider의 완전한 revision snapshot으로 취급하지 않는다. 별도 동종 provider의 시계열 snapshot이 확보되기 전에는 revision이나 방향성 투자 판단을 만들지 않는다.

정상 수집만 snapshot을 append한다. revision은 같은 provider에서 서로 다른 날짜의 snapshot이 둘 이상 있을 때만 의미가 있다. provider가 바뀌면 이전 provider의 숫자와 비교하지 않고 `provider_switch=true`, revision은 충분한 동종 history가 쌓일 때까지 `null`로 둔다. analyst count가 작거나 fallback/`STALE`이면 그 한계를 명시한다.

Guidance 조사 전 `guidance-sources`로 Item 2.02 8-K filing page를 찾는다. 반환값은 `CANDIDATE_SOURCE`일 뿐 guidance 존재나 숫자의 확정 근거가 아니다. Codex가 filing index에서 earnings release 원문을 직접 확인한 뒤에만 기간·범위·통화·단위를 정규화해 `save-guidance`를 실행한다.

Guidance 추출은 Codex 판단이며 Python은 원문 후보 발견, 저장, 비교 가능한 이전 snapshot 대비 `RAISED/MAINTAINED/LOWERED` 계산만 담당한다. `fiscal_period`, `guidance_scope`, `currency`, `value_unit`이 모두 같은 snapshot끼리만 비교한다. 하나라도 다르면 `NOT_COMPARABLE`이며 상향·하향으로 해석하지 않는다. 원문의 reported/organic 및 GAAP/non-GAAP 기준이 중요하면 `input_snapshot_json`에도 남기고 서로 다른 기준을 정성적으로 직접 비교하지 않는다. 컨센서스·revision·guidance만으로 BUY/SELL을 판정하지 않는다.
