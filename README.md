# trade-trend-kit

Personal trade trend kit for collecting X finance posts and generating investment trend reports.

The project is being built incrementally so each module can be reviewed before the next feature is added.

## Current Skeleton

- Python package uses the `src/trade_trend_kit` layout.
- CLI entry point is reserved as `trade-trend-kit`.
- Runtime config example is available at `config/x.example.json`.
- Default local config placeholder is available at `config/x.json`.
- Generated runtime data will live under ignored `data/` and `logs/` directories.

## Local Commands

Install dependencies and the package in editable mode first:

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

```bash
python -m trade_trend_kit validate-config
python -m trade_trend_kit fetch-once --fake
python -m trade_trend_kit fetch-once --twikit
python -m trade_trend_kit fetch-once --twikit --llm
python -m trade_trend_kit fetch-once --fake --log-file logs/fetch-once.log
python -m trade_trend_kit run --fake
python -m trade_trend_kit run --twikit --llm
```

`fetch-once --fake` runs a deterministic local end-to-end pipeline. It reads
`config/x.json`, generates fake X posts, saves raw and normalized tweets under
`data/`, analyzes only newly seen tweets, and writes account/daily reports.
`fetch-once --twikit` uses the real Twikit adapter for X collection while
keeping fake analysis by default. Add `--llm` to use an OpenAI-compatible
analysis provider configured by `LLM_*` values in `.env`.

`run --fake` or `run --twikit --llm` starts the scheduled collector. The
scheduler uses `fetch_interval_minutes` from `config/x.json`, runs one cycle
immediately by default, reloads config before each cycle, and prevents
overlapping scheduled runs.

Use `--log-level` and `--log-file` on `fetch-once` or `run` for local
diagnostics. The same values can also be configured with `LOG_LEVEL` and
`LOG_FILE` in `.env`.

Daily reports are also exported as push-ready payloads under
`data/reports/{date}/publish/`. The project writes structured JSON, Markdown,
and plain text so later social-platform or app publishers can consume reports
without reparsing the report archive.

If the LLM returns invalid JSON and the repair attempt also fails, the raw and
repaired model text is archived under `data/reports/{date}/errors/` with account
metadata and source tweet IDs. The archive intentionally excludes API keys,
cookies, and request headers.

## Real Adapter Setup

Copy `.env.example` to `.env` before using real Twikit or LLM integrations.
For Twikit, set `X_USERNAME`, `X_PASSWORD`, and optionally `X_EMAIL`; successful
login can reuse `TWIKIT_COOKIES_PATH` on later runs. For OpenAI-compatible
analysis, set `LLM_API_KEY` and override `LLM_BASE_URL` / `LLM_MODEL` if using
another compatible provider.

## Dependency Policy

- Add runtime dependencies to `requirements.txt`.
- Add test, lint, and development-only dependencies to `requirements-dev.txt`.
- Keep `pyproject.toml` aligned when a dependency is also required for packaging or the CLI entry point.

## Design

- [Detailed design](docs/DETAILED_DESIGN.md)


