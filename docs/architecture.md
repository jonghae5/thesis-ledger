# Architecture

## Purpose

ThesisLedger tracks the gap between reported facts, business quality, market expectations, model scenarios, and Codex's stated thesis. It does not place trades.

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

Focused Skills keep the analysis axes separate:

- `company-data` owns point-in-time market and fundamental facts.
- `business-quality` interprets business economics, durability, reinvestment, earnings quality, capital allocation, and management execution. It reuses company data and does not produce price targets or trade decisions.
- `expectations` owns consensus, revisions, surprise, and comparable guidance.
- `valuation` owns price-implied expectations and scenario values.
- `macro-context` keeps macro signals independent and explains transmission paths.
- `market-pulse` keeps verified news and catalysts separate from Reddit retail sentiment, narratives, and discussion momentum.
- `investment-analysis` orchestrates only the axes material to the question and owns the final thesis judgment.

## Data lifecycle

Provider responses are cached by TTL and normalized before storage. `fundamental_snapshots` is the only canonical SEC fact source and uses actual filing dates to prevent look-ahead bias. It also stores the selected XBRL concept for expanded business-quality facts so alias choices remain auditable.

`estimate_snapshots`, `guidance_snapshots`, and `investment_analysis` are append-only. Schema changes are applied through ordered migrations.

Guidance source discovery only identifies Item 2.02 8-K filing pages. Codex selects the relevant exhibit and normalizes the original language; Python never interprets filing prose or writes a guidance snapshot automatically.

## Public interface

The CLI has three domains plus `doctor`:

- `data`: fetch and inspect company/market inputs
- `data quality`: compute score-free, point-in-time business-quality inputs from canonical annual filings
- `data guidance-sources`: discover SEC earnings-release source candidates without interpreting or saving guidance
- `data evidence/compare`: compose source-backed inputs, including business-quality metrics, and peer rows without a score
- `valuation`: multiples, reverse DCF, scenarios
- `analysis prepare`: combine prior thesis, changes, and current evidence
- `analysis prepare-current`: build current evidence without exposing prior conclusions and optionally freeze it
- `analysis compare-prior`: reveal prior analysis only after an immutable current-evidence bundle exists
- `analysis`: guidance, catalysts, memo history
- `doctor`: freshness, licensing, and reproducibility checks

All commands emit one JSON object and use exit code 1 for failures.

## Non-goals

Portfolio ledger management, broker integration, automatic trading, options, tax lots, multi-agent debate, vector databases, ML price prediction, and customer-facing compliance are outside this repository.
