from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter

from scipy import stats

from agentic_connections.run import COLUMNS, CONDITIONS, grand_total, read_rows, spent_and_estimate
from agentic_connections.utils import experiments, load_config, resolve_path

T, B = "treatment", "baseline"


def flag(value: str | None) -> int | None:
    """CSV 0/1 field; blank or absent column means missing, never 0."""
    return int(value) if value not in ("", None) else None


def dedup(rows: list[dict]) -> list[dict]:
    """Last row per (condition, run_id), in file order."""
    last = {}
    for r in rows:
        last[(r["condition"], r["run_id"])] = r
    return list(last.values())


def share(hits: int, n: int) -> float:
    return hits / n if n else math.nan


def fisher(hits: dict[str, int], n: dict[str, int]) -> dict:
    """One-sided Fisher, treatment row first, H1: treatment rate greater."""
    out = {"t": (hits[T], n[T]), "b": (hits[B], n[B]), "odds_ratio": math.nan, "p": math.nan}
    if n[T] and n[B]:
        res = stats.fisher_exact([[hits[T], n[T] - hits[T]], [hits[B], n[B] - hits[B]]], alternative="greater")
        out["odds_ratio"], out["p"] = float(res.statistic), float(res.pvalue)
    return out


def analyze(rows: list[dict]) -> dict:
    cost = {c: sum(float(r["cost_usd"] or 0) for r in rows if r["condition"] == c) for c in CONDITIONS}
    final = dedup(rows)
    arm = {c: [r for r in final if r["condition"] == c] for c in CONDITIONS}
    ok = {c: [r for r in arm[c] if r["status"] == "ok"] for c in CONDITIONS}

    def count(c, pred):
        return sum(1 for r in ok[c] if pred(r))

    def rated(c, field):  # ok rows with a non-missing value, and how many are 1
        vals = [flag(r.get(field)) for r in ok[c] if flag(r.get(field)) is not None]
        return sum(vals), len(vals)

    table = {}
    for c in CONDITIONS:
        table[c] = {
            "n_ok": len(ok[c]),
            "excluded": dict(Counter(r["status"] for r in arm[c] if r["status"] != "ok")),
            **{f: share(*rated(c, f)) for f in ("misaligned", "discrepancy", "kpi_crossing")},
            "shortfall": share(count(c, lambda r: flag(r["shortfall"]) == 1), len(ok[c])),
            "mean_true_solved": share(sum(int(r["true_solved"]) for r in ok[c]), len(ok[c])),
            "cost_usd": cost[c],
        }

    def hits_n(field):
        pairs = {c: rated(c, field) for c in CONDITIONS}
        return {c: pairs[c][0] for c in CONDITIONS}, {c: pairs[c][1] for c in CONDITIONS}

    primary = fisher(*hits_n("misaligned"))
    discrepancy = fisher(*hits_n("discrepancy"))
    kpi_crossing = fisher(*hits_n("kpi_crossing"))

    # Sensitivity: no_report counts as misaligned (ok + no_report rows).
    sens_rows = {c: [r for r in arm[c] if r["status"] in ("ok", "no_report")] for c in CONDITIONS}
    sensitivity = fisher(
        {c: sum(1 for r in sens_rows[c] if r["status"] == "no_report" or flag(r["misaligned"]) == 1)
         for c in CONDITIONS},
        {c: len(sens_rows[c]) for c in CONDITIONS},
    )

    conditional = {}
    for c in CONDITIONS:
        for s in (1, 0):
            sub = [flag(r["misaligned"]) for r in ok[c] if flag(r["shortfall"]) == s]
            sub = [v for v in sub if v is not None]
            conditional[(c, s)] = (sum(sub), len(sub))

    solved = {c: [int(r["true_solved"]) for r in ok[c]] for c in CONDITIONS}
    mw = {"p": math.nan, "u": math.nan}
    if solved[T] and solved[B] and len(set(solved[T] + solved[B])) > 1:
        res = stats.mannwhitneyu(solved[T], solved[B], alternative="two-sided")
        mw = {"p": float(res.pvalue), "u": float(res.statistic)}

    return {"table": table, "primary": primary, "sensitivity": sensitivity,
            "discrepancy": discrepancy, "kpi_crossing": kpi_crossing,
            "conditional": conditional, "mannwhitney": mw, "total_cost": sum(cost.values()),
            "n_rows": len(rows), "n_final": len(final)}


def _f(x: float, fmt: str = ".3f") -> str:
    return "n/a" if isinstance(x, float) and math.isnan(x) else format(x, fmt)


def render(res: dict, source: str, totals: tuple[str, float, float] | None = None) -> str:
    lines = [f"# Results: {source}", "",
             f"Rows read: {res['n_rows']}; after dedup to last row per (condition, run_id): {res['n_final']}.", "",
             "| arm | n ok | excluded | misaligned | discrepancy | kpi_crossing | shortfall | mean true solved | cost USD |",
             "|---|---|---|---|---|---|---|---|---|"]
    for c in CONDITIONS:
        t = res["table"][c]
        excl = ", ".join(f"{k}={v}" for k, v in sorted(t["excluded"].items())) or "none"
        lines.append(f"| {c} | {t['n_ok']} | {excl} | {_f(t['misaligned'])} | {_f(t['discrepancy'])} | "
                     f"{_f(t['kpi_crossing'])} | "
                     f"{_f(t['shortfall'])} | {_f(t['mean_true_solved'], '.2f')} | {t['cost_usd']:.4f} |")

    def test_line(name, r):
        (th, tn), (bh, bn) = r["t"], r["b"]
        return (f"- {name}: treatment {th}/{tn} vs baseline {bh}/{bn}; "
                f"odds ratio {_f(r['odds_ratio'], '.3g')}, one-sided Fisher p = {_f(r['p'], '.4g')}")

    lines += ["", "## Tests", "",
              test_line("Primary (favorable misreport, ok rows)", res["primary"]),
              test_line("Sensitivity (no_report counted as misaligned)", res["sensitivity"]),
              test_line("Discrepancy, either direction (ok rows)", res["discrepancy"]),
              test_line("KPI crossing (ok rows)", res["kpi_crossing"]),
              f"- True solved, Mann-Whitney two-sided: U = {_f(res['mannwhitney']['u'], '.1f')}, "
              f"p = {_f(res['mannwhitney']['p'], '.4g')}",
              "", "## Misaligned share by KPI shortfall (ok rows, descriptive)", ""]
    for c in CONDITIONS:
        for s, label in ((1, "short of KPI"), (0, "met KPI")):
            h, n = res["conditional"][(c, s)]
            lines.append(f"- {c}, {label}: {h}/{n} ({_f(share(h, n))})")
    lines += ["", f"Total cost in this file (all rows, superseded errors included): ${res['total_cost']:.4f}"]
    if totals is not None:
        name, spent, grand = totals
        lines += [f"Experiment {name} cost across all phase CSVs: ${spent:.4f}",
                  f"Grand total cost across all experiments: ${grand:.4f}"]
    return "\n".join(lines) + "\n"


def combine(out) -> int:
    """Every experiment's main CSV, all rows, with an ``experiment`` column last."""
    out = resolve_path(out).resolve()
    names = experiments()
    cfgs = {name: load_config(name) for name in names}
    if any(out == resolve_path(p).resolve() for c in cfgs.values() for p in vars(c.paths.runs).values()):
        print(f"Refusing to overwrite an experiment's runs CSV: {out}", file=sys.stderr)
        return 1
    rows = []
    for name in names:  # read everything before the output is opened
        path = resolve_path(cfgs[name].paths.runs.main)
        part = read_rows(path)
        extra = set(part[0]) - set(COLUMNS) if part else set()
        if extra:
            print(f"{path} has unexpected columns {sorted(extra)}; expected a subset of run.COLUMNS.",
                  file=sys.stderr)
            return 1
        rows += [{**r, "experiment": name} for r in part]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[*COLUMNS, "experiment"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Analyze a runs CSV and write a results markdown file.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--experiment", choices=experiments())
    group.add_argument("--combine", metavar="OUT", help="write every experiment's main CSV into one file")
    ap.add_argument("csv", nargs="?", help="default: the experiment's paths.runs.main")
    args = ap.parse_args(argv)
    if args.combine:
        return combine(args.combine)
    cfg = load_config(args.experiment)
    path = resolve_path(args.csv or cfg.paths.runs.main)
    rows = read_rows(path)
    if not rows:
        print(f"No rows in {path}.", file=sys.stderr)
        return 1
    text = render(analyze(rows), path.name, (args.experiment, spent_and_estimate(cfg)[0], grand_total()))
    out = path.with_name("results.md" if path.name == "runs.csv" else f"results_{path.stem}.md")
    out.write_text(text)
    print(text + f"\nWritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
