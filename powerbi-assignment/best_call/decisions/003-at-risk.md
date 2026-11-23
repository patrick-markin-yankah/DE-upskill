# 003 — Who is at risk

**Status:** Accepted. The call is accurate and it misses almost everyone. This copy is the week-4 call. The original note is unchanged.

## Context

A Monday call has to be decided from attendance, participation, labs, and quizzes known by the end of that week. Graduation and certification are the ending. They are the scorecard for a rule, and they are not an input.

The candidates that were refused were run for every week from 1 to 10, on each track, using only what that week could have known. Those counts are in `data_findings.md`. Cloud has 7 non-graduates. Power BI has 14. Together that is 21.

Activity on this intake does not point at those 21. Power BI attendance to date is 1.000 for every learner in every week, so any rule that requires weak attendance flags nobody on that track. Cloud attendance does vary, and the learners who failed attended slightly more often than the learners who graduated, not less. No lab or quiz cell is blank, so a rule that waits for missing work never fires. Zeros are real scores.

She would rather a few right calls than a long noisy list. A wrong flag costs a trainer's afternoon.

## Decision

Two lists.

The first-call list starts in week 4. A learner is on it only when both parts hold: attendance to date is under **0.60**, and the work looks weak, a mean lab under **50** or a mean quiz under **50**. One of those is not enough. Weeks 1 to 3 are silent. A missing mean does not count as under 50. Two missed assessments do not, on their own, put a learner on the list. On this intake every cell holds a number, so that path would have added nobody anyway.

The watch list starts in week 1. It is the wider rule that used to be the call: attendance to date under **0.60**, or both the mean lab and the mean quiz under **50**. One mean under 50 is not enough. A learner with only one mean under 50, and attendance at 60% or above, is on neither list.

A blank score is missing. A score of 0 is submitted, and it counts in the mean. A single score below 30 this week does not, on its own, put a learner on either list.

The first-call list is every learner who meets both parts. It is not capped at 10. Anyone on the first-call list is also on the watch list, because attendance under 60% is already enough for the watch list. Someone with both means under 50 and attendance at 60% or above stays on the watch list and off the call.

Power BI attendance is 1.000, so the first-call list there is empty. The watch list there is the learners whose mean lab and mean quiz are both under 50.

The week to first act is week 4. Calling earlier, on this intake, spends afternoons on people who finish.

## Back-test

Each row uses only what that week could have known. Graduation is the scorecard afterward. "Did not graduate" is how many people on that week's first-call list failed in the end. "Missed" is how many of the 21 non-graduates were off that week's list. "Afternoons on graduates" is the rest of the list.

The combined-rule table in `data_findings.md` is this call. Two missed assessments never fire here, so leaving that path out of the rule does not change a count.

| Week | Calls | Of whom did not graduate | Missed of the 21 | Afternoons on graduates |
| --- | --- | --- | --- | --- |
| 1–3 | 0 | 0 | 21 | 0 |
| 4 | 1 | 1 | 20 | 0 |
| 5 | 1 | 1 | 20 | 0 |
| 6–10 | 0 | 0 | 21 | 0 |

Weeks 4 and 5 raise one Cloud learner, John Miller. He did not graduate. Those two calls land on nobody who finished. The other 20 non-graduates never appear. Power BI raises nobody, in any week.

The watch list is the previous call. In week 1 it holds 40 learners, 5 of whom did not graduate. Cloud is 12 of those 40, 4 of whom did not graduate. Power BI is 28, 1 of whom did not graduate. Its size through week 10 is 40, 38, 34, 34, 30, 29, 30, 29, 31, 28. It is not the Monday call.

## Why

The first-call list is the Monday call: from week 4, low attendance and a mean under 50. The watch list is low attendance, or both means under 50, from week 1. The call spends no afternoon on a graduate. It misses 20 of the 21.

## Rejected

- The previous call, used here as the watch list and not as the call: attendance under 0.60, or both means under 50, from week 1. Week 1 raises 40 learners, 5 of whom did not graduate, and 35 of the calls are graduates.
- The previous watch list: attendance under 0.60, or either mean under 50. Week 1 holds 102 learners. One mean under 50 is not enough to watch.
- Attendance to date under 0.60, with no score check. Cloud week 1 flags one graduate. Weeks 3 to 5 flag two learners, one of whom failed. From week 6 the list is empty. One Cloud non-graduate is ever caught, first in week 3. Power BI flags nobody.
- Attendance to date under 0.50. It catches none of the seven Cloud non-graduates. Power BI flags nobody.
- Attendance to date under 0.70. It catches three of the seven Cloud non-graduates, and it also flags graduates in those same weeks. Power BI flags nobody.
- Two or more missed labs or quizzes. It flags nobody, on either track, in any week. Every cell holds a number.
- A lab or quiz this week that sits 20 or more points below that learner's own earlier mean, once they have two earlier scores of that kind. This is the only candidate that eventually flags every non-graduate, with the first catch in weeks 3 to 6. The lists are too long. Power BI week 4 flags 60 learners, 12 of whom failed, which is a precision of 0.200. The highest precision in the table is Cloud week 8, 5 failures out of 17 calls, which is 0.294. Most of the people on these lists graduated.
- Any rule that reads graduation, certification, or a later week. The ending is how the list is judged after the intake is over. It cannot decide the call.
- Treating this intake as if a tighter activity rule were hiding in the same columns. The back-test does not show one.
