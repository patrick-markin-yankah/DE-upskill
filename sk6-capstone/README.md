# CloudHR

One Power BI model for 200 client organisations. Each signed-in user sees only their own organisation. The report is built in Power BI Desktop. Publishing stays a written plan: there is no Power BI Service account for this project.

This folder is separate from the NorthStar lab in `sk6-lab`. NorthStar keeps `localhost:5434` and the container `sk06-postgres`. CloudHR uses port `5435` and the container `cloudhr-postgres`.

## Docs

| Doc | What it is |
|---|---|
| [`SK-06_Capstone_Project.md`](SK-06_Capstone_Project.md) | Assignment brief |
| [`explanation.md`](explanation.md) | Plain-language walkthrough |
| [`technical.md`](technical.md) | Technical explanation |
| [`Plan.md`](Plan.md) | Model and report decisions |
| [`implementation.md`](implementation.md) | Stage-by-stage build, including the Desktop steps |
| [`docs/data_model.md`](docs/data_model.md) | Grain, relationships, calendar, and SQL control totals |
| [`docs/m_code.md`](docs/m_code.md) | Power Query scripts |
| [`docs/rls_administration.md`](docs/rls_administration.md) | How tenant access is granted, tested, and removed |
| [`docs/performance.md`](docs/performance.md) | Performance Analyzer timings and the before/after change |
| [`docs/deployment_guide.md`](docs/deployment_guide.md) | Workspaces, pipeline, refresh, gateway, and client 201 |

## Start the database

From `sk6-capstone`:

```powershell
docker compose up -d
docker exec cloudhr-postgres pg_isready -U postgres
python scripts\generate_cloudhr.py --out data
docker exec cloudhr-postgres psql -U postgres -d cloudhr -f /sql/01_create_and_load_cloudhr.sql
docker exec cloudhr-postgres psql -U postgres -d cloudhr -f /sql/controls.sql
```

The generator is deterministic. Leave the seed alone after the control totals are written. The load script can be run again: it drops the schemas and reloads the CSVs.

| Item | Value |
|---|---|
| Host port | `localhost:5435` |
| Database | `cloudhr` |
| User / password | `postgres` / `postgres` (local only) |

pgAdmin needs the connection parameter `gssencmode` set to `disable`. Power BI uses Import mode. If Desktop asks about encryption, connect without it. The container has no TLS certificate.

`docker compose down` stops the container and keeps the data. `docker compose down -v` deletes the database volume. The CSVs in `data/` stay either way.

## Power BI

Desktop steps are in [`implementation.md`](implementation.md). Paste the queries from [`docs/m_code.md`](docs/m_code.md).

Save a new file at each milestone rather than overwriting the only copy:

| File | Stage |
|---|---|
| `pbix/CloudHR_01_model.pbix` | Power Query |
| `pbix/CloudHR_02_measures.pbix` | Measures, checked against the SQL totals |
| `pbix/CloudHR_03_report.pbix` | Report, row-level security, and performance |
| `pbix/CloudHR.pbix` | Final copy |

The JSON files in `pbix/` are Performance Analyzer exports.

## What the data contains

200 organisations. The smallest has 50 employees and the largest has 2,000, under a cap of 50,000. Monthly snapshots run from January 2023 through September 2026. The control year is 2025, the latest full calendar year. Performance reviews stop at 2025. A few salaries are zero or negative, and a few hire dates fall after the termination date, so the model has rows to quarantine.
