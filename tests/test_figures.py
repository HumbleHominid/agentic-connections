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
