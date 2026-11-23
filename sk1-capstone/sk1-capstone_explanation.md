# GlobalTech HR Integration Pipeline — Plain-Language Explanation

This document walks through the **implemented** SK-01 capstone: a local Python pipeline that turns four messy HR extracts into one golden employee dataset. It explains what each stage does, why it exists, and what actually happens on the current files. You do not need a deep technical background to follow it. Technical terms appear in **bold** the first time they are used; they are also listed in the [Key terms](#key-terms) section.

Related files:

- [`README.md`](README.md) — how to run the pipeline, outputs, and known limitations
- [`docs/architecture.md`](docs/architecture.md) — module boundaries, sequence, and design decisions
- [`docs/schema.md`](docs/schema.md) — generated column-level contract for the golden dataset

---

## 1. What is this project about?

**GlobalTech** acquired **AcquiredCo**. On day one, HR, payroll, and finance still live in four different extracts:

| Source | What it is | Native shape |
|---|---|---|
| GlobalTech HRIS | Workday-style employee list | Flat CSV, numeric IDs (`1`, `2`, …) |
| AcquiredCo HRIS | BambooHR-style employee list | Nested JSON (`ACQ_00001`, nested `name` / `contact` / `assignment`) |
| Combined payroll | ADP-style pay records for both companies | Excel, mixed currencies and pay frequencies |
| Benefits | MedShield enrollments (mostly GlobalTech) | XML, one row per plan, not per person |

Those systems disagree on almost everything that matters for a single employee spine:

- IDs look like `14571` in one file and `ACQ_00137` in another.
- Employment type is `Full-Time` in GlobalTech and `PT` / `CONTRACTOR` in AcquiredCo.
- Salary may be monthly EUR in one row and bi-weekly GBP in the next.
- Benefits are plan-grain (several rows per person), while HRIS is person-grain.
- The same human can appear in both companies after the acquisition, with different IDs.

**The solution we built:** a six-stage batch pipeline that loads the four files, forces them onto one schema, cleans values, matches people conservatively, quality-checks the result, draws an EDA dashboard, and publishes a partitioned Parquet “golden” dataset. Fuzzy lookalikes are **not** auto-merged; they go to HR as a review CSV.

On the current extracts the published golden set is **18,001 employees** (15,000 GlobalTech + 3,001 AcquiredCo).

---

## 2. The big picture (how the pieces fit)

Everything runs in one Python process. Stages pass **pandas DataFrames** in memory. Files are the only durable boundary: raw inputs on the left, reports and golden Parquet on the right. There is no database and no live API.

```text
  Four raw extracts                         Published artifacts
  CSV / JSON / Excel / XML                  Parquet + CSVs + PNG + docs
           │                                          ▲
           │         in-memory pandas stages          │
           └────────────── pipeline.py ───────────────┘
                            │
     ingest → clean → dedup → validate → visualize → export
                            │
                    quality gate (≤2 FAILs)
                    can stop the last two stages
```

In the order the code actually runs:

1. **Ingest** four native formats and align each to one standard column list.
2. **Clean** names, IDs, employment types, departments, dates, and salaries.
3. **Deduplicate** using HRIS as the person spine; enrich from payroll/benefits; flag ghosts and fuzzy pairs.
4. **Validate** 15 quality checks and halt if more than two checks FAIL.
5. **Visualize** a six-chart 300 DPI EDA PNG (only if the gate passed).
6. **Export** golden Parquet partitioned by company, plus schema docs and review CSVs.

Orchestration lives in `hr_pipeline/pipeline.py`. Shared knobs live in `hr_pipeline/config.py`. Almost all disk writes go through `hr_pipeline/export.py`.

---

## 3. Key terms

### Everyday business terms

| Term | Meaning |
|---|---|
| **HRIS** | Human Resources Information System — the system of record for “who is an employee” |
| **Employee spine** | The list of people we treat as real employees. In this project that list comes from HRIS, not payroll |
| **Golden dataset** | The published, cleaned, one-row-per-person file that downstream HR analytics should use |
| **Ghost employee** | A payroll ID that has no matching HRIS person. Someone is being paid, but they are not on the HR roster |
| **Probable match** | Two records that look like the same person (similar name, close hire dates) but were **not** auto-merged |
| **Company origin** | Whether the surviving row is treated as GlobalTech or AcquiredCo |
| **Employment type** | After cleaning: Full-Time, Part-Time, or Contractor |
| **Pay frequency** | How often the source salary is quoted: Annual, Monthly, or Bi-Weekly |
| **Annualized USD salary** | Source pay converted to a 12-month USD figure so people can be compared |

### Data / pipeline terms

| Term | Meaning in this project |
|---|---|
| **Grain** | What one row means. HRIS grain = one employee. Benefits grain = one enrollment. Payroll can have several rows per person over time |
| **Schema alignment** | Renaming native columns onto one shared list (`employee_id`, `first_name`, …) and filling missing fields with empty values |
| **Provenance** | Trace of where a golden row came from (`source_system`, `source_systems`, `employee_id_raw`) |
| **Namespace** | Prefixing IDs so GlobalTech `42` and AcquiredCo `42` do not collide: `GT-000042` vs `AC-000042` |
| **Dead letter** | A side CSV of records we refused to ingest (malformed row, missing ID, unreadable file) so the rest of the load can continue |
| **Idempotent-ish re-run** | Same inputs and config produce the same golden data. Dead-letter files **append**; golden Parquet is **replaced** |
| **Quality check** | One rule scored as a pass rate over rows (e.g. “95% of emails are unique”) |
| **Quality gate** | Pipeline stop rule: more than two failed checks → do not publish EDA or golden data |
| **Fuzzy match** | Approximate name comparison using RapidFuzz `token_sort_ratio` (word-order-insensitive similarity 0–100) |
| **Blocking** | Only compare people whose hire dates are within ±30 days, so we do not score every name against every other name |
| **Partitioned Parquet** | A folder of compressed columnar files split by `company_origin=GlobalTech` / `AcquiredCo` |
| **SCD / warehouse** | Not used here. This is a day-1 integration pipeline, not a dimensional warehouse |

---

## 4. Configuration: the rulebook (`config.py`)

Before any file is read, `config.py` defines the contract every later stage uses. Putting rules in one place means cleaning, matching, validation, and export cannot drift apart.

Important settings and why they exist:

| Setting | Value | Why |
|---|---|---|
| Standard schema | 26 shared columns | Every source, even payroll and benefits, is forced onto the same column list |
| FX rates | USD=1.00, EUR=1.09, GBP=1.27 | Fixed project rates so salary conversion is deterministic, not market-live |
| Pay multipliers | Annual×1, Monthly×12, Bi-Weekly×26 | Turns a period amount into an annual figure |
| Employment map | `FT` / `FULL-TIME` / `PT` / `CONTRACTOR` → three labels | AcquiredCo codes and GlobalTech words become one taxonomy |
| Department map | 18 English names plus `ENG-01` / `MKT-03` | Current files already use names; code aliases are ready if coded extracts appear |
| Source priority | HRIS=1, payroll=2, benefits=3 | When collapsing duplicates, HRIS identity wins |
| AcquiredCo page size | 100 | Simulates paging through an API even though the source is a local JSON file |
| Fuzzy threshold | 88 | Name similarity must be at least 88/100 to become an HR review pair |
| Fuzzy hire-date window | 30 days | Candidates must have hire dates that close together |
| Quality threshold | 95% | A check PASSes only if ≥95% of evaluated rows pass |
| Max failed checks | 2 | The gate still publishes if (for example) unique-email and salary-range FAIL |
| ID regex | `^(GT\|AC)-\d{6}$` | Canonical IDs after namespacing |
| Salary band | $15,000 – $2,000,000 | Flags extreme annualized values; does not rewrite them |
| Hire-date floor | 1970-01-01 | Dates before this (or after today) are flagged invalid |

The same module creates `data/processed/`, `data/processed/dead_letter/`, and `logs/`, and attaches a logger that writes both to the console and to `logs/pipeline.log`.

---

## 5. Stage 1 — Ingest (`ingest.py`)

**What it is:** Read four different file formats and emit four DataFrames that already use the standard column names.

**Why it is separate from cleaning:** Loading and renaming is a different job from fixing values. If payroll Excel cannot be opened, we still want GlobalTech CSV to load. If one JSON employee is missing an ID, we skip that record instead of crashing the whole job.

Each loader follows the same pattern:

1. Open the file (or dead-letter a file-level failure and return an empty standard frame).
2. Reject rows that lack a usable identity.
3. Call `align_schema()` so every output has the same 26 columns plus `source_system`.
4. Fields a source does not have (payroll has no `first_name`; HRIS has no `currency`) become empty (`pd.NA`).

### 5.1 Schema alignment

`SOURCE_COLUMN_MAPPINGS` is the translation dictionary. Examples:

- AcquiredCo `employee_identifier` → `employee_id`
- AcquiredCo `assignment_hire_timestamp` → `hire_date` (after JSON flattening)
- Payroll `source` → `company_origin`
- Payroll `effective_date` → `payroll_effective_date`
- Benefits `plan_type` → `benefit_plans`

Company origin is stamped by source for HRIS and benefits. Payroll keeps the `source` column from Excel (`GlobalTech` or `AcquiredCo`). Benefits rows are also tagged `benefits_enrolled=True` and `benefit_plan_count=1` at ingest, because each XML enrollment is already a real plan.

Frames are **kept separate**. Concatenating them this early would mix person-grain HRIS with plan-grain benefits and make later matching harder.

### 5.2 GlobalTech CSV

- UTF-8 CSV with Python engine so a broken line can be captured instead of aborting.
- `employee_id` and `manager_id` are read as text so `00042` would not become the number `42`.
- Malformed lines go to `globaltech_hris_dead_letters.csv`.
- Rows with a blank employee ID are dead-lettered and dropped.

Current file: **15,000** rows, 15,000 distinct numeric IDs, hire dates already `YYYY-MM-DD`, employment types already in English (`Full-Time` / `Part-Time` / `Contractor`).

### 5.3 AcquiredCo JSON (simulated pagination)

The file is a single payload (`status`, `timestamp`, `total_records`, `employees`), but the loader pretends it is an API:

- Read the whole JSON.
- Walk `employees` in pages of 100 and log each page.
- Drop records that are not objects or that lack `employee_identifier`.
- Flatten nested keys with `pd.json_normalize(..., sep="_")` so `name.first` becomes `name_first`, which the mapping then renames to `first_name`.
- Warn if `total_records` disagrees with the array length.

Current file: **3,200** employee objects. **200** of them use synthetic IDs like `ACQ_DUP_00000`. Those are still ingested; collapsing them is a later (dedup) concern, because ingest should not decide which duplicate “wins.”

### 5.4 Payroll Excel

- `openpyxl` reads `.xlsx`.
- Required columns: employee ID, company source, salary, currency, frequency, bonus, effective date.
- Unknown `source` values (not `GlobalTech` / `AcquiredCo`) are dead-lettered.
- GlobalTech payroll IDs are bare numbers (`14571`). AcquiredCo payroll IDs still have the `ACQ_` prefix (`ACQ_00137`). Namespacing in the next stage is what makes those joinable to HRIS.

Current file: **19,000** rows, **11,155** distinct raw IDs, currencies split across USD / EUR / GBP, frequencies split across Annual / Monthly / Bi-Weekly. Several rows can exist for the same person with different `effective_date`s.

### 5.5 Benefits XML

- Parse with the standard library XML parser.
- Each `<enrollment>` child tag becomes a field.
- Missing `employee_id` or `plan_type` → dead letter.
- Current file: **12,000** enrollments for **8,283** distinct employee IDs (plan grain, mostly GlobalTech numeric IDs).

### 5.6 Dead letters

Rejected records are **appended** to `data/processed/dead_letter/<source>_dead_letters.csv` with UTC timestamp, source name, reason, and the raw record as JSON. The pipeline continues. An existing `payroll_dead_letters.csv` in the repo is a leftover from an early run that lacked `openpyxl`; later successful runs still append rather than wipe that history.

---

## 6. Stage 2 — Clean (`clean.py`)

**What it is:** Source-independent normalization. After this stage, IDs, names, taxonomies, dates, and salaries are comparable across files.

**Why we keep raw copies:** Downstream reviewers (and the quality report) need to see what the source actually said. Cleaning therefore adds `employee_id_raw`, `manager_id_raw`, `department_original`, and `*_invalid` flags instead of silently overwriting history.

`clean_dataframe()` always runs in this order: names → IDs → employment types → salary → departments → dates.

### 6.1 Names

Unicode **NFKC** normalization plus collapsed whitespace, then title case. That keeps `José`, turns `anne-mARIE` into `Anne-Marie`, and `o'BRIEN` into `O'Brien`. Missing names stay missing.

### 6.2 ID namespacing (the join key for the whole project)

Native IDs overlap. Cleaning extracts the **digits**, zero-pads to six, and prefixes from `company_origin`:

| Raw ID | Company | Canonical ID |
|---|---|---|
| `42` | GlobalTech | `GT-000042` |
| `14571` | GlobalTech | `GT-014571` |
| `ACQ_00007` | AcquiredCo | `AC-000007` |
| `ACQ_DUP_00000` | AcquiredCo | `AC-000000` |

Manager IDs get the same treatment, using the **employee’s** company (managers are assumed in-company). IDs that cannot be parsed (no digits, number bigger than 999,999, missing company) stay empty and are logged.

This is why payroll can later match HRIS: GlobalTech payroll `14571` and HRIS `14571` both become `GT-014571`. AcquiredCo payroll `ACQ_00137` and HRIS `ACQ_00137` both become `AC-000137`. The `DUP` IDs collide with the canonical numeric IDs on purpose; Pass 1 will keep the non-`DUP` row.

### 6.3 Employment types

Uppercased source values are mapped through `EMPLOYMENT_TYPE_MAP`. Unknown values (e.g. `temporary`) become empty and are logged, not invented.

### 6.4 Salary → annual USD

1. Strip currency symbols and commas from `base_salary` (`$85,000` → `85000`). Accounting-style negatives in parentheses are supported.
2. Look up FX and frequency multipliers.
3. `salary_usd_annual = amount × FX × frequency`, rounded to 2 decimals.
4. Keep `base_salary`, `currency`, and `pay_frequency` as they were (currency/frequency casing is normalized).

Example from the tests: `$10,000` monthly USD → `$120,000` annual; `£2,000` bi-weekly → `2000 × 1.27 × 26 = $66,040`.

**Why some salaries later FAIL validation:** Monthly × 12 and Bi-Weekly × 26 on already-large source amounts can exceed the $2M ceiling. The cleaner does **not** cap them. It converts faithfully; validation reports the outliers.

### 6.5 Departments

The original string is stored in `department_original`. The mapped standard name goes in `department`. Unknown non-null values are nulled and flagged `department_unmapped=True`. Those rows are aggregated into `unmapped_departments.csv` for taxonomy review.

On the current extracts every department already matches the English list, so that review file is headers-only.

### 6.6 Dates

Hire date, payroll effective date, and benefit enrollment date are parsed with an explicit format list (`YYYY-MM-DD`, `MM/DD/YYYY`, `DD-Mon-YYYY`, several ISO timestamps), then a pandas fallback for other ISO variants. Timezones are dropped so everything is naive `datetime64[ns]`.

A date is flagged `*_invalid` when:

- the source was non-empty but unparseable, or
- the parsed value is before 1970-01-01 or after today.

The parsed timestamp is **kept** even when out of range, so a reviewer can see `1960-01-01` instead of a blank.

After cleaning, `export_unmapped_departments()` writes the department exception report, and the orchestrator still holds four separate cleaned frames.

---

## 7. Stage 3 — Deduplicate (`dedup.py`)

**What it is:** Build one employee row per canonical HRIS person, attach payroll and benefits when IDs match, detect payroll-only ghosts, and emit fuzzy pairs for humans.

**Why HRIS is the spine:** Payroll-only IDs are not published as employees. Paying someone who is not in HRIS is a review problem (ghost), not a golden-record problem. Benefits never create a person; they only enrich one.

High-level flow inside `deduplicate_employees()`:

```text
HRIS rows (GT + AC)
        │
        ▼
  collapse duplicate namespaced IDs     ← Pass 1a
        │
        ├─ left-join aggregated payroll  ← Pass 1b (exact ID)
        ├─ left-join aggregated benefits ← Pass 1c (exact ID)
        │
        ▼
  ghost report: payroll IDs not in HRIS
        │
        ▼
  merge rare cross-company emails        ← Pass 2 (auto-merge)
        │
        ▼
  score close-hire-date name pairs       ← Pass 3 (review only, no merge)
```

### 7.1 Collapse HRIS by namespaced ID

`collapse_hris_by_employee_id()` concatenates the two HRIS frames and keeps one row per `employee_id`. Sort order:

1. Source priority (both HRIS sources are priority 1).
2. Prefer raw IDs that do **not** contain `DUP` (canonical `ACQ_00001` beats `ACQ_DUP_00001`).

If several rows shared an ID, `dedup_method` becomes `exact_id`; otherwise `single_source`. `source_systems` starts as the surviving HRIS system name.

On the current data this turns **18,200** HRIS rows into **18,001** people: the 200 AcquiredCo `ACQ_DUP_*` IDs namespace onto the same `AC-######` as the canonical rows (plus one extra `AC-000000` from `ACQ_DUP_00000`).

### 7.2 Aggregate payroll and benefits before joining

Joining 19,000 payroll rows or 12,000 enrollments directly onto 18,001 people would duplicate employees. So:

**Payroll:** sort by employee ID, latest `payroll_effective_date` first, then take the first row per ID. One current pay profile per person.

**Benefits:** group by employee ID. Plan names and coverage levels are concatenated in **enrollment-date order** (blanks become `N/A`). Plan count is the number of enrollment rows. Premiums are summed. `benefit_enrollment_date` is the **earliest** enrollment date (`min`). `benefits_enrolled` is true if any row was enrolled.

### 7.3 Pass 1 — exact namespaced ID (auto-merge)

Left-join payroll fields and benefits fields onto the HRIS spine. When a join hits:

- append `,payroll` / `,benefits` to `source_systems`
- set `dedup_method` to `exact_id`

Employees with no benefits get `benefits_enrolled=False` and `benefit_plan_count=0`. `source_systems` is then sorted by source priority so the string is stable (`acquiredco_hris,payroll` not the reverse).

This is the pass that does almost all of the real work on these files.

### 7.4 Ghost employees

Any payroll row whose namespaced ID is **not** in the Pass 1 employee list is a ghost. Multiple ghost rows for the same ID collapse to the latest effective date. The report columns are:

`payroll_employee_id`, `name`, `salary_usd_annual`, `ghost_flag_reason`, `ghost_employee`, `company_origin`, `source_system`

On the current extracts **every payroll ID matches an HRIS ID after namespacing**, so `ghost_employees.csv` is headers-only. The detector and export still run; the empty file is the proof that the check executed.

### 7.5 Pass 2 — cross-company email (auto-merge)

Same normalized email (trim + lowercase) appearing in **both** companies, with more than one row, is treated as one person (for example a contractor in both HRIS systems). The surviving row is the higher-priority source; empty fields are filled from the other row; `dedup_method` becomes `email_match`.

Same-company duplicate emails are **not** merged here. That is why the later UNIQUE-email check can still FAIL: many GlobalTech (and AcquiredCo) people share an address inside one company in this synthetic data.

On the current extracts **zero** emails appear in both companies, so Pass 2 is a no-op. The code path is implemented and unit-tested.

### 7.6 Pass 3 — fuzzy name + hire-date window (review only)

This pass never changes the employee table. It writes candidates for HR.

1. Drop rows without hire date or without a usable full name.
2. Sort by hire date.
3. For each person, only look at later people whose hire date is within **30 days** (two-pointer blocking).
4. Skip same-company pairs and identical IDs — the interesting case is GlobalTech vs AcquiredCo after the acquisition.
5. Score `first_name + last_name` with RapidFuzz `token_sort_ratio` (order of tokens does not matter: “Allen John” vs “John Allen”).
6. Keep pairs with score ≥ **88**.
7. Sort by highest score, then smallest date gap; drop duplicate ID pairs.

Each review row includes both IDs, both names, both companies, similarity, hire-date difference, `recommended_action=review`, and `dedup_method=fuzzy_name`.

Current output: **113** probable pairs, scores from 88 to 100. Example: `GT-007166` “John Allen” and `AC-000000` “John Allen”, same hire date, score 100 — still not merged into golden data.

### 7.7 Provenance on every golden row

`_ensure_provenance()` guarantees `source_systems` and `dedup_method`. If a row lists multiple sources but still says `single_source`, it is corrected to `exact_id`. `fuzzy_name` appears on the review CSV, not on auto-merged golden rows.

Current golden mix:

| `dedup_method` | Rows | Meaning |
|---|---|---|
| `exact_id` | 14,692 | ID collision collapse and/or payroll/benefits enrichment |
| `single_source` | 3,309 | One HRIS row, no extra sources attached |
| `email_match` | 0 | No cross-company email hits in this extract |

`source_systems` combinations include full triple `globaltech_hris,payroll,benefits` (4,762 people) down to HRIS-only rows.

Ghost and probable-match CSVs are written at the end of this stage (and written again during final export).

---

## 8. Stage 4 — Validate (`validate.py`)

**What it is:** Score the deduplicated employee table against 15 rules, write CSV + HTML reports, then decide whether publishing is allowed.

**Why a reusable class:** `DataQualityValidator` only knows how to run generic checks (not-null, unique, regex, allowed set, numeric range, date range, referential integrity). `run_quality_checks()` is the GlobalTech-specific checklist. The same class could be pointed at another dataset.

A check’s pass rate is `(total − failed) / total`. Empty totals count as 100%. Status is PASS if pass rate ≥ 0.95.

### 8.1 The 15 checks

| # | Check | What it asks |
|---|---|---|
| 1–6 | NOT NULL | `employee_id`, `first_name`, `last_name`, `email`, `department`, `country` must be present |
| 7–8 | UNIQUE | Email (case/whitespace insensitive) and employee ID must not repeat |
| 9–10 | VALUES IN SET | Employment type in {Full-Time, Part-Time, Contractor}; currency in {USD, EUR, GBP} when present |
| 11–12 | REGEX | Email looks like an email; ID matches `GT-######` or `AC-######` |
| 13 | NUMERIC RANGE | `salary_usd_annual` between 15,000 and 2,000,000 **when present** |
| 14 | DATE RANGE | `hire_date` between 1970-01-01 and today |
| 15 | REFERENTIAL INTEGRITY | Every non-null `manager_id` exists as an `employee_id` in the same table |

Salary and currency checks evaluate only non-null salaries (currently 11,139 people), not the full 18,001. Manager integrity evaluates 16,187 managers, not people without a manager.

### 8.2 The gate

`enforce_quality_gate()` counts **checks** that FAIL, not failed rows. Up to two failed checks are allowed. Three or more raise `QualityGateError`, which `pipeline.py` logs as critical and re-raises **before** EDA and golden export. The quality CSV/HTML are still written first, so you can see why it stopped.

### 8.3 What the current run actually scored

| Check | Pass rate | Status | Why |
|---|---|---|---|
| UNIQUE: email | 50.77% (8,861 duplicate emails) | **FAIL** | Synthetic HRIS reuses addresses inside a company; Pass 2 only merges *cross-company* collisions |
| NUMERIC RANGE: salary | 72.94% (3,014 of 11,139 above $2M) | **FAIL** | Annualizing monthly/bi-weekly pay on this extract overshoots the ceiling |
| The other 13 checks | ≥ 99.6% | PASS | Including 64 missing departments and 41 missing countries, which still clear 95% |

Two FAILs = at the limit, so the **gate passes** and publishing continues. That is intentional: the pipeline surfaces data problems without blocking a day-1 deliverable for issues the extracts themselves cause.

---

## 9. Stage 5 — Visualize (`visualize.py`)

**What it is:** One 2×3 figure, 20×11 inches, saved at **300 DPI** as `data/processed/hr_eda_report.png`.

**Why after the gate:** Charts should describe the dataset we are willing to publish, together with the quality outcome that justified publishing.

The six panels:

1. **Headcount by department** — horizontal bars, unknown departments labeled `(Unknown)`.
2. **Headcount by country (top 15)** — vertical bars.
3. **Salary by employment type** — boxplots of annual USD, outliers hidden, values clipped at $2M **for display only** so a few multi-million annualized rows do not squash the axis. The golden data is not clipped.
4. **Tenure distribution** — histogram of years since hire, median line annotated.
5. **Benefits enrollment rate by department** — percent with `benefits_enrolled=True`. AcquiredCo is mostly unenrolled because benefits are GlobalTech-focused, which pulls some department rates down.
6. **Data quality summary** — grouped bars of passed vs failed **records** per check (not just PASS/FAIL status).

### Why these chart types (and not the brief’s alternatives)

The assignment asks for six charts. Two of them allow a choice (country: choropleth or bar; salary: violin or box). We picked the type that stays readable on a single 2×3 PNG, matches the data we actually have, and does not add extra geo libraries.

| # | Brief option(s) | What we drew | Why |
|---|---|---|---|
| 1 | Horizontal bar (required) | Horizontal bar, sorted ascending | Department **names** are long. Horizontal bars keep labels fully readable and make size comparison easy (longer bar = more people). A vertical bar would rotate 18 labels into a cramped x-axis. A pie or donut would hide ranking and break down with many slices. |
| 2 | **Choropleth or bar** | Vertical bar, **top 15** countries | **Bar, not choropleth.** `country` is free-text (`United Kingdom`, `Hong Kong`, `India`, …), not ISO codes or coordinates. A map needs a geo library and shapefiles (`geopandas` is not in `requirements.txt`); matplotlib/seaborn alone cannot draw a reliable world choropleth. Small countries and city-like values (Hong Kong) disappear or mis-draw on a map. Color-as-count is also harder to read than bar length. Top 15 keeps the panel readable; the long tail would be a smear of tiny bars. |
| 3 | **Violin or box** | Boxplot, fliers hidden, display clipped at $2M | **Box, not violin.** HR compensation questions are about **median, spread, and IQR** across Full-Time / Part-Time / Contractor — exactly what a boxplot shows. A violin adds a kernel-density shape that looks more precise than this extract deserves: about 3,000 annualized salaries sit above $2M, so a violin would stretch or pile density at the cap and imply a smooth distribution that is an artifact of Monthly×12 / Bi-Weekly×26. We clip **only for the picture** and hide fliers so those outliers do not squash the axis; golden data is unchanged. |
| 4 | Histogram (required) | Histogram, 20 bins, median line | Tenure is a continuous “how many years?” question. A histogram shows the shape (lots of recent hires vs a long-tenured tail). The median line answers “typical tenure” in one number. A bar of tenure buckets would throw away resolution; a boxplot would hide multimodality. |
| 5 | Bar (required) | Vertical bar, y-axis fixed 0–100% | The metric is already a **rate per department**. Bars compare rates directly. A stacked enrolled/not-enrolled bar would mix headcount size into the story; HR planning cares about *percent enrolled*, not raw enrolled counts (large departments would dominate). Fixing the axis at 0–100% stops a 40–50% range from looking like a huge gap. |
| 6 | Grouped bar: passed vs failed per check (required) | Grouped bar of **record** counts | Pipeline health is “how many rows failed each rule,” not only PASS/FAIL at 95%. Grouped bars show both magnitudes on the same check. A pie of “13 passed / 2 failed checks” would hide that UNIQUE email failed ~8,800 rows while a NOT NULL check failed 64. A stacked 100% bar would hide absolute volume. |

Colors use the Okabe–Ito colorblind-safe palette. Each chart has a source footnote so a screenshot is still attributable. The figure header includes generation time and employee count. Matplotlib’s `Agg` backend is used so the PNG can render on a server without a display.

---

## 10. Stage 6 — Export (`export.py`)

**What it is:** The only module that writes pipeline artifacts (plus logging). Transformations stay testable without touching disk; tests monkeypatch these writers.

Final `export_final_artifacts()` writes:

| Artifact | Behavior |
|---|---|
| Golden Parquet | **Replace** the `golden_employees/` directory, then write Snappy-compressed Parquet partitioned by `company_origin` |
| `docs/schema.md` | Regenerated from live dtypes, descriptions, and one example value per column |
| Ghost CSV | Rewrite (headers only if none) |
| Probable-match CSV | Rewrite with review columns |

Extra helpers used by earlier stages: dead letters (append), unmapped departments, quality CSV/HTML, EDA PNG.

Parquet prep converts mixed `object` columns to pandas string so pyarrow does not fail on mixed types. Missing `company_origin` is filled as `Unknown` rather than dropping people. Consumers can read everything or one partition:

```python
import pandas as pd

employees = pd.read_parquet("data/processed/golden_employees")
globaltech = pd.read_parquet("data/processed/golden_employees/company_origin=GlobalTech")
```

The golden **grain** is one row per surviving canonical `employee_id`. Identity and person fields come from HRIS. Pay and benefits are enrichment. Fuzzy twins remain two rows until a human says otherwise.

---

## 11. Orchestration (`pipeline.py`)

`run_pipeline()` is the production path:

1. Log a banner and start time.
2. Ingest → clean → dedup (employees, ghosts, probable matches).
3. Validate with the gate **on**.
4. On `QualityGateError`: log critical, do not run EDA/export, re-raise.
5. Otherwise: EDA, then golden export.
6. Log per-source counts, ghost/probable counts, checks passed, artifact paths, `dedup_method` breakdown, and duration.

Each `run_*` helper can also be called alone. If you call `run_cleaning()` with no argument, it runs ingest first. That is convenient in the notebook; the full pipeline passes frames explicitly so no stage is repeated.

---

## 12. How a single person flows through (example)

Take GlobalTech HRIS employee `14571`, payroll row `14571` / GlobalTech / monthly EUR, and two benefit enrollments for `14571`.

1. **Ingest:** three frames, three grains. HRIS has the name and department. Payroll has pay. Benefits has Vision + Dental.
2. **Clean:** ID becomes `GT-014571` in all three. Salary becomes `base_salary × 1.09 × 12`. Names title-cased. Dates parsed.
3. **Dedup:** HRIS row is the spine. Latest payroll profile is joined. Both plans concatenate to `Vision,Dental` (in date order). `source_systems` = `globaltech_hris,payroll,benefits`. `dedup_method` = `exact_id`.
4. **Validate:** this person is one of 18,001 rows. If their annual USD is above $2M they count as a salary-range failure, but they still remain in the table.
5. **Export:** they land in `company_origin=GlobalTech/` with raw ID `14571` still sitting in `employee_id_raw`.

If the same legal name also exists at AcquiredCo with a hire date within 30 days, Pass 3 adds a probable-match row. Both golden rows stay. HR decides later whether to merge.

---

## 13. Tests and the walkthrough notebook

The pytest suite (`tests/`) uses tiny in-memory frames and temp directories. It does **not** re-process the 15k-row extracts. Coverage includes:

- schema alignment and every cleaner
- payroll/benefits aggregation, DUP collapse, ghosts, email merge, fuzzy review-without-merge
- 15-check suite and gate boundaries (2 FAILs allowed, 3 raise)
- empty review CSVs keep required headers; Parquet partitions; PNG write
- `run_pipeline()` stage order with mocked boundaries

Run from `sk1-capstone/`:

```bash
python3 -m pytest
```

`notebooks/capstone_pipeline.ipynb` is an optional interactive walkthrough of the same functions, useful for inspecting intermediate DataFrames without reading logs.

---

## 14. What “done” looks like on this implementation

You have finished this project when you can point at the code and the outputs together:

- Four heterogeneous extracts load into one schema, with bad rows dead-lettered rather than crashing the job.
- Namespaced `GT-` / `AC-` IDs make cross-system joins possible without colliding numeric IDs.
- HRIS is the employee spine; payroll and benefits enrich; ghosts and fuzzy pairs are review artifacts.
- Fifteen quality checks run; two documented FAILs (shared emails, annualized salaries over $2M) still pass the gate.
- EDA PNG, partitioned golden Parquet (18,001 rows), schema markdown, and review CSVs are produced from `python3 pipeline.py`.
- Tests lock the transformation rules so a future extract change is visible.

If you can explain each of those bullets using this document, you understand the implemented pipeline end to end.

---

## 15. Possible questions and answers

These are the kinds of questions a reviewer, interviewer, or stakeholder might ask. Answers stay in everyday language. They describe **this** project, not a generic textbook.

### What is the business goal? What is this project trying to achieve?

GlobalTech just bought AcquiredCo. HR cannot plan Day 1, check benefits, move payroll, or report headcount to regulators if “who works here, in which role, at what cost” lives in four disagreeing files.

The goal is a **single trusted employee list** — one cleaned row per person we are confident about — plus side reports for problems humans must review (ghosts, lookalike names, unmapped departments). Downstream teams should stop arguing over four extracts and start from the golden dataset.

### Why draw an architecture first?

If you start by writing loaders, you discover too late that payroll is “many rows per person,” benefits is “many plans per person,” and HRIS is “one row per person.” You then glue them together in a way that double-counts people or invents employees from a paycheck.

Architecture first means agreeing, on paper:

- what comes in and what goes out;
- which system is allowed to *create* a person (HRIS) vs only *enrich* one (payroll, benefits);
- what happens to bad rows (dead letter, do not crash);
- when publishing is allowed (quality gate).

The picture for this project is:

```text
  GlobalTech CSV    AcquiredCo JSON    Payroll Excel    Benefits XML
           \              |                 |               /
            \             |                 |              /
             v            v                 v             v
                    Integration pipeline
              ingest → clean → dedup → validate
                         |              |
                    review CSVs    quality gate
                         |              |
                         v              v
                    EDA PNG      Golden employees (Parquet)
                                 + schema documentation
```

That sketch is what `docs/architecture.md` then spells out in modules. The code follows the sketch; the sketch is not reverse-engineered from the code.

### Why is removing duplicates essential?

If the same person appears twice, headcount is wrong, someone can be paid twice, and merger reports to regulators are false. After an acquisition this is especially likely: both companies may have hired the same contractor, or AcquiredCo’s file may contain synthetic `ACQ_DUP_*` collisions.

This pipeline removes duplicates **conservatively**:

- same namespaced ID → treat as one person and keep one row;
- same email across *both* companies → treat as one person (rare here);
- similar name + close hire dates → **do not** auto-merge; send to HR.

We would rather leave two rows for a human than silently fuse two different people. Duplicate *paychecks* for one ID are collapsed to the latest effective date so salary is not double-counted.

### Why are validations essential?

Cleaning does not prove the result is fit to use. Validation is the checklist after the move: “Did every employee still have a name? Are IDs in the `GT-` / `AC-` shape? Do manager IDs point at real people?”

Without it you could publish a golden file that looks complete and still contain 8,000 shared emails or thousands of salaries that annualized above $2M. Those two issues **did** fail checks on this extract. Because we validate, they are visible in the quality report instead of hidden in a spreadsheet someone trusts.

The **gate** (stop if more than two checks fail) is the business control: do not hand Day-1 planners a dataset we already know is badly broken.

### The data and schema keep changing (or arriving skewed). What do you do?

Source systems will add columns, rename fields, send a new employment code, or drop a required ID. If every stage assumed “the Excel file always looks like last month,” the pipeline would crash or silently load nonsense.

This project’s answer is: **define a contract, then enforce it.**

1. **A standard schema** — every source is mapped onto the same column list (`employee_id`, `first_name`, `salary_usd_annual`, …). Extra source fields that we do not care about are ignored. Missing fields become empty, not invented.
2. **Required fields at the door** — if GlobalTech CSV has no `employee_id` column, or a JSON person has no identifier, that file or row is dead-lettered. We do not guess an ID.
3. **Mappings for values that drift** — employment types and departments go through lookup tables. Unknown values are logged and flagged (`department_unmapped`) instead of being forced into “Engineering.”
4. **Keep the original** — `employee_id_raw`, `department_original`, and invalid-date flags mean we can explain a change when next month’s extract looks different.

“Skew” here also means **uneven volume**: 15,000 GlobalTech people vs 3,000 AcquiredCo, benefits covering GlobalTech only. The pipeline does not pretend coverage is equal. It records `benefits_enrolled=False` where there is no enrollment, and partitions the golden file so you can still read one company without pretending the other is the same size.

### Why Parquet (not CSV) for the golden dataset?

CSV is easy to open in Excel, but it is a poor **system of record** for 18,000 employees with mixed types (dates, true/false, money).

Parquet is a compressed, columnar file format made for analytics:

- it stores types (a hire date stays a date, not the text `"2016-09-21"`);
- it is much smaller on disk (Snappy compression);
- tools can read **one company folder** without loading the other (`company_origin=GlobalTech`);
- it is what warehouses and notebooks already expect.

Review files (ghosts, probable matches, quality) stay CSV because humans open those in Excel. The golden spine is Parquet because machines will keep reading it.

The two folders under `golden_employees/` are still **one** dataset — see the earlier note on partitioning. They are not two competing truths.

### Why have test cases if we already ran the pipeline on the real files?

The full run proves “this month’s four files produced 18,001 rows.” It does **not** prove that next month, when one salary looks like `($1,200)` or one AcquiredCo ID is `ACQ_DUP_00001`, the rules still behave.

Tests use **tiny made-up tables** so we can say, in seconds:

- `$10,000` monthly becomes `$120,000` annual USD;
- `ACQ_DUP_*` loses to the canonical AcquiredCo row;
- the quality gate allows two failed checks and stops at three;
- an empty ghost file still has the required column headers.

If someone “improves” ID namespacing and breaks joins, pytest fails before we republish a wrong golden file. Running the whole 15,000-row extract to check one rule would be slow and easy to skip.

### Parallel processing — when we load more data, besides pagination?

Today the job is a **single laptop process**, one stage after another. AcquiredCo JSON is walked in pages of 100 only to *simulate* an API; it is not faster because of that.

If volumes grew (hundreds of thousands of rows, or nightly loads), pagination alone would not be enough. Practical next steps, in order of how this codebase is already split:

1. **Load the four sources at the same time** — CSV, JSON, Excel, and XML do not depend on each other. Four workers could ingest in parallel, then meet at cleaning.
2. **Clean each source in parallel** — name/ID/salary rules do not need the other files until dedup.
3. **Split large files into chunks** — for example payroll by company, or JSON pages fetched from a real API concurrently (with a rate limit so we do not hammer BambooHR).
4. **Move heavy steps off pandas** — Spark, Dask, or a warehouse SQL job, still using the same stage boundaries (ingest / clean / match / validate / publish).
5. **Write partitions in parallel** — GlobalTech and AcquiredCo Parquet folders can land independently once the in-memory table exists.

Dedup is the step that is hardest to parallelize naively: fuzzy name matching must compare people *across* companies. You parallelize by blocking (we already only compare hire dates within 30 days), not by blindly splitting the file in half.

### What else would you do before this goes to production?

This capstone is a **controlled local batch**. Production would still use the same stages, plus the boring operational layer:

| Gap today | What production would add |
|---|---|
| Files on a laptop | Read from a secured landing zone or HR APIs; write golden data to a cataloged table (not a folder someone might overwrite) |
| Anyone with the repo can see names, emails, salaries | Access control, encryption at rest, retention and deletion rules for employee PII |
| Run by hand (`python3 pipeline.py`) | Schedule (Airflow, Dagster, or similar); alert if the job fails or the quality gate fires |
| Config baked into `config.py` | Environment-specific rates, thresholds, and paths (dev vs prod) without changing code |
| Fuzzy pairs sit in a CSV | A persistent identity crosswalk: HR approves a match once, and later loads reuse that decision |
| Two failed checks still publish | Weight critical checks (missing employee ID) harder than cosmetic ones; maybe block on UNIQUE ID even if email uniqueness fails |
| Logs on disk | Metrics and dashboards: row counts, duration, dead-letter volume, gate status |
| Pandas in one process | Scale-out engine if volume grows (see parallel processing above) |

The architecture is already shaped so those swaps are *replacements at the edges* (how we read, how we write, how we schedule), not a rewrite of “HRIS is the spine.”

### A few more architecture and implementation questions

**Why is HRIS the employee spine, not payroll?**  
Payroll tells you who got paid. HRIS tells you who is an employee. A paycheck with no HR record is a **ghost** — a compliance risk — not a person we should add to the official headcount. Benefits never create a person either; they only attach plans to someone HR already knows.

**Why namespace IDs (`GT-001042` vs `AC-001042`)?**  
Both companies used overlapping numbers. Without a prefix, employee `1042` at GlobalTech and employee `1042` at AcquiredCo would look like one person. The prefix is a cheap, explicit way to say “same digits, different companies” until a later match (email or HR review) proves otherwise.

**Why dead-letter bad rows instead of failing the whole job?**  
Day 1 still needs a dataset. One broken JSON employee, or one payroll row with a blank ID, should not block 18,000 good rows. We park the bad record with a reason, continue, and let someone fix the source. A **missing source file** is also logged rather than crashing, so you can see which input was empty.

**Why not auto-merge fuzzy name matches?**  
“John Allen” hired on the same day in both companies *might* be one person — or two people with a common name. Merging them in code could hide a real employee and under-count the merger. The review file is the product: HR confirms; the pipeline does not play HR.

**Why allow two quality checks to fail and still publish?**  
The assignment (and this extract) expect some known mess: shared emails in the synthetic HRIS, salaries that annualize above $2M. A gate of “everything must be perfect” would never publish. Two failed *checks* (not two failed rows) is a compromise: surface the problems, still deliver Day 1, stop only when the file is broadly untrustworthy.

**Is the golden dataset “done” identity resolution?**  
No. It is Day-1 *best effort*. Exact IDs and cross-company emails are merged. Lookalikes wait for people. Production would keep an approved match table so we do not ask HR the same question every night.
