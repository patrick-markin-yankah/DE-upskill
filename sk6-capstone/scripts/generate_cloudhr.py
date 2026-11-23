"""Generate the CloudHR source data for the SK-06 capstone.

Writes seven CSV files into the folder given by --out (default: data).
Only the Python standard library is used. The random seed is fixed, so
the control totals do not move. Do not change SEED once those totals
are written down.

snapshot_month is the first day of the month. Power Query builds the
month-end DateKey from it.

Employee-count bands are the real-world labels from the brief. Loaded
headcount stays at or under 50,000 employees: the smallest organisation
has 50 people and the largest has 2,000. No organisation is loaded at
10,000. Snapshots run from January 2023 through September 2026, the last
closed month. Review years stop at 2025 because 2026 has not closed.
A few illegal rows are planted on purpose and left in the files.
Each employee email is first.last.employee_id@orgN.cloudhr.com.
"""
import argparse
import csv
import datetime as dt
import random
from collections import defaultdict
from pathlib import Path

SEED = 20261020
N_BAD_DATES = 16
N_BAD_SALARIES_DECEMBER = 8
N_BAD_SALARIES_OTHER = 24
EMPLOYEE_CAP = 50000

WINDOW_START = dt.date(2023, 1, 1)
LAST_SNAPSHOT = dt.date(2026, 9, 1)  # last closed month; the file is current as of 20 Oct 2026
LAST_REVIEW_YEAR = 2025              # 2026 is partial, so it has no performance reviews
HIRE_EARLIEST = dt.date(2014, 1, 1)

# Most junior to most senior. dim_job_level uses this order later.
LEVELS = ["IC1", "IC2", "IC3", "IC4", "M1", "M2", "M3"]
LEVEL_WEIGHTS = [22, 28, 22, 12, 9, 5, 2]
PAY_BANDS = (
    (48000, 62000),
    (64000, 86000),
    (88000, 118000),
    (120000, 155000),
    (150000, 190000),
    (185000, 240000),
    (230000, 310000),
)

INDUSTRIES = [
    "Technology", "Healthcare", "Financial Services", "Manufacturing",
    "Retail", "Professional Services", "Education", "Logistics",
]
COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Germany",
    "Australia", "Netherlands", "Ireland", "Singapore",
]
COUNTRY_FACTOR = {
    "United States": 1.00,
    "United Kingdom": 0.86,
    "Canada": 0.90,
    "Germany": 0.94,
    "Australia": 0.91,
    "Netherlands": 0.93,
    "Ireland": 0.88,
    "Singapore": 0.96,
}
# label, number of orgs, min loaded employees, max loaded employees
# The 1-50 band is loaded at 50. One organisation in the top band is set to 2,000.
SIZE_BANDS = [
    ("1-50", 100, 50, 50),
    ("51-200", 55, 70, 140),
    ("201-1000", 30, 250, 450),
    ("1001-10000", 15, 1400, 2000),
]
TIER_CHOICES = {
    "1-50": (["Starter", "Growth"], [8, 2]),
    "51-200": (["Starter", "Growth", "Enterprise"], [2, 7, 1]),
    "201-1000": (["Growth", "Enterprise"], [4, 6]),
    "1001-10000": (["Enterprise"], [1]),
}
# (department_group, department_name), shortest orgs take the prefix
ALL_DEPTS = [
    ("Engineering", "Software Engineering"),
    ("Sales", "New Business"),
    ("Operations", "Operations"),
    ("People & Finance", "People"),
    ("Customer", "Customer Success"),
    ("Operations", "Support"),
    ("Engineering", "Data"),
    ("People & Finance", "Finance"),
    ("Engineering", "Infrastructure"),
    ("Sales", "Customer Accounts"),
]
DEPT_COUNT = {"1-50": 4, "51-200": 6, "201-1000": 8, "1001-10000": 10}

NAME_A = [
    "Apex", "Brightline", "Cinder", "Harbor", "Lumen", "Northwind", "Pinnacle", "Summit",
    "Vantage", "Willow", "Copper", "Fieldstone", "Kindred", "Marlow", "Oakline", "Redwood",
    "Silver", "TrueNorth", "Union", "Westbridge",
]
NAME_B = [
    "Analytics", "Health", "Foods", "Logistics", "Systems", "Partners", "Retail", "Labs",
    "Manufacturing", "Education",
]

EMPLOYMENT_TYPES = ["Full-time", "Part-time", "Contract"]
EMPLOYMENT_WEIGHTS = [80, 12, 8]
TYPE_FACTOR = {"Full-time": 1.00, "Part-time": 0.60, "Contract": 1.05}
TERM_REASONS = ["Voluntary", "Involuntary", "End of Contract", "Retirement"]
TERM_WEIGHTS = [62, 18, 12, 8]
LEAVE_TYPES = ["Annual", "Sick", "Parental", "Other"]

FIRST_NAMES = [
    "Ama", "Kwame", "Efua", "Kofi", "Sarah", "James", "Linda", "David", "Grace", "Michael",
    "Akosua", "Yaw", "Esi", "Daniel", "Rita", "Paul", "Naomi", "Victor", "Abena", "Samuel",
]
LAST_NAMES = [
    "Mensah", "Owusu", "Johnson", "Smith", "Boateng", "Brown", "Asante", "Williams", "Osei", "Davis",
    "Appiah", "Miller", "Addo", "Wilson", "Agyeman", "Taylor", "Ansah", "Clark", "Frimpong", "Lewis",
]

SECURITY = [
    ("admin.org001@cloudhr.com", 1, "HR_ADMIN"),
    ("viewer.org001@cloudhr.com", 1, "HR_VIEWER"),
    ("viewer.org002@cloudhr.com", 2, "HR_VIEWER"),
]


def _months_through(start, last):
    months = []
    year, month = start.year, start.month
    while True:
        current = dt.date(year, month, 1)
        months.append(current)
        if current == last:
            return months
        month += 1
        if month == 13:
            year += 1
            month = 1


MONTHS = _months_through(WINDOW_START, LAST_SNAPSHOT)
WINDOW_END = dt.date(2026, 9, 30)


def month_end(month_start):
    if month_start.month == 12:
        return dt.date(month_start.year, 12, 31)
    return dt.date(month_start.year, month_start.month + 1, 1) - dt.timedelta(days=1)


def employed_on(emp, day):
    if emp["hire_date"] > day:
        return False
    term = emp["termination_date"]
    return term is None or term >= day


def add_weekdays(start, n_days):
    """Return the date that completes n_days weekdays, counting start."""
    day = start
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    left = n_days - 1
    while left > 0:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            left -= 1
    return day


def weekdays_between(start, end):
    options = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            options.append(day)
        day += dt.timedelta(days=1)
    return options


def annual_salary(emp, level_idx, month):
    lo, hi = PAY_BANDS[level_idx]
    amount = lo + emp["pay_percentile"] * (hi - lo)
    amount *= emp["country_factor"] * TYPE_FACTOR[emp["employment_type"]]
    amount *= 1.03 ** (month.year - 2023)
    return round(amount, 2)


def work_email(emp):
    # employee_id keeps the address unique when a name repeats inside one org.
    return (
        f"{emp['first_name']}.{emp['last_name']}.{emp['employee_id']}"
        f"@org{emp['org_id']}.cloudhr.com"
    ).lower()


def as_row(values):
    row = []
    for value in values:
        if value is None:
            row.append("")
        elif isinstance(value, bool):
            row.append("true" if value else "false")
        elif isinstance(value, dt.date):
            row.append(value.isoformat())
        elif isinstance(value, float):
            row.append(f"{value:.2f}")
        else:
            row.append(value)
    return row


def write_csv(folder, name, header, records):
    path = folder / name
    count = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for record in records:
            writer.writerow(as_row(record))
            count += 1
    print(f"  {name:<34} {count:>8,} rows")
    return count


def termination_reason(rng, employment_type):
    if employment_type == "Contract" and rng.random() < 0.50:
        return "End of Contract"
    return rng.choices(TERM_REASONS, TERM_WEIGHTS)[0]


def build(rng):
    if sum(band[1] for band in SIZE_BANDS) != 200:
        raise SystemExit("SIZE_BANDS must describe 200 organisations")
    if MONTHS[0] != WINDOW_START or MONTHS[-1] != LAST_SNAPSHOT or len(MONTHS) != 45:
        raise SystemExit("snapshot window must be January 2023 through September 2026")
    if month_end(LAST_SNAPSHOT) != WINDOW_END:
        raise SystemExit("WINDOW_END must be the last day of the last snapshot month")

    organisations = []
    departments = []
    org_depts = {}
    org_meta = {}
    department_id = 0
    org_id = 0
    for band, n_orgs, lo, hi in SIZE_BANDS:
        for _ in range(n_orgs):
            org_id += 1
            industry = rng.choice(INDUSTRIES)
            country = rng.choice(COUNTRIES)
            tier = rng.choices(*TIER_CHOICES[band])[0]
            name = f"{NAME_A[(org_id - 1) % len(NAME_A)]} {NAME_B[(org_id - 1) // len(NAME_A)]}"
            organisations.append((org_id, name, industry, band, country, tier))
            depts = []
            for group, dept_name in ALL_DEPTS[:DEPT_COUNT[band]]:
                department_id += 1
                depts.append(department_id)
                departments.append((department_id, org_id, dept_name, group, f"CC-{department_id:04d}"))
            org_depts[org_id] = depts
            org_meta[org_id] = {
                "country_factor": COUNTRY_FACTOR[country],
                "headcount": rng.randint(lo, hi),
            }
    largest_id = max(org_meta, key=lambda i: (org_meta[i]["headcount"], i))
    org_meta[largest_id]["headcount"] = 2000
    n_employees = sum(meta["headcount"] for meta in org_meta.values())
    if n_employees > EMPLOYEE_CAP:
        raise SystemExit(f"employee count {n_employees:,} is above the {EMPLOYEE_CAP:,} cap")

    employees = []
    org_employee_ids = defaultdict(list)
    employee_id = 0
    pre_window_days = (WINDOW_START - HIRE_EARLIEST).days
    during_days = (WINDOW_END - WINDOW_START).days
    for org_id, meta in org_meta.items():
        depts = org_depts[org_id]
        for _ in range(meta["headcount"]):
            employee_id += 1
            if rng.random() < 0.55:
                hire = HIRE_EARLIEST + dt.timedelta(days=rng.randint(0, pre_window_days - 1))
            else:
                hire = WINDOW_START + dt.timedelta(days=rng.randint(0, during_days))
            employment_type = rng.choices(EMPLOYMENT_TYPES, EMPLOYMENT_WEIGHTS)[0]
            term = None
            reason = None
            earliest_term = hire + dt.timedelta(days=30)
            if earliest_term <= WINDOW_END and rng.random() < 0.22:
                span = (WINDOW_END - earliest_term).days
                term = earliest_term + dt.timedelta(days=rng.randint(0, span))
                reason = termination_reason(rng, employment_type)
            level_idx = rng.choices(range(len(LEVELS)), LEVEL_WEIGHTS)[0]
            employees.append({
                "employee_id": employee_id,
                "org_id": org_id,
                "first_name": rng.choice(FIRST_NAMES),
                "last_name": rng.choice(LAST_NAMES),
                "start_department_id": rng.choice(depts),
                "start_level_idx": level_idx,
                "employment_type": employment_type,
                "hire_date": hire,
                "termination_date": term,
                "termination_reason": reason,
                "pay_percentile": rng.random(),
                "country_factor": meta["country_factor"],
            })
            org_employee_ids[org_id].append(employee_id)

    room = dt.timedelta(days=14)
    terminated = [
        e for e in employees
        if e["termination_date"] is not None and e["termination_date"] <= WINDOW_END - room
    ]
    if len(terminated) < N_BAD_DATES:
        raise SystemExit("not enough terminated employees to plant bad hire dates")
    for emp in rng.sample(terminated, N_BAD_DATES):
        earliest = emp["termination_date"] + room
        latest = min(WINDOW_END, emp["termination_date"] + dt.timedelta(days=75))
        emp["hire_date"] = earliest + dt.timedelta(days=rng.randint(0, (latest - earliest).days))

    snapshots = []
    for emp in employees:
        active = [month for month in MONTHS if employed_on(emp, month_end(month))]
        emp["active_months"] = active
        promo_month = None
        move_month = None
        move_department_id = None
        if emp["start_level_idx"] < len(LEVELS) - 1 and len(active) >= 12 and rng.random() < 0.28:
            promo_month = rng.choice(active[6:])
        others = [d for d in org_depts[emp["org_id"]] if d != emp["start_department_id"]]
        if others and len(active) >= 8 and rng.random() < 0.12:
            move_month = rng.choice(active[4:])
            move_department_id = rng.choice(others)
        last_dept = emp["start_department_id"]
        last_level = emp["start_level_idx"]
        active_set = set(active)
        for month in MONTHS:
            level = emp["start_level_idx"] + (1 if promo_month is not None and month >= promo_month else 0)
            dept = move_department_id if move_month is not None and month >= move_month else emp["start_department_id"]
            employed = month in active_set
            salary = annual_salary(emp, level, month) if employed else None
            if employed:
                last_dept = dept
                last_level = level
            snapshots.append([month, emp["employee_id"], emp["org_id"], employed, salary, LEVELS[level], dept])
        emp["department_id"] = last_dept
        emp["job_level"] = LEVELS[last_level]

    leaves = []
    reviews = []
    leave_id = 0
    review_id = 0
    for emp in employees:
        if not emp["active_months"]:
            continue
        others = [i for i in org_employee_ids[emp["org_id"]] if i != emp["employee_id"]] or [emp["employee_id"]]
        by_year = defaultdict(list)
        for month in emp["active_months"]:
            by_year[month.year].append(month)
        for year in sorted(by_year):
            months = by_year[year]
            total_annual = rng.randint(8, 16)
            parts = [total_annual]
            if total_annual >= 12 and len(months) > 1 and rng.random() < 0.55:
                first = rng.randint(5, total_annual - 4)
                parts = [first, total_annual - first]
            for days in parts:
                leave_id = _append_leave(leaves, leave_id, rng, emp, others, months, "Annual", days)
            if rng.random() < 0.70:
                leave_id = _append_leave(leaves, leave_id, rng, emp, others, months, "Sick", rng.randint(1, 3))
            if rng.random() < 0.25:
                leave_id = _append_leave(leaves, leave_id, rng, emp, others, months, "Sick", rng.randint(1, 2))
            if rng.random() < 0.12:
                leave_id = _append_leave(leaves, leave_id, rng, emp, others, months, "Other", rng.randint(1, 3))
            if rng.random() < 0.035:
                leave_id = _append_leave(leaves, leave_id, rng, emp, others, months, "Parental", rng.randint(20, 45))
            if year <= LAST_REVIEW_YEAR and emp["hire_date"] <= dt.date(year, 10, 1):
                review_id += 1
                rating = rng.choices([1, 2, 3, 4, 5], [5, 12, 40, 32, 11])[0]
                reviews.append((review_id, emp["employee_id"], emp["org_id"], year, rating, rng.choice(others)))

    _plant_salaries(rng, snapshots)

    employee_rows = [
        (
            e["employee_id"], e["org_id"], e["first_name"], e["last_name"], work_email(e),
            e["department_id"], e["job_level"], e["employment_type"], e["hire_date"],
            e["termination_date"], e["termination_reason"],
        )
        for e in employees
    ]
    return {
        "organisations.csv": (
            ["org_id", "org_name", "industry", "employee_count_band", "country", "subscription_tier"],
            organisations,
        ),
        "departments.csv": (
            ["department_id", "org_id", "department_name", "department_group", "cost_centre"],
            departments,
        ),
        "employees.csv": (
            ["employee_id", "org_id", "first_name", "last_name", "email", "department_id", "job_level",
             "employment_type", "hire_date", "termination_date", "termination_reason"],
            employee_rows,
        ),
        "employee_monthly_snapshots.csv": (
            ["snapshot_month", "employee_id", "org_id", "is_active", "base_salary_usd", "job_level", "department_id"],
            snapshots,
        ),
        "leave_records.csv": (
            ["leave_id", "employee_id", "org_id", "leave_type", "start_date", "end_date", "days_taken", "approved_by"],
            leaves,
        ),
        "performance_reviews.csv": (
            ["review_id", "employee_id", "org_id", "review_year", "rating", "reviewer_id"],
            reviews,
        ),
        "security_mapping.csv": (
            ["user_email", "org_id", "access_level"],
            SECURITY,
        ),
    }


def _weekday_count(start, end):
    return len(weekdays_between(start, end))


def _append_leave(leaves, leave_id, rng, emp, approvers, months, leave_type, n_days):
    placed = _place_leave(rng, emp, months, n_days)
    if not placed:
        return leave_id
    start, end = placed
    days = _weekday_count(start, end)
    leave_id += 1
    leaves.append((leave_id, emp["employee_id"], emp["org_id"], leave_type, start, end, days, rng.choice(approvers)))
    return leave_id


def _place_leave(rng, emp, months, n_days):
    month = rng.choice(months)
    last = month_end(month)
    first = month
    if emp["hire_date"] > first:
        first = emp["hire_date"]
    term = emp["termination_date"]
    if term is not None and term < last:
        last = term
    options = weekdays_between(first, last)
    if not options:
        return None
    start = rng.choice(options)
    end = add_weekdays(start, n_days)
    if term is not None and end > term:
        return None
    if end > WINDOW_END:
        return None
    return start, end


def _plant_salaries(rng, snapshots):
    december = dt.date(2025, 12, 1)
    december_rows = [i for i, row in enumerate(snapshots) if row[3] and row[0] == december]
    other_rows = [i for i, row in enumerate(snapshots) if row[3] and row[0] != december]
    if len(december_rows) < N_BAD_SALARIES_DECEMBER or len(other_rows) < N_BAD_SALARIES_OTHER:
        raise SystemExit("not enough active snapshot rows to plant bad salaries")
    chosen = rng.sample(december_rows, N_BAD_SALARIES_DECEMBER) + rng.sample(other_rows, N_BAD_SALARIES_OTHER)
    for n, index in enumerate(chosen):
        if n % 2 == 0:
            snapshots[index][4] = 0.0
        else:
            snapshots[index][4] = -float(rng.choice([250, 500, 1000, 2500]))


def _read(folder, name):
    with (folder / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _rows(folder, name):
    with (folder / name).open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def verify(folder, expected):
    orgs = _read(folder, "organisations.csv")
    depts = _read(folder, "departments.csv")
    employees = _read(folder, "employees.csv")
    reviews = _read(folder, "performance_reviews.csv")
    security = _read(folder, "security_mapping.csv")
    actual = {
        "organisations.csv": len(orgs),
        "departments.csv": len(depts),
        "employees.csv": len(employees),
        "performance_reviews.csv": len(reviews),
        "security_mapping.csv": len(security),
    }

    if len(orgs) != 200:
        raise SystemExit("expected 200 organisations")
    if len(employees) > EMPLOYEE_CAP:
        raise SystemExit(f"employee count {len(employees):,} is above the {EMPLOYEE_CAP:,} cap")

    dept_org = {row["department_id"]: row["org_id"] for row in depts}
    emp_org = {}
    per_org = defaultdict(int)
    seen_email = set()
    bad_dates = 0
    for row in employees:
        emp_org[row["employee_id"]] = row["org_id"]
        per_org[row["org_id"]] += 1
        if dept_org[row["department_id"]] != row["org_id"]:
            raise SystemExit(f"employee {row['employee_id']} department is in another org")
        term = row["termination_date"]
        reason = row["termination_reason"]
        if (term == "") != (reason == ""):
            raise SystemExit(f"employee {row['employee_id']} termination date and reason disagree")
        if row["hire_date"] > WINDOW_END.isoformat() or (term and term > WINDOW_END.isoformat()):
            raise SystemExit(f"employee {row['employee_id']} has a date after {WINDOW_END.isoformat()}")
        if term and row["hire_date"] > term:
            bad_dates += 1
        elif term and row["hire_date"] >= term:
            raise SystemExit(f"employee {row['employee_id']} hire date is not before termination")
        expected_email = (
            f"{row['first_name']}.{row['last_name']}.{row['employee_id']}"
            f"@org{row['org_id']}.cloudhr.com"
        ).lower()
        if row["email"] != expected_email:
            raise SystemExit(f"employee {row['employee_id']} email does not match the name and id")
        if row["email"] in seen_email:
            raise SystemExit(f"duplicate email {row['email']}")
        seen_email.add(row["email"])
    if bad_dates != N_BAD_DATES:
        raise SystemExit(f"expected {N_BAD_DATES} hire dates after termination, found {bad_dates}")

    band_of = {row["org_id"]: row["employee_count_band"] for row in orgs}
    by_band = defaultdict(list)
    for org_id, count in per_org.items():
        if count >= 10000:
            raise SystemExit(f"org {org_id} is loaded at {count} employees")
        by_band[band_of[org_id]].append(count)
    labels = [band[0] for band in SIZE_BANDS]
    averages = [sum(by_band[label]) / len(by_band[label]) for label in labels]
    band_sizes = {band[0]: band[1] for band in SIZE_BANDS}
    for label in labels:
        if len(by_band[label]) != band_sizes[label]:
            raise SystemExit(f"band {label} has {len(by_band[label])} orgs")
    if not all(averages[i] < averages[i + 1] for i in range(len(averages) - 1)):
        raise SystemExit(f"size bands do not increase: {averages}")

    months = set()
    per_employee = defaultdict(int)
    bad_salary = 0
    snapshot_count = 0
    for row in _rows(folder, "employee_monthly_snapshots.csv"):
        snapshot_count += 1
        months.add(row["snapshot_month"])
        per_employee[row["employee_id"]] += 1
        if row["org_id"] != emp_org[row["employee_id"]]:
            raise SystemExit(f"snapshot org does not match employee {row['employee_id']}")
        if dept_org[row["department_id"]] != row["org_id"]:
            raise SystemExit(f"snapshot department is outside org {row['org_id']}")
        if row["job_level"] not in LEVELS:
            raise SystemExit(f"unknown job level {row['job_level']}")
        salary = row["base_salary_usd"]
        if row["is_active"] == "true":
            if salary == "":
                raise SystemExit("active snapshot is missing a salary")
            if float(salary) <= 0:
                bad_salary += 1
        elif row["is_active"] == "false":
            if salary != "":
                raise SystemExit("inactive snapshot should not carry a salary")
        else:
            raise SystemExit(f"unexpected is_active value {row['is_active']!r}")
    actual["employee_monthly_snapshots.csv"] = snapshot_count
    if bad_salary != N_BAD_SALARIES_DECEMBER + N_BAD_SALARIES_OTHER:
        raise SystemExit(f"expected 32 non-positive salaries, found {bad_salary}")
    if months != {month.isoformat() for month in MONTHS}:
        raise SystemExit("snapshot months are not January 2023 through September 2026")
    if any(count != len(MONTHS) for count in per_employee.values()) or len(per_employee) != len(employees):
        raise SystemExit("each employee must have one snapshot row per month")

    seen_reviews = set()
    for row in reviews:
        if row["org_id"] != emp_org[row["employee_id"]]:
            raise SystemExit("review org does not match the employee")
        if row["reviewer_id"] not in emp_org:
            raise SystemExit("reviewer_id is not an employee")
        rating = int(row["rating"])
        review_year = int(row["review_year"])
        if rating < 1 or rating > 5:
            raise SystemExit("rating outside 1-5")
        if review_year < WINDOW_START.year or review_year > LAST_REVIEW_YEAR:
            raise SystemExit(f"review year {review_year} is outside 2023-{LAST_REVIEW_YEAR}")
        key = (row["employee_id"], row["review_year"])
        if key in seen_reviews:
            raise SystemExit("duplicate performance review")
        seen_reviews.add(key)

    leave_count = 0
    for row in _rows(folder, "leave_records.csv"):
        leave_count += 1
        if row["leave_type"] not in LEAVE_TYPES:
            raise SystemExit(f"unknown leave type {row['leave_type']}")
        if row["org_id"] != emp_org[row["employee_id"]]:
            raise SystemExit("leave org does not match the employee")
        if row["approved_by"] not in emp_org:
            raise SystemExit("approved_by is not an employee")
        start = dt.date.fromisoformat(row["start_date"])
        end = dt.date.fromisoformat(row["end_date"])
        if end > WINDOW_END or start > WINDOW_END:
            raise SystemExit(f"leave {row['leave_id']} extends past {WINDOW_END.isoformat()}")
        if _weekday_count(start, end) != int(row["days_taken"]):
            raise SystemExit(f"leave {row['leave_id']} days_taken does not match the dates")
    actual["leave_records.csv"] = leave_count
    for name, count in expected.items():
        if actual[name] != count:
            raise SystemExit(f"{name}: printed {count:,}, recounted {actual[name]:,}")

    security_rows = [(row["user_email"], row["org_id"], row["access_level"]) for row in security]
    expected_security = [(email, str(org_id), level) for email, org_id, level in SECURITY]
    if security_rows != expected_security:
        raise SystemExit("security_mapping does not match the three lab users")

    largest = max(per_org.values())
    smallest = min(per_org.values())
    if smallest != 50 or largest != 2000:
        raise SystemExit(f"expected loaded headcount from 50 to 2,000, found {smallest:,} to {largest:,}")
    band_text = ", ".join(
        f"{label} avg {averages[i]:.0f} ({len(by_band[label])} orgs)"
        for i, label in enumerate(labels)
    )
    print("  recounted row counts match")
    print(f"  loaded employees by band: {band_text}")
    print(f"  smallest organisation: {smallest:,} employees")
    print(f"  largest organisation: {largest:,} employees")
    print(f"  snapshots: {MONTHS[0].isoformat()} through {MONTHS[-1].isoformat()} ({len(MONTHS)} months)")
    print(f"  planted errors: {bad_dates} hire dates after termination, {bad_salary} non-positive salaries")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data")
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    print(f"Generating CloudHR data (seed {SEED}) into {out.resolve()}")
    tables = build(rng)
    expected = {}
    for name in list(tables):
        header, records = tables.pop(name)
        expected[name] = write_csv(out, name, header, records)
        del records
    verify(out, expected)
    print("Done.")


if __name__ == "__main__":
    main()
