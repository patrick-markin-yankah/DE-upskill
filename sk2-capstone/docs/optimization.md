# Performance Optimization Report (Deliverable 5)

Database: `medinsure` · Schema: `dw`  
Related scripts: [`sql/06_tuning.sql`](../sql/06_tuning.sql), [`sql/05_analytics.sql`](../sql/05_analytics.sql)  
Plans captured: 2026-08-31 against ~1.66M `fact_claim` rows.

---

## 1. Index strategy

### 1.1 Indexes on `fact_claim`

| Index | Columns | Type | Supports |
|---|---|---|---|
| `fact_claim_pkey` | `claim_key` | B-tree unique | PK lookups; parent of line fact FK |
| `fact_claim_claim_id_key` | `claim_id` | B-tree unique | Degenerate natural key; idempotent ETL; line→header resolve |
| `idx_fact_claim_service_date` | `service_date_key` | B-tree | Queries #1, #3, #5–#8 (service-time analytics); Q6 index-only scan |
| `idx_fact_claim_processed_date` | `processed_date_key` | B-tree | Incremental ETL HWM filters / ops by process date |
| `idx_fact_claim_member` | `member_key` | B-tree | Utilization (#3), cohort (#7), OON PMPY (#5) |
| `idx_fact_claim_provider` | `provider_key` | B-tree | Provider performance (#1), denials (#4), YTD (#8) |
| `idx_fact_claim_diagnosis` | `diagnosis_key` | B-tree | Diagnosis category spend (#2) |
| `idx_fact_claim_plan` | `plan_key` | B-tree | Utilization by plan type (#3) |
| `idx_fact_claim_provider_service_paid` | `(provider_key, service_date_key) INCLUDE (total_paid)` | B-tree covering | Provider×date aggregates (#1, #8); INCLUDE avoids heap fetch for `SUM(total_paid)` when planner uses this path |

### 1.2 Indexes on `fact_claim_line`

| Index | Columns | Type | Supports |
|---|---|---|---|
| `fact_claim_line_pkey` | `claim_line_key` | B-tree unique | PK |
| `fact_claim_line_claim_line_id_key` | `claim_line_id` | B-tree unique | Idempotent line ETL |
| `idx_fact_claim_line_claim_key` | `claim_key` | B-tree | Join to header fact |
| `idx_fact_claim_line_claim_id` | `claim_id` | B-tree | Degenerate header link / DQ |
| `idx_fact_claim_line_service` | `service_date_key` | B-tree | Line-level time filters |
| `idx_fact_claim_line_member` | `member_key` | B-tree | Member-scoped line queries |
| `idx_fact_claim_line_provider` | `provider_key` | B-tree | Provider-scoped line queries |
| `idx_fact_claim_line_plan` | `plan_key` | B-tree | Plan-scoped line queries |
| `idx_fact_claim_line_procedure` | `procedure_key` | B-tree | Procedure analytics; orphan-procedure DQ |

### 1.3 Indexes deliberately **not** created

| Candidate | Why skipped |
|---|---|
| `claim_status` alone | Very low cardinality (`paid` / `denied` / `partial`). Seq scan + filter is cheaper; denials (#4) already filter after joining provider. |
| `claim_type` alone | Same low-cardinality issue (3 values). |
| `total_paid` / `total_allowed` alone | Measures, not selective predicates; would slow every ETL insert for little read benefit. |
| `(diagnosis_key, service_date_key)` composite | Query #2 aggregates all history by category; single-column FK index is enough. Extra composite adds write cost on 2M-row loads. |
| Duplicate single-column `provider_key` beyond existing | Already covered by `idx_fact_claim_provider` plus the composite covering index. |

**Trade-off rule:** every fact FK gets a B-tree (brief requirement). Extra composites only where analytics repeatedly filter/group the same column pair and INCLUDE pays off. Low-cardinality attrs are left unindexed to protect nightly load speed.

---

## 2. Execution plan analysis

### 2.1 Query #1 — Top 20 providers with YoY (`LAG`)

**Full EXPLAIN (ANALYZE, BUFFERS):**

```text
 Limit  (cost=211272.58..211272.63 rows=20 width=532) (actual time=743.856..743.887 rows=20.00 loops=1)
   Buffers: shared hit=15667 read=9619 written=277, temp read=10967 written=11002
   CTE annual_paid
     ->  Finalize GroupAggregate  (cost=123035.53..189212.82 rows=165011 width=65) (actual time=347.516..697.720 rows=52722.00 loops=1)
           Group Key: p.provider_id, p.provider_name, p.specialty, d.year
           Buffers: shared hit=15667 read=9619 written=277, temp read=10617 written=10651
           ->  Gather Merge  (cost=123035.53..181209.80 rows=396026 width=65) (actual time=347.497..650.296 rows=158155.00 loops=1)
                 Workers Planned: 2
                 Workers Launched: 2
                 Buffers: shared hit=15667 read=9619 written=277, temp read=10617 written=10651
                 ->  Partial GroupAggregate  (cost=122035.51..134498.55 rows=165011 width=65) (actual time=341.237..616.419 rows=52718.33 loops=3)
                       Group Key: p.provider_id, p.provider_name, p.specialty, d.year
                       Buffers: shared hit=15667 read=9619 written=277, temp read=10617 written=10651
                       ->  Sort  (cost=122035.51..123768.91 rows=693360 width=39) (actual time=341.214..542.584 rows=554713.33 loops=3)
                             Sort Key: p.provider_id, p.provider_name, p.specialty, d.year
                             Sort Method: external merge  Disk: 28944kB
                             Buffers: shared hit=15667 read=9619 written=277, temp read=10617 written=10651
                             Worker 0:  Sort Method: external merge  Disk: 28944kB
                             Worker 1:  Sort Method: external merge  Disk: 28056kB
                             ->  Hash Join  (cost=972.42..35808.84 rows=693360 width=39) (actual time=4.663..170.441 rows=554713.33 loops=3)
                                   Hash Cond: (f.service_date_key = d.date_key)
                                   Buffers: shared hit=15637 read=9619 written=277
                                   ->  Hash Join  (cost=843.01..33857.44 rows=693360 width=39) (actual time=4.165..112.684 rows=554713.33 loops=3)
                                         Hash Cond: (f.provider_key = p.provider_key)
                                         Buffers: shared hit=15520 read=9619 written=277
                                         ->  Parallel Seq Scan on fact_claim f  (cost=0.00..31193.92 rows=693392 width=18) (actual time=0.059..27.033 rows=554713.33 loops=3)
                                               Buffers: shared hit=14678 read=9582 written=272
                                         ->  Hash  (cost=568.01..568.01 rows=22000 width=37) (actual time=4.070..4.072 rows=22000.00 loops=3)
                                               ->  Seq Scan on dim_provider p  (cost=0.00..568.01 rows=22000 width=37) (actual time=0.024..1.790 rows=22000.00 loops=3)
                                                     Filter: (provider_key <> 0)
                                   ->  Hash  (cost=79.18..79.18 rows=4018 width=8) (actual time=0.490..0.490 rows=4018.00 loops=3)
                                         ->  Seq Scan on dim_date d  (cost=0.00..79.18 rows=4018 width=8) (actual time=0.021..0.242 rows=4018.00 loops=3)
   ... WindowAgg / LAG, top-N heapsort for LIMIT 20 ...
 Planning Time: 3.140 ms
 Execution Time: 745.807 ms
```

**Plain-English interpretation (3–5 sentences):**  
Postgres parallelizes a full pass over `fact_claim` (about 1.66M rows), hash-joins providers and dates, then sorts and aggregates paid amounts by provider and year. Because the query needs almost every claim row, a sequential scan beats an index seek. The `LAG` window then computes prior-year paid on the aggregated (~52k) provider-year rows, and a top-N sort returns the 20 largest for the latest year. Total runtime was about **746 ms**.

**Most expensive node:** the **external merge Sort** before `Partial GroupAggregate` (≈341–543 ms per worker, tens of MB spilled to disk). It orders ~555k rows per worker by provider attributes and year so the group aggregate can run. That sort—not the hash joins—dominates cost. Raising `work_mem` for reporting sessions (or pre-aggregating into a provider-year MV) would reduce disk spill.

---

### 2.2 Query #6 — Monthly volume + 3-month moving average (base tables)

**Full EXPLAIN (ANALYZE, BUFFERS) — before MV:**

```text
 WindowAgg  (cost=31501.29..31544.55 rows=132 width=52) (actual time=200.200..201.189 rows=46.00 loops=1)
   Window: w1 AS (ORDER BY d.year, d.month ROWS BETWEEN '2'::bigint PRECEDING AND CURRENT ROW)
   Buffers: shared hit=178 read=2010 written=1052
   ->  Finalize GroupAggregate  (cost=31500.96..31541.91 rows=132 width=20) (actual time=200.190..201.159 rows=46.00 loops=1)
         Group Key: d.year, d.month
         ->  Gather Merge  (cost=31500.96..31537.88 rows=317 width=16) (actual time=200.180..201.128 rows=138.00 loops=1)
               Workers Planned: 2
               Workers Launched: 2
               ->  Sort  (cost=30500.94..30501.27 rows=132 width=16) (actual time=198.243..198.245 rows=46.00 loops=3)
                     Sort Key: d.year, d.month
                     ->  Partial HashAggregate  (cost=30494.97..30496.29 rows=132 width=16) (actual time=198.223..198.228 rows=46.00 loops=3)
                           Group Key: d.year, d.month
                           ->  Hash Join  (cost=129.83..25294.53 rows=693392 width=8) (actual time=0.747..154.296 rows=554713.33 loops=3)
                                 Hash Cond: (f.service_date_key = d.date_key)
                                 ->  Parallel Index Only Scan using idx_fact_claim_service_date on fact_claim f  (cost=0.43..23343.04 rows=693392 width=4) (actual time=0.198..108.333 rows=554713.33 loops=3)
                                       Heap Fetches: 0
                                 ->  Hash  (cost=79.18..79.18 rows=4018 width=12) (actual time=0.534..0.534 rows=4018.00 loops=3)
                                       ->  Seq Scan on dim_date d  (cost=0.00..79.18 rows=4018 width=12)
 Planning Time: 0.249 ms
 Execution Time: 201.221 ms
```

**Plain-English interpretation:**  
The planner uses a **parallel index-only scan** on `idx_fact_claim_service_date` (no heap fetches), joins to `dim_date`, and hash-aggregates claim counts by year/month. A window aggregate then computes the 3-month moving average over the 46 monthly rows. Runtime was about **201 ms**—much of it reading ~1.66M date keys from the index.

**Most expensive node:** the **Parallel Index Only Scan** on `fact_claim` (~108 ms actual per worker path, feeding the hash join). Even “index only,” touching every claim’s date key for a full-history monthly rollup is the bulk of the work. That is exactly what a monthly materialized view removes from the dashboard path.

---

## 3. Materialized view — `dw.mv_monthly_claims_summary`

### 3.1 Definition

```sql
CREATE MATERIALIZED VIEW dw.mv_monthly_claims_summary AS
SELECT
    d.year,
    d.month,
    MAKE_DATE(d.year, d.month, 1) AS month_start,
    COUNT(*) AS claim_volume,
    SUM(f.total_paid) AS total_paid,
    SUM(f.total_allowed) AS total_allowed
FROM dw.fact_claim f
JOIN dw.dim_date d ON d.date_key = f.service_date_key
GROUP BY d.year, d.month;

CREATE UNIQUE INDEX uq_mv_monthly_claims_summary
    ON dw.mv_monthly_claims_summary (year, month);
```

Dashboards compute the moving average on top of the MV (46 rows) instead of re-scanning `fact_claim`.

### 3.2 EXPLAIN after MV

```text
 WindowAgg  (cost=2.75..3.77 rows=46 width=52) (actual time=0.011..0.030 rows=46.00 loops=1)
   ->  Sort  (cost=2.73..2.85 rows=46 width=20) (actual time=0.008..0.010 rows=46.00 loops=1)
         Sort Key: year, month
         ->  Seq Scan on mv_monthly_claims_summary  (cost=0.00..1.46 rows=46 width=20) (actual time=0.002..0.005 rows=46.00 loops=1)
               Buffers: shared hit=1
 Planning Time: 0.021 ms
 Execution Time: 0.038 ms
```

### 3.3 Before vs after

| Path | Execution time | What changed |
|---|---|---|
| Base tables (Q6) | **~201 ms** | Index-only scan of all claim date keys + aggregate |
| Materialized view | **~0.04 ms** | Seq scan of 46 pre-aggregated rows + window |

≈ **5,000×** faster for the dashboard-shaped read.

### 3.4 Refresh schedule recommendation

**Recommend: refresh once nightly, immediately after the fact ETL succeeds.**

Justification:

- Monthly claim volume is an ops/trend metric; hour-level freshness adds little value versus yesterday’s close.
- `REFRESH MATERIALIZED VIEW CONCURRENTLY` (enabled by the unique index) keeps the MV readable during refresh so morning dashboards are not blocked.
- Refresh cost is a one-time aggregate over `fact_claim` (~150–200 ms here)—cheap next to a full incremental load of millions of rows.
- Hourly refresh would multiply that aggregate ~24×/day for almost no decision benefit on this grain.

Operational recipe:

```sql
-- After successful load_fact_claim / load_fact_claim_line:
REFRESH MATERIALIZED VIEW CONCURRENTLY dw.mv_monthly_claims_summary;
```

---

## 4. Summary

| Lever | Outcome |
|---|---|
| FK B-tree indexes on both facts | Meet brief; enable joins and selective filters |
| Covering `(provider_key, service_date_key) INCLUDE (total_paid)` | Extra support for provider spend queries |
| Skipped low-cardinality indexes | Protect ETL write throughput |
| Q1 plan | Dominated by disk-spill sort before aggregate (~746 ms) |
| Q6 plan | Dominated by full index-only date scan (~201 ms) |
| `mv_monthly_claims_summary` | Cuts Q6-style reads to ~0.04 ms; refresh nightly after ETL |
