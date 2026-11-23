# CloudHR Power Query M

Parameters, created before these queries: `ServerName` = `localhost:5435`, `DatabaseName` = `cloudhr`. Import mode.

`workforce_base` is a staging query. Uncheck **Enable load** so it does not become a table. `salary_errors` and `security_users` are hidden in report view. `security_users` is the view `security.security_users`. Do not load `security.security_mapping` from Postgres.

## workforce_base

```m
// workforce_base — snapshots joined to employees, names never selected
let
    Source     = PostgreSQL.Database(ServerName, DatabaseName),
    Snapshots  = Source{[Schema = "hr", Item = "employee_monthly_snapshots"]}[Data],
    Employees  = Source{[Schema = "hr", Item = "employees"]}[Data],
    People     = Table.SelectColumns(Employees, {
                     "employee_id", "employment_type", "hire_date",
                     "termination_date", "termination_reason"}),
    Joined     = Table.NestedJoin(Snapshots, {"employee_id"}, People, {"employee_id"},
                     "Employee", JoinKind.Inner),
    Expanded   = Table.ExpandTableColumn(Joined, "Employee", {
                     "employment_type", "hire_date", "termination_date", "termination_reason"})
in
    Expanded
```



## salary_errors

```m
// salary_errors — original rows whose salary is zero or negative
let
    Source = workforce_base,
    Bad    = Table.SelectRows(Source, each [base_salary_usd] <> null and [base_salary_usd] <= 0),
    Keep   = Table.SelectColumns(Bad, {
                 "snapshot_month", "employee_id", "org_id", "department_id",
                 "job_level", "base_salary_usd"}),
    Typed  = Table.TransformColumnTypes(Keep, {
                 {"snapshot_month", type date}, {"employee_id", Int64.Type},
                 {"org_id", Int64.Type}, {"department_id", Int64.Type},
                 {"job_level", type text}, {"base_salary_usd", Currency.Type}})
in
    Typed
```



## fact_employee_monthly

Keeps every snapshot row. A non-positive salary becomes null here, after `salary_errors` has copied the original value. `salary_band` is added after that nulling step, and `salary_band_sort` orders those bands from lowest to highest. `DateKey` is the last day of `snapshot_month` as `YYYYMMDD`.

```m
// fact_employee_monthly
let
    Source   = workforce_base,
    WithEnd  = Table.AddColumn(Source, "MonthEnd", each Date.EndOfMonth([snapshot_month]), type date),
    WithKey  = Table.AddColumn(WithEnd, "DateKey", each
                   Date.Year([MonthEnd]) * 10000 + Date.Month([MonthEnd]) * 100 + Date.Day([MonthEnd]),
                   Int64.Type),
    WithFlag = Table.AddColumn(WithKey, "is_data_error", each
                   [termination_date] <> null and [hire_date] > [termination_date], type logical),
    NullPay  = Table.TransformColumns(WithFlag, {
                   "base_salary_usd", each if _ = null or _ > 0 then _ else null, Currency.Type}),
    WithBand = Table.AddColumn(NullPay, "salary_band", each
                   if [base_salary_usd] = null then null
                   else if [base_salary_usd] < 50000 then "Under 50,000"
                   else if [base_salary_usd] < 75000 then "50,000-74,999"
                   else if [base_salary_usd] < 100000 then "75,000-99,999"
                   else if [base_salary_usd] < 150000 then "100,000-149,999"
                   else if [base_salary_usd] < 200000 then "150,000-199,999"
                   else "200,000 and above", type text),
    WithSort = Table.AddColumn(WithBand, "salary_band_sort", each
                   if [salary_band] = "Under 50,000" then 1
                   else if [salary_band] = "50,000-74,999" then 2
                   else if [salary_band] = "75,000-99,999" then 3
                   else if [salary_band] = "100,000-149,999" then 4
                   else if [salary_band] = "150,000-199,999" then 5
                   else if [salary_band] = "200,000 and above" then 6
                   else null, Int64.Type),
    Dropped  = Table.RemoveColumns(WithSort, {"MonthEnd"}),
    Typed    = Table.TransformColumnTypes(Dropped, {
                   {"snapshot_month", type date}, {"employee_id", Int64.Type},
                   {"org_id", Int64.Type}, {"is_active", type logical},
                   {"job_level", type text}, {"department_id", Int64.Type},
                   {"employment_type", type text}, {"hire_date", type date},
                   {"termination_date", type date}, {"termination_reason", type text},
                   {"DateKey", Int64.Type}, {"is_data_error", type logical},
                   {"base_salary_usd", Currency.Type}, {"salary_band", type text},
                   {"salary_band_sort", Int64.Type}})
in
    Typed
```

For the performance test, drop `snapshot_month` after `DateKey` is built. No measure reads it. In `Dropped`, remove `snapshot_month` along with `MonthEnd`, and delete `{"snapshot_month", type date}` from `Typed`. Leave this query as it is until that test.

## dim_organisation

```m
// dim_organisation
let
    Source   = PostgreSQL.Database(ServerName, DatabaseName),
    Rows     = Source{[Schema = "org", Item = "organisations"]}[Data],
    Selected = Table.SelectColumns(Rows, {
                   "org_id", "org_name", "industry", "employee_count_band",
                   "country", "subscription_tier"}),
    Typed    = Table.TransformColumnTypes(Selected, {
                   {"org_id", Int64.Type}, {"org_name", type text},
                   {"industry", type text}, {"employee_count_band", type text},
                   {"country", type text}, {"subscription_tier", type text}})
in
    Typed
```



## dim_department

```m
// dim_department
let
    Source   = PostgreSQL.Database(ServerName, DatabaseName),
    Rows     = Source{[Schema = "org", Item = "departments"]}[Data],
    Selected = Table.SelectColumns(Rows, {
                   "department_id", "org_id", "department_name",
                   "department_group", "cost_centre"}),
    Typed    = Table.TransformColumnTypes(Selected, {
                   {"department_id", Int64.Type}, {"org_id", Int64.Type},
                   {"department_name", type text}, {"department_group", type text},
                   {"cost_centre", type text}})
in
    Typed
```



## dim_employee

```m
// dim_employee — current staff only: latest snapshot is active, and termination_date is null
let
    Source    = PostgreSQL.Database(ServerName, DatabaseName),
    Snapshots = Source{[Schema = "hr", Item = "employee_monthly_snapshots"]}[Data],
    Employees = Source{[Schema = "hr", Item = "employees"]}[Data],
    Latest    = Table.SelectColumns(
                    Table.SelectRows(Snapshots, each [snapshot_month] = #date(2026, 9, 1) and [is_active] = true),
                    {"employee_id"}),
    Current   = Table.SelectRows(Employees, each [termination_date] = null),
    Joined    = Table.NestedJoin(Current, {"employee_id"}, Latest, {"employee_id"}, "Snap", JoinKind.Inner),
    Selected  = Table.SelectColumns(Joined, {
                    "employee_id", "department_id", "job_level", "employment_type", "hire_date"}),
    Typed     = Table.TransformColumnTypes(Selected, {
                    {"employee_id", Int64.Type}, {"department_id", Int64.Type},
                    {"job_level", type text}, {"employment_type", type text},
                    {"hire_date", type date}})
in
    Typed
```



## dim_job_level

```m
// dim_job_level — junior to senior
let
    Levels = #table(
        type table [job_level = text, level_sort = Int64.Type],
        {
            {"IC1", 1}, {"IC2", 2}, {"IC3", 3}, {"IC4", 4},
            {"M1", 5}, {"M2", 6}, {"M3", 7}
        })
in
    Levels
```



## fact_leave

```m
// fact_leave — DateKey is the leave start date
let
    Source   = PostgreSQL.Database(ServerName, DatabaseName),
    Leave    = Source{[Schema = "hr", Item = "leave_records"]}[Data],
    Selected = Table.SelectColumns(Leave, {
                   "leave_id", "employee_id", "org_id", "leave_type",
                   "start_date", "end_date", "days_taken"}),
    WithKey  = Table.AddColumn(Selected, "DateKey", each
                   Date.Year([start_date]) * 10000 + Date.Month([start_date]) * 100 + Date.Day([start_date]),
                   Int64.Type),
    Typed    = Table.TransformColumnTypes(WithKey, {
                   {"leave_id", Int64.Type}, {"employee_id", Int64.Type},
                   {"org_id", Int64.Type}, {"leave_type", type text},
                   {"start_date", type date}, {"end_date", type date},
                   {"days_taken", Int64.Type}, {"DateKey", Int64.Type}})
in
    Typed
```



## fact_review

```m
// fact_review — DateKey is 1 January of review_year
let
    Source   = PostgreSQL.Database(ServerName, DatabaseName),
    Reviews  = Source{[Schema = "hr", Item = "performance_reviews"]}[Data],
    Selected = Table.SelectColumns(Reviews, {
                   "review_id", "employee_id", "org_id", "review_year", "rating"}),
    WithKey  = Table.AddColumn(Selected, "DateKey", each [review_year] * 10000 + 101, Int64.Type),
    Typed    = Table.TransformColumnTypes(WithKey, {
                   {"review_id", Int64.Type}, {"employee_id", Int64.Type},
                   {"org_id", Int64.Type}, {"review_year", Int64.Type},
                   {"rating", Int64.Type}, {"DateKey", Int64.Type}})
in
    Typed
```



## leave_entitlement

```m
// leave_entitlement — not stored in the source
let
    Allowance = #table(
        type table [leave_type = text, days_per_year = Int64.Type],
        {
            {"Annual", 20}, {"Sick", 10}, {"Parental", 60}, {"Other", 5}
        })
in
    Allowance
```



## security_users

Active employees only. The view already applies that rule: `termination_date` is null, and the September 2026 snapshot is active. Hide this table in report view. Do not relate it to any other table. `first_name` and `last_name` are not loaded. `level_sort` 5 and above is M1, M2, and M3.

```m
// security_users — sign-in rows for Tenant Access. Hidden and unrelated.
let
    Source   = PostgreSQL.Database(ServerName, DatabaseName),
    Rows     = Source{[Schema = "security", Item = "security_users"]}[Data],
    Selected = Table.SelectColumns(Rows, {
                   "email", "org_id", "department_id", "job_level", "level_sort"}),
    Typed    = Table.TransformColumnTypes(Selected, {
                   {"email", type text}, {"org_id", Int64.Type},
                   {"department_id", Int64.Type}, {"job_level", type text},
                   {"level_sort", Int64.Type}})
in
    Typed
```



## dim_date

Runs from 1 January 2022 through 30 September 2026. Fixed-date US federal holidays are flagged on the observed weekday: Friday when the date is a Saturday, Monday when it is a Sunday. Week number uses Sunday as the first day of the week.

```m
// dim_date
let
    Start = #date(2022, 1, 1),
    End   = #date(2026, 9, 30),
    Dates = List.Dates(Start, Duration.Days(End - Start) + 1, #duration(1, 0, 0, 0)),
    NthDow = (year as number, month as number, dow as number, n as number) as date =>
        let
            First  = #date(year, month, 1),
            Shift  = Number.Mod(dow - Date.DayOfWeek(First, Day.Sunday) + 7, 7),
            Result = Date.AddDays(First, Shift + 7 * (n - 1))
        in
            Result,
    LastMonday = (year as number, month as number) as date =>
        let
            Last = Date.EndOfMonth(#date(year, month, 1))
        in
            Date.AddDays(Last, -Date.DayOfWeek(Last, Day.Monday)),
    Observe = (d as date) as date =>
        if Date.DayOfWeek(d, Day.Sunday) = 6 then Date.AddDays(d, -1)
        else if Date.DayOfWeek(d, Day.Sunday) = 0 then Date.AddDays(d, 1)
        else d,
    Holidays = List.Buffer(List.Combine(List.Transform({2022, 2023, 2024, 2025, 2026}, (y) => {
        Observe(#date(y, 1, 1)),
        NthDow(y, 1, 1, 3),
        NthDow(y, 2, 1, 3),
        LastMonday(y, 5),
        Observe(#date(y, 6, 19)),
        Observe(#date(y, 7, 4)),
        NthDow(y, 9, 1, 1),
        NthDow(y, 10, 1, 2),
        Observe(#date(y, 11, 11)),
        NthDow(y, 11, 4, 4),
        Observe(#date(y, 12, 25))
    }))),
    Rows = List.Transform(Dates, (d) => [
        DateKey = Date.Year(d) * 10000 + Date.Month(d) * 100 + Date.Day(d),
        Date = d,
        Year = Date.Year(d),
        #"Month Number" = Date.Month(d),
        #"Month Name" = Date.MonthName(d),
        Quarter = "Q" & Text.From(Date.QuarterOfYear(d)),
        #"Day of Week" = Date.DayOfWeekName(d),
        #"Is Weekend" = let dow = Date.DayOfWeek(d, Day.Sunday) in dow = 0 or dow = 6,
        #"Is Holiday" = List.Contains(Holidays, d),
        #"Week Number" = Date.WeekOfYear(d, Day.Sunday)
    ]),
    Typed = Table.TransformColumnTypes(Table.FromRecords(Rows), {
        {"DateKey", Int64.Type}, {"Date", type date}, {"Year", Int64.Type},
        {"Month Number", Int64.Type}, {"Month Name", type text},
        {"Quarter", type text}, {"Day of Week", type text},
        {"Is Weekend", type logical}, {"Is Holiday", type logical},
        {"Week Number", Int64.Type}})
in
    Typed
```

