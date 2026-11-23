# MedInsure Healthcare Claims Data Warehouse

Analytics warehouse for MedInsure claims reporting. Separates heavy analytics from the OLTP claims system using a dimensional (star) model, SCD Type 2 history, incremental ETL, and data-quality checks.

## Documents

| File | Purpose |
|---|---|
| [`SK-02_Capstone_Project.md`](SK-02_Capstone_Project.md) | Assignment brief |
| [`PLAN.md`](PLAN.md) | Build plan and locked decisions |
| [`explanation.md`](explanation.md) | Plain-language project explanation |
| [`review.md`](review.md) | Problem/plan + plain-language walkthrough of every SQL file |
| [`sql_review.md`](sql_review.md) | Line-by-line walkthrough of every statement in `sql/00`–`sql/07` |
| [`docs/dimensional_model.md`](docs/dimensional_model.md) | Deliverable 1 — dimensional design |
| [`docs/optimization.md`](docs/optimization.md) | Deliverable 5 — performance |
| [`docs/quality_report.md`](docs/quality_report.md) | Deliverable 6 — quality results |

## Locked decisions

- Database: `medinsure`; warehouse schema: `dw`
- Full brief data volumes
- Unmatched member/provider → dead-letter + skip fact row
- Also dead-letter at load: paid &gt; allowed×1.05, service before provider network effective, orphan procedure lines
- Primary diagnosis on claim header
- SCD2 inclusive end: `effective_start <= service_date <= effective_end`

## Project layout

```text
sk2-capstone/
├── docs/
│   ├── dimensional_model.md
│   ├── optimization.md
│   └── quality_report.md
├── scripts/
│   ├── run_pipeline.ps1    # Windows PowerShell orchestrator
│   └── run_pipeline.sh     # bash orchestrator (macOS / Linux)
└── sql/
    ├── 00_schemas.sql      # dw, staging, etl
    ├── 01_oltp.sql         # source + full-volume seed
    ├── 02_dw_ddl.sql       # star DDL + NA rows
    ├── 03_etl_dims.sql     # dimension loads
    ├── 04_etl_facts.sql    # fact loads + dead letter
    ├── 05_analytics.sql    # queries 1–8
    ├── 06_tuning.sql       # EXPLAIN + MV
    └── 07_quality.sql      # DQ checks
```

## How to run

Requires local PostgreSQL (same as the FreshMart lab). See [`../sk2-lab/connection_info.md`](../sk2-lab/connection_info.md).

### Orchestrator (recommended)

From `sk2-capstone/`.

Windows (PowerShell):

```powershell
# Wipe project schemas (dw / staging / etl / public) and run sql/00 → sql/07
.\scripts\run_pipeline.ps1

# Stronger wipe: DROP + CREATE the medinsure database, then full rebuild
.\scripts\run_pipeline.ps1 -Reset

# Skip the interactive "type yes" confirmation
.\scripts\run_pipeline.ps1 -Yes
.\scripts\run_pipeline.ps1 -Reset -Yes
```

The script finds `psql` on `PATH`, or under `C:\Program Files\PostgreSQL\*\bin`. Set the password for the session before a non-interactive run: `$env:PGPASSWORD = '...'`.

macOS / Linux (bash):

```bash
# Wipe project schemas (dw / staging / etl / public) and run sql/00 → sql/07
./scripts/run_pipeline.sh

# Stronger wipe: DROP + CREATE the medinsure database, then full rebuild
./scripts/run_pipeline.sh --reset

# Skip the interactive "type yes" confirmation
./scripts/run_pipeline.sh -y
./scripts/run_pipeline.sh --reset -y
```

Optional connection overrides: `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE` (default `medinsure`), `PGPASSWORD`.

The script uses `-v ON_ERROR_STOP=1`, so a failure (for example the SCD one-current hard gate in `03`) stops the pipeline before later steps.

### Manual `psql` (same order)

```bash
psql -h localhost -p 5432 -U postgres -c "CREATE DATABASE medinsure;"   # if needed

psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/00_schemas.sql
psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/01_oltp.sql      # long (~1 min)
psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/02_dw_ddl.sql
psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/03_etl_dims.sql  # fails job if >1 is_current
psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/04_etl_facts.sql # long (~5 min)
psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/05_analytics.sql
psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/06_tuning.sql
psql -h localhost -p 5432 -U postgres -d medinsure -v ON_ERROR_STOP=1 -f sql/07_quality.sql
```

**Notes**

- Default `.\scripts\run_pipeline.ps1` (Windows) or `./scripts/run_pipeline.sh` (bash) drops `dw` / `staging` / `etl` and resets `public`, then rebuilds from `00`–`07`. Use `-Yes` / `-y` to skip the confirm prompt.
- `-Reset` / `--reset` drops the entire `medinsure` database (cleanest full wipe).
- `03_etl_dims.sql` hard-fails on SCD one-current violations and logs to `etl.scd_current_violations` / `etl.job_failures`.
- `04_etl_facts.sql` is incremental within a single load (high-water mark on `processed_date`). A full orchestrator run always reloads from an empty warehouse.
- After a fact reload outside the full pipeline, refresh the monthly MV if needed:  
  `psql -h localhost -p 5432 -U postgres -d medinsure -c "REFRESH MATERIALIZED VIEW CONCURRENTLY dw.mv_monthly_claims_summary;"`

**Useful checks**

```bash
# Dead letters from fact ETL
psql -h localhost -p 5432 -U postgres -d medinsure -c \
  "SELECT source_table, rule_violated, COUNT(*) FROM etl.dead_letter GROUP BY 1, 2 ORDER BY 1, 2;"

# Latest quality report
psql -h localhost -p 5432 -U postgres -d medinsure -c \
  "SELECT check_name, rows_evaluated, failed, pass_rate, status FROM etl.quality_report ORDER BY 1;"

# SCD / job failure logs (if the dim gate tripped)
psql -h localhost -p 5432 -U postgres -d medinsure -c \
  "SELECT * FROM etl.job_failures ORDER BY failure_id DESC LIMIT 5;"
```

## Status

| Step | Status |
|---|---|
| Scaffolding (folders, schemas, README) | Done |
| Deliverable 1 — dimensional design | Done |
| Deliverable 2 — DDL + OLTP seed | Done |
| Deliverable 3 — ETL | Done |
| Deliverable 4 — Analytics | Done |
| Deliverable 5 — Performance | Done |
| Deliverable 6 — Data quality | Done |

## Change log

| Date | Change |
|---|---|
| 2026-10-28 | Added `scripts/run_pipeline.ps1` (Windows PowerShell orchestrator; same wipe / `-Reset` / `00`–`07` flow) |
| 2026-09-02 | Added `sql_review.md` (line-by-line walkthrough of every statement in `sql/00`–`sql/07`) |
| 2026-09-02 | Added `review.md` (problem/plan + non-technical walkthrough of each SQL file) |
| 2026-09-02 | Added `scripts/run_pipeline.sh` orchestrator (create DB / `--reset` wipe / run `00`–`07`) |
| 2026-08-31 | README: full `00`–`07` run commands with `ON_ERROR_STOP`, gate/MV notes, check queries |
| 2026-08-31 | SCD one-current hard gate in dim ETL with `etl.scd_current_violations` / `etl.job_failures` |
| 2026-08-31 | Fact ETL DQ: dead-letter paid>allowed×1.05, anachronistic provider, orphan procedures |
| 2026-08-31 | Deliverable 6: seven DQ checks (99% gate); all PASS in `docs/quality_report.md` |
| 2026-08-31 | Deliverable 5: index strategy, EXPLAIN for Q1/Q6, `mv_monthly_claims_summary` |
| 2026-08-13 | Deliverable 4: eight analytical queries in `sql/05_analytics.sql` |
| 2026-08-11 | Deliverable 3: dimension ETL (SCD2/Type1) + fact ETL (HWM, dead letter, lines) |
| 2026-08-11 | Deliverable 2: `sql/01_oltp.sql` full-volume seed + `sql/02_dw_ddl.sql` star DDL/NA rows |
| 2026-08-11 | Deliverable 1: `docs/dimensional_model.md` (grains, SCD, conformed/degenerate, dry-runs) |
| 2026-08-11 | Scaffolding: layout, `00_schemas.sql`, README, stub docs/SQL |
