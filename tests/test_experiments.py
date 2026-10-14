import csv
import json

import pytest

from agentic_connections import analyze, run, utils
from agentic_connections.agent import TOOLS
from agentic_connections.utils import experiments, load_config, repo_root

NAMES = ["haiku55-low", "sonnet55-medium"]


def test_every_experiment_config_loads_with_prefixed_paths():
    assert experiments() == NAMES
    for name in NAMES:
        cfg = load_config(name)
        prefix = f"experiments/{name}/"
        assert cfg.paths.transcripts.startswith(prefix)
        assert all(p.startswith(prefix) for p in vars(cfg.paths.runs).values())
        assert set(vars(cfg.paths.runs)) == set(vars(cfg.paths.seed_offset))


def test_experiments_are_comparable():
    h, s = (load_config(n) for n in NAMES)
    assert vars(h.game) == vars(s.game) and vars(h.kpi) == vars(s.kpi)
    assert h.model.max_turns == s.model.max_turns
    assert h.paths.seed_offset.main == s.paths.seed_offset.main == 0
    assert (h.paths.puzzles, h.paths.materials) == (s.paths.puzzles, s.paths.materials)
    main = set(range(50))
    for phase, off in vars(s.paths.seed_offset).items():
        if phase != "main":
            assert not main & set(range(off, off + 50)), phase


def test_sonnet_settings():
    m = load_config("sonnet55-medium").model
    assert (m.id, m.effort, m.max_tokens) == ("claude-sonnet-5-5", "medium", 16000)
    assert load_config("sonnet55-medium").budget.cap_usd == 18.0


def test_tools_txt_matches_code():
    assert json.loads((repo_root() / "materials" / "tools.txt").read_text()) == TOOLS


def make_experiment(root, name, *main_costs):
    d = root / "experiments" / name
    d.mkdir(parents=True)
    p = f"experiments/{name}/artifacts"
    (d / "config.toml").write_text(
        f'[paths]\ntranscripts = "{p}/transcripts"\n'
        f'runs = {{ smoke = "{p}/runs_smoke.csv", main = "{p}/runs.csv" }}\n')
    (d / "artifacts").mkdir()
    with open(d / "artifacts" / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=run.COLUMNS)
        w.writeheader()
        for i, c in enumerate(main_costs):
            w.writerow({"condition": "baseline", "run_id": i, "status": "ok", "cost_usd": c})


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "repo_root", lambda: tmp_path)
    utils._read_config.cache_clear()
    make_experiment(tmp_path, "exp-a", 0.5, 0.25)
    make_experiment(tmp_path, "exp-b", 1.0)
    (tmp_path / "experiments" / "exp-b" / "artifacts" / "runs_smoke.csv").write_text(
        "condition,run_id,status,cost_usd\nbaseline,0,ok,0.125\n")
    yield tmp_path
    utils._read_config.cache_clear()


def test_grand_total_sums_every_experiment(tmp_root):
    assert run.grand_total() == pytest.approx(1.875)


def test_combine_concatenates_main_csvs(tmp_root):
    out = tmp_root / "dist" / "runs.csv"
    assert analyze.main(["--combine", str(out)]) == 0
    with open(out, newline="") as f:
        header = next(csv.reader(f))
        f.seek(0)
        rows = list(csv.DictReader(f))
    assert header[:7] == ["condition", "run_id", "model_id", "date", "expected", "observed", "misaligned"]
    assert header[-1] == "experiment" and header[:-1] == run.COLUMNS
    assert len(rows) == 3  # main CSVs only: 2 + 1
    assert [r["experiment"] for r in rows] == ["exp-a", "exp-a", "exp-b"]
