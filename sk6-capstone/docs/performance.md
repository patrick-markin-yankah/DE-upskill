# CloudHR performance timings

Recorded from Performance Analyzer exports. Direct query is 0 ms on every visual. This model is Import.

DAX query is the Query duration in the export. Other is the visual's total time minus that query. Cards titled "Card" are named below by the measure they evaluate.

Targets: every visual under 800 ms of DAX query time, and at least 80% under 400 ms.

30 visuals across the four pages. After `snapshot_month` was removed from `fact_employee_monthly`, every DAX query is under 800 ms. 27 of 30 (90%) are under 400 ms. Tenure vs Salary was 831 ms before that change and 782 ms after. DAX Studio Server Timings for the query before the change: formula engine 1,176 ms, storage engine 47 ms, 5 storage-engine queries.

## Executive Workforce Summary

Export: `pbix/ExecutiveWorkforceSummary.json`, refresh at 2026-10-21 13:17:57 UTC. Year filter is 2025.

| Visual | DAX query (ms) | Direct query (ms) | Other (ms) |
|---|---:|---:|---:|
| Year | 315 | 0 | 184 |
| Quarter | 321 | 0 | 216 |
| department_group | 317 | 0 | 235 |
| employment_type | 295 | 0 | 199 |
| Card — Active Headcount | 299 | 0 | 230 |
| Card — Turnover Rate | 338 | 0 | 219 |
| Card — Avg Tenure (Years) | 467 | 0 | 1,085 |
| Card — Avg Base Salary | 326 | 0 | 230 |
| Headcount Trend | 314 | 0 | 147 |
| Headcount by Department Group | 335 | 0 | 123 |
| Hires and Terminations | 600 | 0 | 302 |

11 visuals. All 11 DAX queries are under 800 ms. 9 of 11 are under 400 ms. The two above 400 ms are Hires and Terminations (600 ms) and Avg Tenure (Years) (467 ms).

## Workforce Composition

Export: `pbix/WorkforceComposition.json`, refresh at 2026-10-21 13:25:41 UTC. The recorded queries have no year filter.

| Visual | DAX query (ms) | Direct query (ms) | Other (ms) |
|---|---:|---:|---:|
| Year | 135 | 0 | 83 |
| job_level | 139 | 0 | 102 |
| employment_type | 129 | 0 | 75 |
| Headcount by job level | 147 | 0 | 36 |
| Headcount by employment type | 145 | 0 | 35 |
| Avg Tenure by Department | 272 | 0 | 21 |
| Largest Departments | 182 | 0 | 343 |

7 visuals. Every DAX query is under 400 ms.

## Compensation Analytics

Export: `pbix/CompensationAnalytics.json`, refresh at 2026-10-21 13:26:38 UTC. Tenure vs Salary is filtered to September 2026. The other queries on this page have no year filter.

| Visual | DAX query (ms) | Direct query (ms) | Other (ms) |
|---|---:|---:|---:|
| department_name | 286 | 0 | 88 |
| job_level | 288 | 0 | 107 |
| employment_type | 276 | 0 | 59 |
| Avg Salary by job level | 292 | 0 | 38 |
| Salary Distribution | 293 | 0 | 36 |
| Compensation Band Width By Department | 353 | 0 | 66 |
| Tenure vs Salary | 782 | 0 | 247 |

7 visuals. Tenure vs Salary is the only DAX query on this page over 400 ms. The first recording was 831 ms of DAX query time and 115 ms Other. After `snapshot_month` was removed from `fact_employee_monthly`, the same visual is 782 ms and 247 ms. Direct query stayed 0 ms.

DAX Studio Server Timings for the Tenure vs Salary query:

| Formula engine | Storage engine | Storage-engine queries |
|---:|---:|---:|
| 1,176 ms | 47 ms | 5 |

## Leave & Attendance

Export: `pbix/Leave&Attendance.json`, refresh at 2026-10-21 13:27:14 UTC. Year filter is 2025.

| Visual | DAX query (ms) | Direct query (ms) | Other (ms) |
|---|---:|---:|---:|
| Year | 109 | 0 | 61 |
| Utilization by leave type | 172 | 0 | 36 |
| Monthly Leave  Days Trend | 131 | 0 | 26 |
| Departmental Leave Trend | 175 | 0 | 34 |
| Leave Type Breakdown | 128 | 0 | 26 |

5 visuals. Every DAX query is under 400 ms.
