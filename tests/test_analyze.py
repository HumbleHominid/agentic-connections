import csv
import math
from types import SimpleNamespace

import pytest
from scipy import stats

from connections_redteam import analyze
from connections_redteam.run import COLUMNS


def row(cond, k, status="ok", mis=0, fav=None, solved=2, short=1, cost=0.01):
    ok = status == "ok"
    return {**{c: "" for c in COLUMNS}, "condition": cond, "run_id": str(k), "status": status,
            "misaligned": str(mis) if ok else "", "favorable": str(mis if fav is None else fav) if ok else "",
            "true_solved": str(solved), "shortfall": str(short), "cost_usd": str(cost)}


def arm(cond, n, hits, start=0, **kw):
    return [row(cond, start + i, mis=int(i < hits), **kw) for i in range(n)]


def fisher_p(a, b, c, d):
    return stats.fisher_exact([[a, b], [c, d]], alternative="greater").pvalue


def test_effect_10_of_50_vs_0_of_50():
    res = analyze.analyze(arm("treatment", 50, 10) + arm("baseline", 50, 0))
    assert res["primary"]["t"] == (10, 50) and res["primary"]["b"] == (0, 50)
    assert res["primary"]["p"] == pytest.approx(fisher_p(10, 40, 0, 50))
    assert res["primary"]["p"] < 0.05
    assert res["table"]["treatment"]["misaligned"] == pytest.approx(0.2)


def test_null_2_vs_2():
    res = analyze.analyze(arm("treatment", 50, 2) + arm("baseline", 50, 2))
    assert res["primary"]["p"] == pytest.approx(fisher_p(2, 48, 2, 48))
    assert res["primary"]["p"] > 0.5


def test_primary_excludes_non_ok_and_sensitivity_counts_no_report():
    rows = (arm("treatment", 10, 1) + [row("treatment", 10 + i, "no_report") for i in range(3)]
            + [row("treatment", 20, "refusal")]
            + arm("baseline", 10, 1) + [row("baseline", 10, "no_report")])
    res = analyze.analyze(rows)
    assert res["primary"]["t"] == (1, 10) and res["primary"]["b"] == (1, 10)
    assert res["sensitivity"]["t"] == (4, 13) and res["sensitivity"]["b"] == (2, 11)
    assert res["sensitivity"]["p"] == pytest.approx(fisher_p(4, 9, 2, 9))
    assert res["table"]["treatment"]["excluded"] == {"no_report": 3, "refusal": 1}


def test_superseded_error_not_in_denominators_but_in_cost():
    rows = (arm("treatment", 5, 1) + arm("baseline", 5, 0)
            + [row("baseline", 5, "error", cost=0.5), row("baseline", 6, "error", cost=0.25)]
            + [row("baseline", 5, mis=1, cost=0.01)])  # retry of run 5 supersedes its error
    res = analyze.analyze(rows)
    t = res["table"]["baseline"]
    assert t["n_ok"] == 6 and t["excluded"] == {"error": 1}
    assert res["primary"]["b"] == (1, 6) and res["sensitivity"]["b"] == (1, 6)
    assert t["cost_usd"] == pytest.approx(5 * 0.01 + 0.5 + 0.25 + 0.01)
    assert res["total_cost"] == pytest.approx(10 * 0.01 + 0.5 + 0.25 + 0.01)
    assert res["n_rows"] == 13 and res["n_final"] == 12


def test_blank_flags_are_missing_not_zero():
    rows = arm("treatment", 4, 2) + arm("baseline", 4, 0)
    rows[0]["misaligned"] = ""  # a hit with a missing value
    rows[1]["favorable"] = ""
    res = analyze.analyze(rows)
    assert res["primary"]["t"] == (1, 3)
    assert res["favorable"]["t"] == (1, 3)


def test_favorable_and_conditional_and_mannwhitney():
    t = [row("treatment", i, mis=1, fav=int(i < 3), short=1, solved=1) for i in range(5)] + \
        [row("treatment", 5 + i, mis=0, short=0, solved=4) for i in range(5)]
    b = [row("baseline", i, mis=int(i == 0), short=int(i < 5), solved=3 + (i % 2)) for i in range(10)]
    res = analyze.analyze(t + b)
    assert res["favorable"]["t"] == (3, 10) and res["favorable"]["b"] == (1, 10)
    assert res["favorable"]["p"] == pytest.approx(fisher_p(3, 7, 1, 9))
    assert res["conditional"][("treatment", 1)] == (5, 5) and res["conditional"][("treatment", 0)] == (0, 5)
    assert res["conditional"][("baseline", 1)] == (1, 5)
    ts, bs = [1] * 5 + [4] * 5, [3 + (i % 2) for i in range(10)]
    assert res["mannwhitney"]["p"] == pytest.approx(stats.mannwhitneyu(ts, bs, alternative="two-sided").pvalue)


def test_conditional_uses_ok_rows_only():
    rows = arm("treatment", 2, 1) + [row("treatment", 9, "no_report", short=1)] + arm("baseline", 2, 0)
    assert analyze.analyze(rows)["conditional"][("treatment", 1)] == (1, 2)


def test_degenerate_inputs_do_not_crash():
    for rows in ([], arm("treatment", 3, 1), [row("baseline", 0, "no_report")],
                 arm("treatment", 3, 0, solved=2) + arm("baseline", 3, 0, solved=2)):
        res = analyze.analyze(rows)
        text = analyze.render(res, "x.csv")
        assert "# Results" in text
    res = analyze.analyze(arm("treatment", 3, 1))
    assert math.isnan(res["primary"]["p"]) and "n/a" in analyze.render(res, "x.csv")


def test_cli_writes_results(tmp_path, monkeypatch, capsys):
    path = tmp_path / "runs.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(arm("treatment", 10, 3) + arm("baseline", 10, 0))
    monkeypatch.setattr(analyze, "spent_and_estimate", lambda cfg: (1.23, 0.0))
    assert analyze.main([str(path)]) == 0
    text = (tmp_path / "results.md").read_text()
    assert "Primary" in text and "Grand total cost across all phase CSVs: $1.2300" in text
    assert "Primary" in capsys.readouterr().out
    pilot = tmp_path / "runs_pilot.csv"
    pilot.write_text(path.read_text())
    assert analyze.main([str(pilot)]) == 0 and (tmp_path / "results_runs_pilot.md").exists()


def test_cli_empty_file(tmp_path):
    assert analyze.main([str(tmp_path / "missing.csv")]) == 1
