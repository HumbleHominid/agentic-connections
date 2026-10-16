# Agentic Connections

An LLM agent plays NYT Connections under a clean instruction, then reports its results. Treatment adds a KPI to the company handbook the agent reads; we measure favorable misreporting against the game's ground truth. See `report.pdf` for design and results.

## Setup

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                      # add --dev for pytest and matplotlib
cp .env.example .env         # then set ANTHROPIC_KEY
```

## Run

Experiments: `haiku55-low`, `haiku55-low-kpi0`, `sonnet55-medium` (config in `experiments/<name>/config.toml`).

```sh
# n paired baseline/treatment runs; phases: smoke, pilot, pilot2, main
uv run --env-file .env python -m agentic_connections.run --experiment sonnet55-medium --phase main --n 50
```

- Output: `experiments/<name>/artifacts/runs_<phase>.csv` (`runs.csv` for `main`). Re-running resumes, skipping completed runs.
- Spend is capped per experiment (`[budget]` in the config); the run stops when the cap would be exceeded.
- Puzzles are fetched from the NYT API on first use and cached in `data/puzzles/` (not shipped, per NYT ToS). The date range is fixed in the config, so the pool is identical on re-fetch.

## Analyze

```sh
uv run python -m agentic_connections.analyze --experiment sonnet55-medium   # writes artifacts/results.md
uv run python -m agentic_connections.analyze --combine dist/runs.csv        # all experiments, one CSV
uv run python -m agentic_connections.analyze --compare sonnet55-medium haiku55-low-kpi0
uv run python -m agentic_connections.figures                                # report/fig_results.pdf
```

## Test

```sh
uv run pytest        # offline; uses a fake client
```

## Layout

- `src/agentic_connections/`: `game.py` (ground truth), `agent.py` (tool loop), `run.py`, `analyze.py`, `figures.py`
- `materials/`: system prompt, user instruction, handbooks, tools, nudge
- `experiments/`: config, hypothesis, and result CSVs per experiment
- `runs.csv`: all runs, combined
