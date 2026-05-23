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
python -m trade_trend_kit fetch-once
python -m trade_trend_kit run
```

These commands are scaffolded in step 1 and will gain real behavior in later steps.

## Dependency Policy

- Add runtime dependencies to `requirements.txt`.
- Add test, lint, and development-only dependencies to `requirements-dev.txt`.
- Keep `pyproject.toml` aligned when a dependency is also required for packaging or the CLI entry point.

## Design

- [Detailed design](docs/DETAILED_DESIGN.md)


