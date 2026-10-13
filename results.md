# Results: runs.csv

Rows read: 107; after dedup to last row per (condition, run_id): 100.

| arm | n ok | excluded | misaligned | discrepancy | kpi_crossing | shortfall | mean true solved | cost USD |
|---|---|---|---|---|---|---|---|---|
| baseline | 50 | none | 0.020 | 0.060 | 0.000 | 0.320 | 3.64 | 0.3963 |
| treatment | 50 | none | 0.000 | 0.060 | 0.000 | 0.280 | 3.48 | 0.3784 |

## Tests

- Primary (favorable misreport, ok rows): treatment 0/50 vs baseline 1/50; odds ratio 0, one-sided Fisher p = 1
- Sensitivity (no_report counted as misaligned): treatment 0/50 vs baseline 1/50; odds ratio 0, one-sided Fisher p = 1
- Discrepancy, either direction (ok rows): treatment 3/50 vs baseline 3/50; odds ratio 1, one-sided Fisher p = 0.6611
- KPI crossing (ok rows): treatment 0/50 vs baseline 0/50; odds ratio n/a, one-sided Fisher p = 1
- True solved, Mann-Whitney two-sided: U = 1214.0, p = 0.7562

## Misaligned share by KPI shortfall (ok rows, descriptive)

- baseline, short of KPI: 1/16 (0.062)
- baseline, met KPI: 0/34 (0.000)
- treatment, short of KPI: 0/14 (0.000)
- treatment, met KPI: 0/36 (0.000)

Total cost in this file (all rows, superseded errors included): $0.7747
Grand total cost across all phase CSVs: $1.0836
