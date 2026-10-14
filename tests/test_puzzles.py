import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_connections import puzzles

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "puzzle_fixture.json").read_text())


def make(day: str) -> puzzles.Puzzle:
    return puzzles.parse({**FIXTURE, "print_date": day})


def test_parse_fixture():
    p = puzzles.parse(FIXTURE)
    assert p.date == "2099-01-01" and p.id == 9001
    assert len(p.groups) == 4 and all(len(ws) == 4 for _, ws in p.groups)
    assert p.groups[0] == ("FRUITS", ("APPLE", "PEAR", "PLUM", "FIG"))


def test_select_deterministic_and_seed_dependent():
    pool = [make(f"2099-01-{d:02d}") for d in range(1, 29)]
    a = puzzles.select(pool, 7, 4)
    assert a == puzzles.select(pool, 7, 4)
    assert len({p.date for p in a}) == 4
    # main / pilot / smoke seeds for the same k give different puzzles
    picks = {tuple(p.date for p in puzzles.select(pool, off + 7, 4)) for off in (0, 1000, 2000)}
    assert len(picks) == 3


def test_load_range_uses_cache_and_raises_on_fetch_failure(tmp_path, monkeypatch):
    cfg = SimpleNamespace(
        game=SimpleNamespace(date_start="2099-01-01", date_end="2099-01-03"),
        paths=SimpleNamespace(puzzles=str(tmp_path)),
    )
    (tmp_path / "2099-01-03.json").write_text(json.dumps({**FIXTURE, "print_date": "2099-01-03"}))
    monkeypatch.setattr(puzzles, "_download", lambda day: {**FIXTURE, "print_date": day})
    assert [p.date for p in puzzles.load_range(cfg)] == ["2099-01-01", "2099-01-02", "2099-01-03"]

    def fail_02(day):
        if day == "2099-01-02":
            raise OSError("404")
        return {**FIXTURE, "print_date": day}

    (tmp_path / "2099-01-02.json").unlink()
    monkeypatch.setattr(puzzles, "_download", fail_02)
    with pytest.raises(OSError):
        puzzles.load_range(cfg)
    assert not (tmp_path / "2099-01-02.json").exists()



def _raw(groups):
    return {"print_date": "2099-01-01", "id": 1,
            "categories": [{"title": f"T{i}", "cards": [{"content": w} for w in ws]}
                           for i, ws in enumerate(groups)]}


def test_parse_rejects_wrong_group_count():
    with pytest.raises(ValueError, match="4 groups of 4"):
        puzzles.parse(_raw([["a", "b", "c", "d"]] * 3))
    with pytest.raises(ValueError):
        puzzles.parse(_raw([["a", "b", "c", "d"]] * 5))


def test_parse_rejects_wrong_group_size():
    with pytest.raises(ValueError):
        puzzles.parse(_raw([["a", "b", "c"]] + [["a", "b", "c", "d"]] * 3))


def test_parse_missing_keys_raises_keyerror():
    with pytest.raises(KeyError):
        puzzles.parse({"print_date": "2099-01-01"})


def test_select_too_many_raises_and_does_not_mutate():
    pool = [make("2099-01-01"), make("2099-01-02")]
    with pytest.raises(ValueError):
        puzzles.select(pool, 1, 3)
    assert len(pool) == 2


def test_select_is_subset_and_full_size_is_permutation():
    pool = [make(f"2099-01-{d:02d}") for d in range(1, 6)]
    assert sorted(p.date for p in puzzles.select(pool, 1, 5)) == sorted(p.date for p in pool)
    assert puzzles.select(pool, 1, 0) == []


def test_fetch_caches_and_force_redownloads(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(puzzles, "_download", lambda day: calls.append(day) or {**FIXTURE, "id": len(calls)})
    assert puzzles.fetch("2099-01-01", tmp_path)["id"] == 1
    assert puzzles.fetch("2099-01-01", tmp_path)["id"] == 1
    assert puzzles.fetch("2099-01-01", tmp_path, force=True)["id"] == 2
    assert len(calls) == 2


def test_load_range_raises_on_malformed_puzzle_and_caches_nothing(tmp_path, monkeypatch):
    cfg = SimpleNamespace(game=SimpleNamespace(date_start="2099-01-01", date_end="2099-01-02"),
                          paths=SimpleNamespace(puzzles=str(tmp_path)))
    monkeypatch.setattr(puzzles, "_download",
                        lambda day: _raw([["a"] * 4] * 3) if day.endswith("01") else {**FIXTURE, "print_date": day})
    with pytest.raises(ValueError):
        puzzles.load_range(cfg)
    assert not list(tmp_path.iterdir())


def test_fetch_rejects_non_ok_status(tmp_path, monkeypatch):
    monkeypatch.setattr(puzzles, "_download", lambda day: {**FIXTURE, "status": "ERROR"})
    with pytest.raises(ValueError):
        puzzles.fetch("2099-01-01", tmp_path)
    assert not list(tmp_path.iterdir())


def test_parse_rejects_repeated_words_after_normalisation():
    words = [["a", "b", "c", "d"], ["e", "f", "g", "h"], ["i", "j", "k", "l"], ["m", "n", "o", " A "]]
    with pytest.raises(ValueError):
        puzzles.parse(_raw(words))


def test_load_range_empty_when_end_before_start(tmp_path, monkeypatch):
    cfg = SimpleNamespace(game=SimpleNamespace(date_start="2099-01-02", date_end="2099-01-01"),
                          paths=SimpleNamespace(puzzles=str(tmp_path)))
    assert puzzles.load_range(cfg) == []
