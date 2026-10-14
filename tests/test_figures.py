import csv
import subprocess
import sys

import pytest
from scipy import stats

from agentic_connections import figures
from agentic_connections.run import COLUMNS, read_rows
from agentic_connections.utils import resolve_path

S, H = figures.PAIR


def row(exp, cond, k, status="ok", mis=0, kpi=0, short=0):
    ok = status == "ok"
    return {**{c: "" for c in COLUMNS}, "experiment": exp, "condition": cond, "run_id": str(k),
            "status": status, "misaligned": str(mis) if ok else "", "kpi_crossing": str(kpi) if ok else "",
            "shortfall": str(short)}


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[*COLUMNS, "experiment"])
        w.writeheader()
        w.writerows(rows)
    return read_rows(path)


def test_figure_data_dedup_counts_and_cp(tmp_path):
    rows = ([row(S, "treatment", i, mis=int(i < 2), kpi=int(i == 0), short=int(i < 3)) for i in range(10)]
            + [row(S, "baseline", i) for i in range(10)]
            + [row(S, "baseline", 10, "error"), row(S, "baseline", 10, mis=1)]  # retry supersedes error
            + [row(S, "baseline", 11, "error")]
            + [row(H, c, i, mis=1) for c in ("baseline", "treatment") for i in range(5)]
            + [row("other", "treatment", i, mis=1) for i in range(5)])
    d = figures.figure_data(write_csv(tmp_path / "runs.csv", rows))
    assert set(d) == {S, H}
    assert d[S]["shortfall"] == (3, 10) and d[S]["kpi_crossing"] == (1, 10)
    assert (d[S]["baseline"]["hits"], d[S]["baseline"]["n"]) == (1, 11)
    assert (d[S]["treatment"]["hits"], d[S]["treatment"]["n"]) == (2, 10)
    assert d[S]["treatment"]["ci"] == pytest.approx(
        (stats.beta.ppf(0.025, 2, 9), stats.beta.ppf(0.975, 3, 8)))
    assert d[S]["baseline"]["ci"][0] == pytest.approx(stats.beta.ppf(0.025, 1, 11))
    assert figures.cp(0, 50)[0] == 0 and figures.cp(5, 5)[1] == 1
    assert d[H]["treatment"]["hits"] == 5 and d[H]["treatment"]["ci"][1] == 1


@pytest.mark.skipif(not resolve_path("dist/runs.csv").exists(), reason="no dist/runs.csv")
def test_figure_data_real_csv():
    d = figures.figure_data(read_rows(resolve_path("dist/runs.csv")))
    assert d[S]["shortfall"] == (16, 50) and d[S]["kpi_crossing"] == (0, 50)
    assert d[H]["shortfall"] == (36, 50) and d[H]["kpi_crossing"] == (0, 50)
    assert [(d[e][c]["hits"], d[e][c]["n"]) for e in (S, H) for c in ("baseline", "treatment")] == \
        [(0, 50), (0, 50), (2, 50), (2, 50)]
    assert d[S]["baseline"]["ci"] == pytest.approx((0, 0.0711), abs=1e-4)
    assert d[H]["baseline"]["ci"] == pytest.approx((0.0049, 0.1371), abs=1e-4)


def test_plot_writes_pdf(tmp_path):
    d = {e: {"shortfall": (3, 10), "kpi_crossing": (0, 10),
             **{c: {"hits": 1, "n": 10, "ci": figures.cp(1, 10)} for c in ("baseline", "treatment")}}
         for e in (S, H)}
    out = tmp_path / "fig.pdf"
    figures.plot(d, out)
    assert out.read_bytes().startswith(b"%PDF")


def test_no_matplotlib_on_import():
    code = "import sys, agentic_connections.run, agentic_connections.figures; " \
           "assert 'matplotlib' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def _full(extra=()):
    return [row(e, c, i) for e in (S, H) for c in ("baseline", "treatment") for i in range(3)] + list(extra)


@pytest.mark.parametrize("k,n", [(0, 50), (50, 50), (7, 50), (1, 1)])
def test_cp_matches_scipy(k, n):
    lo, hi = figures.cp(k, n)
    assert lo == (0.0 if k == 0 else pytest.approx(stats.beta.ppf(0.025, k, n - k + 1)))
    assert hi == (1.0 if k == n else pytest.approx(stats.beta.ppf(0.975, k + 1, n - k)))


def test_other_experiment_rows_ignored(tmp_path):
    rows = _full([row("haiku55-low", "treatment", i, mis=1, kpi=1, short=1) for i in range(5)])
    d = figures.figure_data(write_csv(tmp_path / "r.csv", rows))
    assert set(d) == {S, H}
    assert d[H]["treatment"]["n"] == 3 and d[H]["treatment"]["hits"] == 0


def test_last_row_error_after_ok_excludes_run(tmp_path):
    rows = _full([row(S, "baseline", 0, mis=1), row(S, "baseline", 0, "error")])
    d = figures.figure_data(write_csv(tmp_path / "r.csv", rows))
    assert (d[S]["baseline"]["hits"], d[S]["baseline"]["n"]) == (0, 2)


def test_blank_misaligned_on_non_ok_not_counted(tmp_path):
    rows = _full([row(S, "treatment", 9, "error")])
    d = figures.figure_data(write_csv(tmp_path / "r.csv", rows))
    assert d[S]["treatment"]["n"] == 3 and d[S]["shortfall"][1] == 3


def test_blank_misaligned_on_ok_row_is_missing_not_zero(tmp_path):
    r = row(S, "baseline", 9)
    r["misaligned"] = ""
    d = figures.figure_data(write_csv(tmp_path / "r.csv", _full([r])))
    assert d[S]["baseline"]["n"] == 3


def test_denominators_and_kpi_crossing_treatment_only(tmp_path):
    rows = ([row(S, "treatment", i, short=int(i < 2), kpi=int(i == 0)) for i in range(4)]
            + [row(S, "baseline", i, short=1, kpi=1) for i in range(6)]
            + [row(H, c, i) for c in ("baseline", "treatment") for i in range(2)])
    d = figures.figure_data(write_csv(tmp_path / "r.csv", rows))
    assert d[S]["shortfall"] == (2, 4) and d[S]["kpi_crossing"] == (1, 4)


@pytest.mark.parametrize("drop", [lambda r: r["experiment"] != H,
                                  lambda r: not (r["experiment"] == S and r["condition"] == "treatment")])
def test_missing_experiment_or_arm_fails_clearly(tmp_path, drop):
    rows = [r for r in _full() if drop(r)]
    with pytest.raises(ValueError, match="no ok rows"):
        figures.figure_data(write_csv(tmp_path / "r.csv", rows))
    assert figures.main(["--runs", str(tmp_path / "r.csv"), "--out", str(tmp_path / "o.pdf")]) == 1


def test_main_custom_paths(tmp_path):
    runs, out = tmp_path / "r.csv", tmp_path / "new" / "o.pdf"
    write_csv(runs, _full())
    assert figures.main(["--runs", str(runs), "--out", str(out)]) == 0
    assert out.read_bytes().startswith(b"%PDF")


def test_main_empty_csv_returns_1(tmp_path):
    runs = tmp_path / "r.csv"
    write_csv(runs, [])
    assert figures.main(["--runs", str(runs), "--out", str(tmp_path / "o.pdf")]) == 1


def test_main_default_paths_under_repo_root(monkeypatch):
    seen = {}
    monkeypatch.setattr(figures, "read_rows", lambda p: seen.setdefault("runs", p) and _full())
    monkeypatch.setattr(figures, "plot", lambda d, out: seen.setdefault("out", out))
    assert figures.main([]) == 0
    root = resolve_path(".")
    assert seen["runs"] == root / "dist/runs.csv" and seen["out"] == root / "report/fig_results.pdf"


def test_plot_is_deterministic(tmp_path):
    d = figures.figure_data(write_csv(tmp_path / "r.csv", _full()))
    figures.plot(d, tmp_path / "a.pdf")
    figures.plot(d, tmp_path / "b.pdf")
    assert (tmp_path / "a.pdf").read_bytes() == (tmp_path / "b.pdf").read_bytes()
