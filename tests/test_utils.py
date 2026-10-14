import json

from agentic_connections.utils import cached, load_config


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
    cfg = load_config("haiku55-low", force_recompute=True)
    assert cfg.game.puzzles_per_run == 4
    assert cfg.paths.runs.main == "experiments/haiku55-low/artifacts/runs.csv"
    assert cfg.paths.seed_offset.pilot == 1000
    assert cfg.paths.runs.pilot2 == "experiments/haiku55-low/artifacts/runs_pilot2.csv" and cfg.paths.seed_offset.pilot2 == 1000
    assert (cfg.game.max_mistakes, cfg.kpi.min_solved, cfg.kpi.max_total_mistakes) == (3, 4, 2)
    assert load_config("haiku55-low") is cfg


import pytest

from agentic_connections import utils

_load = lambda p: json.loads(p.read_text())
_save = lambda obj, p: p.write_text(json.dumps(obj))


def test_cached_failed_compute_leaves_no_file(tmp_path):
    node = tmp_path / "sub" / "x.json"

    def boom():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        cached(node, boom, _load, _save)
    assert not node.exists()


def test_cached_failed_force_compute_keeps_old_file(tmp_path):
    node = tmp_path / "x.json"
    cached(node, lambda: {"v": 1}, _load, _save)
    with pytest.raises(RuntimeError):
        cached(node, lambda: (_ for _ in ()).throw(RuntimeError()), _load, _save, force=True)
    assert _load(node) == {"v": 1}


def test_cached_hit_does_not_call_compute(tmp_path):
    node = tmp_path / "x.json"
    node.write_text('{"v": 9}')
    assert cached(node, lambda: pytest.fail("computed"), _load, _save) == {"v": 9}


def test_cached_falsy_result_is_cached(tmp_path):
    node = tmp_path / "x.json"
    calls = []
    for _ in range(2):
        assert cached(node, lambda: calls.append(1) or [], _load, _save) == []
    assert len(calls) == 1


def test_resolve_path_relative_vs_absolute(tmp_path):
    assert utils.resolve_path(tmp_path) == tmp_path
    assert utils.resolve_path("data/x") == utils.repo_root() / "data" / "x"


def test_namespace_nested_dicts():
    ns = utils._namespace({"a": {"b": {"c": 1}}, "d": [1]})
    assert ns.a.b.c == 1 and ns.d == [1]
