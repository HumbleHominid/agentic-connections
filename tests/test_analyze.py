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


# --- gap tests ---

def test_fisher_orientation_baseline_higher_gives_p_near_one():
    res = analyze.analyze(arm("treatment", 20, 0) + arm("baseline", 20, 10))
    assert res["primary"]["p"] > 0.99
    assert res["primary"]["odds_ratio"] == 0
    assert res["primary"]["p"] == pytest.approx(fisher_p(0, 20, 10, 10))


def test_dedup_error_then_ok_keeps_ok():
    rows = [row("baseline", 1, "error", cost=0.3), row("baseline", 1, mis=1)]
    res = analyze.analyze(rows + arm("treatment", 1, 0, start=7))
    assert res["table"]["baseline"]["n_ok"] == 1 and res["table"]["baseline"]["excluded"] == {}
    assert res["primary"]["b"] == (1, 1)


def test_dedup_ok_then_nothing_stays_ok():
    res = analyze.analyze(arm("baseline", 2, 1) + arm("treatment", 2, 0))
    assert res["n_rows"] == res["n_final"] == 4
    assert res["table"]["baseline"]["n_ok"] == 2


def test_dedup_ok_then_later_error_takes_last_row():
    # Documents semantics: last row wins, even if it is an error.
    rows = [row("baseline", 1, mis=1), row("baseline", 1, "error")]
    t = analyze.analyze(rows)["table"]["baseline"]
    assert t["n_ok"] == 0 and t["excluded"] == {"error": 1}


def test_same_run_id_in_different_arms_not_deduped():
    res = analyze.analyze([row("baseline", 1), row("treatment", 1)])
    assert res["n_final"] == 2


def test_refusal_excluded_from_primary_and_sensitivity():
    rows = arm("treatment", 4, 1) + [row("treatment", 9, "refusal")] + arm("baseline", 4, 0)
    res = analyze.analyze(rows)
    assert res["primary"]["t"] == (1, 4)
    assert res["sensitivity"]["t"] == (1, 4)


def test_csv_written_by_run_append_row_roundtrips(tmp_path):
    from connections_redteam.run import append_row, read_rows
    p = tmp_path / "runs.csv"
    rows = ([row("treatment", i, mis=int(i < 2)) for i in range(4)]
            + [row("baseline", i, mis=0) for i in range(4)]
            + [row("baseline", 9, "no_report"), row("treatment", 9, "refusal")])
    rows[0]["shortfall"] = ""  # missing value written as empty string
    for r in rows:
        append_row(p, r)
    read = read_rows(p)
    assert all(v == "" or isinstance(v, str) for r in read for v in r.values())
    res = analyze.analyze(read)
    assert res["primary"]["t"] == (2, 4) and res["primary"]["b"] == (0, 4)
    assert res["sensitivity"]["b"] == (1, 5)
    assert res["table"]["treatment"]["excluded"] == {"refusal": 1}
    assert res["conditional"][("treatment", 1)] == (1, 3)  # blank shortfall row not counted


def test_one_arm_missing_entirely_renders_na():
    res = analyze.analyze(arm("baseline", 5, 1))
    assert res["table"]["treatment"]["n_ok"] == 0
    assert math.isnan(res["primary"]["p"]) and math.isnan(res["sensitivity"]["p"])
    assert math.isnan(res["mannwhitney"]["p"])
    assert "n/a" in analyze.render(res, "x.csv")


def test_cli_naming_in_tmp_path_only(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "spent_and_estimate", lambda cfg: (0.0, 0.0))
    for name, out in (("runs.csv", "results.md"), ("smoke.csv", "results_smoke.md"),
                      ("runs_main.csv", "results_runs_main.md")):
        p = tmp_path / name
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(arm("treatment", 3, 1) + arm("baseline", 3, 0))
        assert analyze.main([str(p)]) == 0
        assert (tmp_path / out).exists()


def test_cli_total_cost_includes_superseded_error(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "spent_and_estimate", lambda cfg: (0.0, 0.0))
    p = tmp_path / "runs.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows([row("baseline", 1, "error", cost=0.5), row("baseline", 1, cost=0.25),
                     row("treatment", 1, cost=0.25)])
    analyze.main([str(p)])
    assert "Total cost in this file (all rows, superseded errors included): $1.0000" in (tmp_path / "results.md").read_text()
