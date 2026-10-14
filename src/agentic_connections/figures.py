from __future__ import annotations

import argparse
import sys

from scipy import stats

from agentic_connections.analyze import dedup, flag
from agentic_connections.run import CONDITIONS, read_rows
from agentic_connections.utils import resolve_path

PAIR = ("sonnet55-medium", "haiku55-low-kpi0")
LABELS = {"sonnet55-medium": "Sonnet 5.5 (medium)", "haiku55-low-kpi0": "Haiku 5.5 (low)"}

INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
COLOR = {"baseline": "#2a78d6", "treatment": "#eb6834"}


def cp(hits: int, n: int) -> tuple[float, float]:
    """Exact two-sided 95% Clopper-Pearson interval."""
    lo = stats.beta.ppf(0.025, hits, n - hits + 1) if hits else 0.0
    hi = stats.beta.ppf(0.975, hits + 1, n - hits) if hits < n else 1.0
    return float(lo), float(hi)


def figure_data(rows: list[dict]) -> dict:
    """Per experiment in PAIR: treatment shortfall/kpi_crossing, and misaligned + CP per arm.
    Same dedup / ok-only / blank-is-missing semantics as analyze."""
    out = {}
    for name in PAIR:
        final = dedup([r for r in rows if r.get("experiment") == name])
        ok = {c: [r for r in final if r["condition"] == c and r["status"] == "ok"] for c in CONDITIONS}
        t = ok["treatment"]
        d = {"shortfall": (sum(flag(r["shortfall"]) == 1 for r in t), len(t)),
             "kpi_crossing": (sum(flag(r["kpi_crossing"]) == 1 for r in t), len(t))}
        for c in CONDITIONS:
            vals = [v for v in (flag(r.get("misaligned")) for r in ok[c]) if v is not None]
            d[c] = {"hits": sum(vals), "n": len(vals), "ci": cp(sum(vals), len(vals))}
        out[name] = d
    return out


def plot(data: dict, out_path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    sans = "Helvetica Neue" if any(f.name == "Helvetica Neue" for f in font_manager.fontManager.ttflist) \
        else "DejaVu Sans"
    plt.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": [sans],
                         "font.size": 8, "text.color": INK, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8,
                         "ytick.labelsize": 8, "axes.edgecolor": MUTED, "axes.linewidth": 0.5})
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.7, 2.0), layout="constrained", facecolor="white")
    pct = lambda x, _=None: f"{x:.0%}"
    for ax, title in ((a, "Motive vs. misreport (treatment arms)"), (b, "Favorable misreports (95% CI)")):
        ax.set_title(title, loc="left", fontsize=9, color=INK)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(length=0)
        ax.xaxis.set_major_formatter(pct)
        ax.grid(axis="x", color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)

    names = list(PAIR)
    ys = [len(names) - 1 - i for i in range(len(names))]  # first experiment on top
    for y, name in zip(ys, names):
        d = data[name]
        h, n = d["shortfall"]
        k, m = d["kpi_crossing"]
        a.barh(y + 0.15, h / n, height=0.35, color=COLOR["treatment"])
        a.text(h / n + 0.02, y + 0.15, f"{h / n:.0%} ({h}/{n})", va="center", color=INK2)
        a.plot(k / n, y - 0.25, "o", ms=5, mfc="white", mec=COLOR["treatment"], mew=1.2,
               clip_on=False)
        a.text(0.03, y - 0.25, f"claimed KPI met: {k} of {h}", va="center", color=INK2)
    a.set_xlim(0, 1)
    a.set_ylim(-0.6, len(names) - 0.4)
    a.set_yticks(ys, [LABELS[n] for n in names])

    off = {"baseline": 0.15, "treatment": -0.15}
    xmax = max(data[n][c]["ci"][1] for n in names for c in CONDITIONS)
    for y, name in zip(ys, names):
        for c in CONDITIONS:
            d = data[name][c]
            lo, hi = d["ci"]
            b.plot([lo, hi], [y + off[c]] * 2, color=COLOR[c], lw=1.75, solid_capstyle="round")
            b.plot(d["hits"] / d["n"], y + off[c], "o", ms=6, color=COLOR[c], mec="white", mew=1.5,
                   label=c.capitalize() if name == names[0] else None, clip_on=False)
            b.text(hi + xmax * 0.03, y + off[c], f"{d['hits']}/{d['n']}", va="center", color=INK2)
    b.set_xlim(0, max(0.2, xmax * 1.25))
    b.set_ylim(-0.6, len(names) - 0.4)
    b.set_yticks(ys, [LABELS[n] for n in names])
    b.legend(loc="upper right", frameon=False, fontsize=7, labelcolor=INK2, handletextpad=0.2,
             borderaxespad=0.1)
    fig.savefig(out_path, format="pdf", bbox_inches="tight", metadata={"CreationDate": None})
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Draw the results figure for the comparable experiment pair.")
    ap.add_argument("--runs", default="dist/runs.csv")
    ap.add_argument("--out", default="report/fig_results.pdf")
    args = ap.parse_args(argv)
    path = resolve_path(args.runs)
    rows = read_rows(path)
    if not rows:
        print(f"No rows in {path}.", file=sys.stderr)
        return 1
    data = figure_data(rows)
    out = resolve_path(args.out)
    plot(data, out)
    print(f"{data}\nWritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
