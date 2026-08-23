# Architecture

## Purpose

ThesisLedger tracks the gap between reported facts, market expectations, model scenarios, and Codex's stated thesis. It does not place trades.

## Boundaries

```text
Codex + focused Skills
    │ chooses only the analysis needed
    ▼
Typer CLI (JSON stdout)
    ├── providers: Yahoo, SEC, Alpha Vantage, Finnhub
    ├── research service: evidence, quality gates, peer comparison
    ├── tools: deterministic calculations
    └── storage: DuckDB repositories + migrations
```

- Codex owns interpretation, variant perception, risk language, and memo writing.
- Python owns collection, validation, calculation, and persistence. It never calls an LLM.
- `.agents/skills` is canonical; `.claude/skills` is a compatibility symlink.

## Data lifecycle

Provider responses are cached by TTL and normalized before storage. `fundamental_snapshots` is the only SEC source and uses actual filing dates to prevent look-ahead bias.

`estimate_snapshots`, `guidance_snapshots`, and `investment_analysis` are append-only. The repository targets newly created databases; schema compatibility with older local DuckDB files is not maintained.

## Public interface

The CLI has three domains plus `doctor`:

- `data`: fetch and inspect company/market inputs
- `data evidence/compare`: compose source-backed inputs and peer rows without a score
- `valuation`: multiples, reverse DCF, scenarios
- `analysis prepare`: combine prior thesis, changes, and current evidence
- `analysis`: guidance, catalysts, memo history
- `doctor`: freshness, licensing, and reproducibility checks

All commands emit one JSON object and use exit code 1 for failures.

## Non-goals

Portfolio ledger management, broker integration, automatic trading, options, tax lots, multi-agent debate, vector databases, ML price prediction, and customer-facing compliance are outside this repository.
