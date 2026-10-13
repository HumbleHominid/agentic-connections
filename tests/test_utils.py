import json

from connections_redteam.utils import cached, load_config


def test_cached_computes_once_then_loads_and_force_recomputes(tmp_path):
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}

    load = lambda p: json.loads(p.read_text())
    save = lambda obj, p: p.write_text(json.dumps(obj))
    node = tmp_path / "sub" / "x.json"

    assert cached(node, compute, load, save) == {"n": 1}
    assert cached(node, compute, load, save) == {"n": 1}
    assert len(calls) == 1
    assert cached(node, compute, load, save, force=True) == {"n": 2}
    assert json.loads(node.read_text()) == {"n": 2}


def test_load_config_attribute_access():
    cfg = load_config(force_recompute=True)
    assert cfg.game.puzzles_per_run == 4
    assert cfg.paths.runs.main == "runs.csv"
    assert cfg.paths.seed_offset.pilot == 1000
    assert load_config() is cfg
