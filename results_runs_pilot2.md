# Results: runs_pilot2.csv

Rows read: 20; after dedup to last row per (condition, run_id): 20.

| arm | n ok | excluded | misaligned | favorable | shortfall | mean true solved | cost USD |
|---|---|---|---|---|---|---|---|
| baseline | 10 | none | 0.300 | 0.100 | 0.500 | 3.70 | 0.0718 |
| treatment | 10 | none | 0.200 | 0.200 | 0.400 | 3.90 | 0.0755 |

## Tests

- Primary (misaligned, ok rows): treatment 2/10 vs baseline 3/10; odds ratio 0.583, one-sided Fisher p = 0.8483
- Sensitivity (no_report counted as misaligned): treatment 2/10 vs baseline 3/10; odds ratio 0.583, one-sided Fisher p = 0.8483
- Favorable direction (ok rows): treatment 2/10 vs baseline 1/10; odds ratio 2.25, one-sided Fisher p = 0.5
- True solved, Mann-Whitney two-sided: U = 60.0, p = 0.3006

## Misaligned share by KPI shortfall (ok rows, descriptive)

- baseline, short of KPI: 1/5 (0.200)
- baseline, met KPI: 2/5 (0.400)
- treatment, short of KPI: 2/4 (0.500)
- treatment, met KPI: 0/6 (0.000)

Total cost in this file (all rows, superseded errors included): $0.1473
Grand total cost across all phase CSVs: $0.3089
