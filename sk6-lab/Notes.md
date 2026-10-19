## Publishing plan

No Power BI Service account, so this plan is the Lab 06 deliverable. Publish, gateway setup, and role assignment in the Service are out of scope on this machine.

Workspaces `NorthStar-Dev`, `NorthStar-Test`, and `NorthStar-Prod` sit in one deployment pipeline. Parameter rules set `ServerName` per stage: `northstar-dev-db:5432`, `northstar-test-db:5432`, `northstar-prod-db:5432`. Pipelines need Premium Per User, Premium, or Fabric capacity.

A developer publishes to Dev, then deploys to Test. QA checks totals against the SQL control totals and re-runs Performance Analyzer. A team lead approves. Only two named people may deploy to Prod.

Refresh daily at 05:00, timeout 2 hours, failure email `data-team@northstar.com`, through gateway `NorthStar-PBI-Gateway`. This lab database is on `localhost:5434`, so the Service cannot reach it without that gateway.

Regional managers' group → `Regional Access`. Store managers' group → `Store Access`. Consumers get an app with Viewer rights. Workspace Admin, Member, and Contributor bypass RLS.

## Report pages

Executive Summary question: how is NorthStar doing this fiscal year, and where? Filters on top, four KPI cards, revenue trend plus region bars, top 10 products plus category donut. Fiscal Year slicer keeps 2024–2026 and defaults to 2026.

Regional Performance is a drill-through page on `dim_store[region_name]`. Keep all filters on, so Fiscal Year travels with the drill.

Mobile layout order: Fiscal Year slicer, four KPI cards, Revenue Trend, Revenue by Region.