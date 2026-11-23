# CloudHR RLS administration

One role, `Tenant Access`, reads `security_users`. That table is hidden and related to nothing. A work email is `first.last.{employee_id}@org{org_id}.cloudhr.com`. Daniel Davis, employee 1, organisation 1, is `daniel.davis.1@org1.cloudhr.com`. The other Daniel Davis in that organisation is `daniel.davis.49@org1.cloudhr.com`.

`security_users` is the view `security.security_users`. A row is present when `termination_date` is null and the September 2026 snapshot is active. That is the same set as `dim_employee`: 37,051 people. Someone who has left, or an email that is not in the view, matches nothing and every visual is blank.

M1, M2, and M3 (`level_sort` >= 5) see every department in their own organisation. IC1 through IC4 see only the department on their current employee row. The role does not filter `dim_job_level`, so an IC2 still sees every job level inside that department.

The organisation filter sits on `dim_organisation` and reaches every fact. The department filter sits on `dim_department` and reaches `fact_employee_monthly`. `fact_leave` and `fact_review` have no `department_id`, so Leave & Attendance and performance ratings stay at organisation scope for every active employee.

```dax
// dim_organisation. A missing email returns blank, so no organisation qualifies.
[org_id] =
LOOKUPVALUE(
    security_users[org_id],
    security_users[email],
    USERPRINCIPALNAME()
)
```

```dax
// dim_department. M1 and above see the whole organisation. Everyone else sees one department.
VAR Email = USERPRINCIPALNAME()
VAR OrgId =
    LOOKUPVALUE(security_users[org_id], security_users[email], Email)
VAR DeptId =
    LOOKUPVALUE(security_users[department_id], security_users[email], Email)
VAR LevelSort =
    LOOKUPVALUE(security_users[level_sort], security_users[email], Email)
RETURN
    dim_department[org_id] = OrgId
        && (
            LevelSort >= 5
            || dim_department[department_id] = DeptId
        )
```

View as, Year = 2025, other slicers cleared, role `Tenant Access` only. Headcount is the December 2025 snapshot.

| User | Scope | Active Headcount | Avg Base Salary |
|---|---|---:|---:|
| `daniel.davis.1@org1.cloudhr.com` | IC2, People, Apex Analytics | 11 | department only |
| `rita.mensah.16@org1.cloudhr.com` | M3, all of Apex Analytics | 38 | $92,754.01 |
| `efua.williams.51@org2.cloudhr.com` | IC3, Operations, Brightline Analytics | 13 | department only |
| `akosua.addo.55@org2.cloudhr.com` | M2, all of Brightline Analytics | 32 | $81,569.51 |
| `james.addo.2@org1.cloudhr.com` | M2, Apex Analytics, terminated 2026-01-26 | blank | blank |
| `intruder@cloudhr.com` | none | blank | blank |

The two company salaries are the December 2025 cards for the whole organisation. An IC's salary card is that department only, and it must not equal the company card.

## Add a person

Hire them in `hr.employees` with a unique email of this form, and give them an active September 2026 snapshot. The view picks them up. Refresh the model. Do not add a relationship and do not add a role.

## Remove a person

Set `termination_date`, or mark the September 2026 snapshot inactive. The next refresh drops the email from `security_users`. View as then shows the same blank page as `intruder@cloudhr.com`.

## Test after a change

On Executive Workforce Summary, set Year to 2025 and clear the other slicers. **Modeling → View as → Other user**, with only `Tenant Access` selected.

1. An IC email shows that department's December headcount, and no other department or organisation.
2. An M1, M2, or M3 email in the same organisation shows the organisation headcount.
3. An email from another organisation shows that organisation only.
4. An email that is not in `security_users` shows a blank page.

Stop viewing before editing further.

## A user reports seeing another company

Confirm they open the report as a Viewer or as an app consumer. Workspace Admin, Member, and Contributor bypass the role and see every organisation. Then confirm the email has one row in `security.security_users` and that `org_id` is theirs. Two rows for one email cannot be loaded: `hr.employees.email` is unique. A wrong `org_id` on the employee row shows the other company. An IC who sees another department is signed in at M1 or above, or the department on the employee row is wrong.
