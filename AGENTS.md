# ThesisLedger agent guide

Codex가 투자 판단을 orchestration하고, `src/`의 CLI는 데이터 수집·저장·결정론적 계산만 수행한다. Python은 LLM을 호출하지 않는다.

## 반드시 지킬 원칙

1. `estimate_snapshots`, `guidance_snapshots`, `investment_analysis`는 append-only다.
2. SEC 재무는 실제 filing date 기준 `fundamental_snapshots`만 canonical source로 사용한다.
3. 숫자는 기준일과 성격(`FACT`, `ESTIMATE`, `MODEL_OUTPUT`, `LLM_INFERENCE`, `USER_ASSUMPTION`)을 구분한다.
4. BUY/SELL보다 지난 분석 이후 무엇이 변했는지 먼저 확인한다.
5. 단일 종합 risk score를 만들지 않는다.

## 질문 라우팅

| 질문 | Skill |
|---|---|
| 종합 투자 판단, thesis 변화, catalyst/risk | `investment-analysis` |
| 가격, 모멘텀, 매출, 마진, 재무상태 | `company-data` |
| 사업 경제성, moat, 재투자, 이익의 질, 자본배분 | `business-quality` |
| 컨센서스, revision, guidance, surprise | `expectations` |
| multiple, reverse DCF, scenario | `valuation` |
| 금리, 인플레이션, 경기, 신용, VIX, 공포탐욕지수 | `macro-context` |

좁은 질문에는 해당 Skill만 사용한다. 실제 절차와 해석 규칙은 `.agents/skills/<name>/SKILL.md`가 canonical source다. `.claude/skills`는 호환용 symlink다.

보유종목 원장이나 투자자 정책 파일은 관리하지 않는다. 보유 여부·수량·평균단가·투자 가능 자산·손실 한도는 필요한 조사에서 사용자가 제공한 현재 값을 사용한다.

## CLI

```bash
uv run thesis data seed
uv run thesis data fetch <TICKER>
uv run thesis data market <TICKER>
uv run thesis data fundamentals <TICKER>
uv run thesis data quality <TICKER> [--as-of YYYY-MM-DD]
uv run thesis data expectations <TICKER>
uv run thesis data revisions <TICKER>
uv run thesis data earnings-surprise <TICKER>
uv run thesis data evidence <TICKER>
uv run thesis data compare <TICKER_A> <TICKER_B> [TICKER_C...]
uv run thesis data catalysts <TICKER>
uv run thesis data news <TICKER>
uv run thesis data macro-fetch
uv run thesis data macro [--as-of YYYY-MM-DD]

uv run thesis valuation multiples <TICKER>
uv run thesis valuation reverse-dcf <TICKER>
uv run thesis valuation scenario <TICKER> [OPTIONS]
uv run thesis valuation sensitivity <TICKER> [OPTIONS]

uv run thesis analysis save-guidance <TICKER> [OPTIONS]
uv run thesis analysis save-catalyst <TICKER> [OPTIONS]
uv run thesis analysis save <TICKER> [OPTIONS]
uv run thesis analysis latest <TICKER>
uv run thesis analysis history <TICKER>
uv run thesis analysis change-since <TICKER> --since-date YYYY-MM-DD
uv run thesis analysis prepare <TICKER>

uv run thesis doctor
```

모든 명령은 stdout에 JSON 한 줄을 출력하며 실패 시 exit code 1을 반환한다.
같은 DuckDB 파일을 여는 CLI 명령은 병렬 실행하지 않고 순차 실행한다.
