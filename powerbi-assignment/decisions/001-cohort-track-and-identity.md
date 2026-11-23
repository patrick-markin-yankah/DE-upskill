# 001 — Cohort, track, and identity

**Status:** Accepted. The at-risk rule is not part of this note.

## Context

The exports have no learner id, no cohort column, and no roster. Cohort and track exist only as folders. Most files use an email. Participation uses a display name. The two tracks write Zoom duration differently: Power BI uses clock text such as `1:46:00`, and Cloud uses a whole number of minutes such as `66`.

The exports account for every learner and every class day. Cloud has the same 40 emails on attendance, labs, quizzes, and status. Power BI has the same 100. No email is on both tracks. No cleaned participation name failed to match, and none matched more than one learner. No learner-day has more than one Zoom row. Nineteen Cloud sessions are exactly 30 minutes. A session of exactly 30 minutes is not attended.

## Decision

**Cohort.** The cohort key is the parent folder of the track folder. On this shipment the key is `Module 7 Data`. The label is the earliest class date in that cohort, formatted `MMM yyyy`, which is `Aug 2024`. A second intake folder beside this one gets its own key from its own folder name, and its own label from its own earliest class date. Two intakes that start in the same month keep different keys.

**Track.** The track key is the track folder name with the suffix ` Training` removed. This shipment has `Cloud` and `PowerBI`. `PowerBI` is shown as `Power BI`. Any other folder that ends in ` Training`, including a later `Data Engineering Training`, keeps whatever remains after the suffix is removed. Queries do not branch on the track name.

**Learner.** The learner key is the email, trimmed and lower-cased. The learner list is the union of emails on attendance, labs, quizzes, and status. One email that appears with two cohort keys or two track keys is written to the exception list and is not merged into one learner. This intake has no such email.

**Participation.** A participation name is matched inside the same cohort and track. The match key is the display name in lower case, with characters other than letters and spaces removed, and with repeated spaces collapsed. A name that matches one learner is kept. A name that matches none, or more than one, is an exception and does not become a new learner.

**Duration.** A numeric duration is already minutes. Clock text such as `h:mm:ss` is converted to minutes. The track name is not an input to that choice.

**Attendance day.** A class day is attended when the learner's minutes on that date sum to more than 30. The loaded attendance row is one row per learner per class date. This intake has no day with two Zoom rows, so the sum equals the single session. The sum stays the rule, because a later file may contain a rejoin. Exactly 30 minutes is not attended. The 19 Cloud sessions on that boundary stay absent.

## Why

The folder is the only place cohort and track are known, and the brief requires them to be derived. A typed label such as "Autumn 2024" would have to be edited when the next intake arrives. The email is the only identifier shared by attendance, assessments, and status, and on this intake it is already unique. The name key is safe here: 1,784 Cloud participation rows and 4,253 Power BI rows each matched one learner. Keeping unmatched names off the learner list stops a typo from becoming a person who then looks absent from every other feed.

Reading duration from the value, rather than from the track, is what keeps the 30-minute rule intact. Treating Cloud's `66` as clock text, or Power BI's `1:46:00` as a raw number, would mark the wrong people present.

Summing a day that currently has only one row changes nothing in the control totals. Dropping a second row as a broken export would be a guess this intake does not support, and it would be the wrong guess if the second row is a rejoin.

## Rejected

- Typing the cohort name, or using the file name to decide which feed a workbook is.
- Building the learner list from participation names.
- Matching a participation name by comparing it with the text before `@` in the email.
- Collapsing an email that appears on two tracks into one learner.
- Treating a second Zoom row on the same day as a corrupt duplicate and discarding it.
- Counting a session of exactly 30 minutes as attended.
