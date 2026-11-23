# CloudHR deployment guide

This is the release plan. The report is not published. There is no Power BI Service account on this machine.

The semantic model uses Import. `ServerName` and `DatabaseName` are Power Query parameters. `DatabaseName` stays `cloudhr` in every stage. Deployment rules change `ServerName` only.

A deployment pipeline needs Premium Per User, Premium, or Fabric capacity.

## Workspaces

One pipeline holds three workspaces.

| Workspace | Who | Workspace role |
|---|---|---|
| `CloudHR-Dev` | Developers | Member. They publish the `.pbix` here. |
| `CloudHR-Dev` | Two named release owners | Admin |
| `CloudHR-Test` | QA | Member. Members see every organisation, so QA can match the SQL control totals. |
| `CloudHR-Test` | Two named release owners | Admin |
| `CloudHR-Prod` | Two named release owners | Admin. These are the only accounts that deploy to production. |

Client HR users are not members of any workspace. They receive the production app as Viewers. `Tenant Access` applies to Viewers and to app consumers. Workspace Admin, Member, and Contributor bypass the role, which is why QA can see the whole database and why a client account is never given a workspace role.

## Pipeline

1. A developer publishes `pbix/CloudHR.pbix` to `CloudHR-Dev`.
2. Deploy from Dev to Test.
3. QA checks Test against `docs/data_model.md`. For 2025, with no organisation selected, December active headcount is 35,882, Q1 active headcount is 33,264, hires are 5,730, terminations are 2,100, average base salary is $102,809.64, and leave days are 574,024. Performance Analyzer on the four main pages shows 0 ms direct query, every visual under 800 ms of DAX query time, and at least 80% under 400 ms.
4. A team lead approves the Test stage in the pipeline.
5. One of the two release owners deploys from Test to Prod.

Parameter rules set `ServerName` on each stage:

| Stage | `ServerName` |
|---|---|
| Dev | `cloudhr-dev-db:5432` |
| Test | `cloudhr-test-db:5432` |
| Prod | `cloudhr-prod-db:5432` |

The laptop container on `localhost:5435` is the Desktop source only. It is not a pipeline stage.

## Refresh

The production semantic model refreshes weekly, Sunday at 02:00, with a timeout of 2 hours. Test uses the same schedule so the approval check is against current data.

Refresh runs through the on-premises data gateway `CloudHR-PBI-Gateway`. The Power BI Service cannot reach the Postgres host on its own. The gateway holds the database credentials for each `ServerName`. A failed refresh sends mail to `data-team@cloudhr.com`.

## Onboarding client 201

Adding the 201st organisation is a data change. It uses the existing app, the existing role, and the existing report. End to end it takes hours, within one working day once the source files are ready. The Sunday refresh allows up to 2 hours. It does not start a new project.

Production reads `security.security_users`, a view over active employees. Later clients are rows in `hr.employees` and the monthly snapshots. There is no separate access list to maintain.

1. Load the new organisation, departments, employees, monthly snapshots, leave, and reviews into the production database. The new `org_id` is 201. Each employee email is `first.last.{employee_id}@org201.cloudhr.com`.
2. Refresh the production semantic model. Active employees are already in the view.
3. Give those users the production app as Viewers.

They open the same app. M1 and above see only organisation 201. Everyone else sees their department inside organisation 201. Removing a user is setting `termination_date`, or marking the September 2026 snapshot inactive, and refreshing, as `docs/rls_administration.md` describes.
