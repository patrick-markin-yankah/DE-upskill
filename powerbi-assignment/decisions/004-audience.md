# 004 — Who may see what

**Status:** Accepted. This is the improvement beyond the brief.

## Context

One report is opened by three audiences. The Program Director needs every intake and every track. A trainer should land on the intake and track they own, and not see the other track's call list. A learner should see their own row, and the median of their own track, which has no classmate's name.

Trainer and director assignments are not in the exports. The Zoom `Role` column is the session role, host or participant, and it is not used here. Students are not listed. Their sign-in is their email.

## Decision

The assignments live in `security/security_users.xlsx`, beside the report, not in the trainer folders. A new intake or a new trainer is a new row. The cohort key and the track key are the strings the model stores: `Module 7 Data`, `Cloud`, and `PowerBI`.

| UserEmail | Role | CohortKey | TrackKey |
| --- | --- | --- | --- |
| `abena.osei@darecareers.test` | Director | | |
| `trainer.powerbi@darecareers.test` | Trainer | `Module 7 Data` | `PowerBI` |
| `trainer.cloud@darecareers.test` | Trainer | `Module 7 Data` | `Cloud` |

The table is hidden and has no relationships. The path is the `SecurityPath` parameter.

Three roles:

- **Director** has no filter. That sign-in sees every intake and every track.
- **Trainer** keeps a learner, an intake, or a track only when the sign-in has a Trainer row for that cohort key and that track key. A trainer of this intake does not see a later intake until a row is added for it.
- **Student** keeps the learner whose email is the sign-in, and the intake and track on that row. No student is on the assignment list.

Someone with no assignment and no matching email sees no learners. A published workspace has to give these people viewer access. Edit rights bypass the filters. This brief is graded in Desktop, so View as is the proof. Test one role at a time.

The weekly summary stays hidden, with no learner names and no relationship. A student measure reads it from the cohort and track still in context, so the student sees their own track's median and cannot list classmates.

## What each sign-in keeps

These are the learners the filters keep on this intake. Cloud is 40. Power BI is 100. Together that is 140. `emilyjohnson@example.com` is one Power BI learner. `james.williams@msc.com` is one Cloud learner. Neither address is on the assignment list.

| View as | Other user | Learners |
| --- | --- | --- |
| Director | leave blank | 140, both tracks |
| Trainer | `trainer.powerbi@darecareers.test` | 100, Power BI only |
| Trainer | `trainer.cloud@darecareers.test` | 40, Cloud only |
| Student | `emilyjohnson@example.com` | 1. Monday shows her row only when she is flagged |
| Student | `james.williams@msc.com` | 1 |
| Student | `nobody@darecareers.test` | 0 |
| Trainer | `nobody@darecareers.test` | 0 |

## Why

Abena asked for one report the team can refresh. The same file also has to keep a learner off someone else's call list, and put a trainer on their own track on Monday morning. Putting the assignments in the exports would mix a staffing list into a grade file, and it would have to be rewritten when a trainer changes. A row beside the report does not.
