# Data Quality Report (Deliverable 6)

Database: `medinsure` · Warehouse schema: `dw`  
Script: [`sql/07_quality.sql`](../sql/07_quality.sql)  
Results stored in: `etl.quality_report`  
Threshold: **PASS if pass_rate ≥ 99%**  
Run date: 2026-08-31

---

## Summary

| Checks | Passed | Failed |
|---|---|---|
| 7 | **7** | **0** |

All minimum brief checks meet the 99% gate (actual pass rate **100%** on every check).

---

## Results

| check_name | rows_evaluated | passed | failed | pass_rate | status |
|---|---:|---:|---:|---:|---|
| `fact_claim.valid_date_member_provider_keys` | 1,664,140 | 1,664,140 | 0 | 100.00 | **PASS** |
| `fact_claim.paid_vs_allowed_5pct` | 1,664,140 | 1,664,140 | 0 | 100.00 | **PASS** |
| `dim_member.one_current_per_id` | 500,000 | 500,000 | 0 | 100.00 | **PASS** |
| `dim_provider.one_current_per_id` | 15,000 | 15,000 | 0 | 100.00 | **PASS** |
| `fact_claim_line.claim_id_in_fact_claim` | 6,240,447 | 6,240,447 | 0 | 100.00 | **PASS** |
| `fact_claim_line.procedure_in_dim_procedure` | 6,240,447 | 6,240,447 | 0 | 100.00 | **PASS** |
| `fact_claim.service_before_provider_network_effective` | 1,664,140 | 1,664,140 | 0 | 100.00 | **PASS** |

---

## Check definitions

| Check | What it evaluates |
|---|---|
| `fact_claim.valid_date_member_provider_keys` | Every claim’s `service_date_key` and `processed_date_key` exist in `dim_date`; `member_key` / `provider_key` exist in their dims and are not the NA placeholder (`0`). |
| `fact_claim.paid_vs_allowed_5pct` | No claim has `total_paid > total_allowed * 1.05` (5% rounding tolerance). |
| `dim_member.one_current_per_id` | Each real `member_id` has exactly one `is_current = TRUE` row. |
| `dim_provider.one_current_per_id` | Each real `provider_id` has exactly one `is_current = TRUE` row. |
| `fact_claim_line.claim_id_in_fact_claim` | Every line’s degenerate `claim_id` exists on `fact_claim` (header RI). |
| `fact_claim_line.procedure_in_dim_procedure` | Every line resolves to a real `dim_procedure` row (not NA / missing). |
| `fact_claim.service_before_provider_network_effective` | No claim has `service_date <` the linked provider version’s `network_effective_date` (anachronistic care). |

---

## Notes

1. **ETL enforcement (load-time)** — `sql/04_etl_facts.sql` dead-letters and skips:
   - `unknown_member` / `unknown_provider` / unknown date keys
   - `paid_exceeds_allowed` (`total_paid > total_allowed * 1.05`)
   - `anachronistic_provider` (`service_date < network_effective_date`)
   - `orphan_procedure` / `missing_claim_header` on claim lines  
   SCD “one current” is hard-gated in `sql/03_etl_dims.sql` (logs to `etl.scd_current_violations` / `etl.job_failures`, then RAISE). Deliverable 6 still re-checks as a report.
2. **Dead-letter volume** — Headers that fail SCD/date/amount/network rules never enter `fact_claim`; their lines are dead-lettered as `missing_claim_header`. See `etl.dead_letter`.
3. **Anachronistic / paid / orphan counts on this seed** — Synthetic data currently produces zero of those three header/line rules after the unknown-member/provider filter; the rules still run on every load.
4. **Re-run** — `psql -d medinsure -f sql/07_quality.sql` truncates and reloads `etl.quality_report` with a fresh snapshot.

---

## How to reproduce

```bash
psql -h localhost -p 5432 -U postgres -d medinsure -f sql/07_quality.sql

psql -h localhost -p 5432 -U postgres -d medinsure -c \
  "SELECT * FROM etl.quality_report ORDER BY status DESC, pass_rate;"
```
