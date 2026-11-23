# 003 — Who is at risk

**Status:** Accepted. The flag is weak on this intake.

## Context

A Monday call has to be decided from attendance, participation, labs, and quizzes known by the end of that week. Graduation and certification are the ending. They are the scorecard for a rule, and they are not an input.

The candidates that were refused were run for every week from 1 to 10, on each track, using only what that week could have known. Those counts are in `data_findings.md`. The back-test of the list below is in this note. Cloud has 7 non-graduates. Power BI has 14. Together that is 21.

Activity on this intake does not point at those 21. Power BI attendance to date is 1.000 for every learner in every week, so any rule that requires weak attendance flags nobody on that track. Cloud attendance does vary, and the learners who failed attended slightly more often than the learners who graduated, not less. No lab or quiz cell is blank, so a rule that waits for missing work never fires. Zeros are real scores.

## Decision

Two lists, from week 1.

The first-call list is every learner with attendance to date under **0.60**, or with both the mean lab and the mean quiz under **50**. One mean under 50 is not enough. A missing mean does not count as under 50. They leave a later week when attendance is no longer under 60% and at least one mean is 50 or above.

The watch list is wider. A learner is on it for attendance under **0.60**, or for a mean lab under **50**, or for a mean quiz under **50**.

A blank score is missing. A score of 0 is submitted, and it counts in the mean. Two missing assessments do not, on their own, put a learner on either list. A single score below 30 this week does not, on its own, put a learner on either list.

The first-call list is every candidate. It is not capped at 10. Severity still orders the list: missed assessments, then the thinnest attendance. A tied severity is broken by email. Anyone on the first-call list is also on the watch list. A learner with only one mean under 50, and attendance at 60% or above, stays on the watch list and off the first-call list.

Power BI attendance is 1.000, so the first-call list there is the learners whose mean lab and mean quiz are both under 50. The watch list there is anyone with either mean under 50.

The week to first act is week 1. Waiting does not make the list more accurate.

## Back-test

Each row uses only what that week could have known. Graduation is the scorecard afterward. "Did not graduate" is how many people on that week's first-call list failed in the end. "Missed" is how many of the 21 non-graduates were off that week's list. "Afternoons on graduates" is the rest of the list: a call on someone who finished.

| Week | Calls | Of whom did not graduate | Missed of the 21 | Afternoons on graduates |
| --- | --- | --- | --- | --- |
| 1 | 40 | 5 | 16 | 35 |
| 2 | 38 | 7 | 14 | 31 |
| 3 | 34 | 4 | 17 | 30 |
| 4 | 34 | 5 | 16 | 29 |
| 5 | 30 | 5 | 16 | 25 |
| 6 | 29 | 3 | 18 | 26 |
| 7 | 30 | 3 | 18 | 27 |
| 8 | 29 | 3 | 18 | 26 |
| 9 | 31 | 2 | 19 | 29 |
| 10 | 28 | 3 | 18 | 25 |

Week 1, the week to first act, raises **40** learners. **5** of them did not graduate. **16** of the 21 non-graduates are missed. The other 35 calls are graduates. That is 35 trainer afternoons in one week on people who finished. She asked for 10 right flags rather than 40 noisy ones. Week 1 is the noisy shape: 5 right, 35 wrong.

By track in week 1: Cloud raises 12, 4 of whom did not graduate, so 3 of its 7 non-graduates are missed. Power BI raises 28, 1 of whom did not graduate, so 13 of its 14 non-graduates are missed. In week 1 the watch list holds 102 learners. That is most of the room, and it is not the call.

Week 2 catches the most failures, 7 of 38 calls, and still misses 14 of the 21. From week 6 the list catches 3 or fewer of the 21.

Across all ten weeks, 13 of the 21 appear at least once. 8 never do. Three of those eight are on Cloud and five are on Power BI: Anthony Mitchell, Emily Davis, and Matthew Nelson on Cloud; Abigail Brooks, Liam Brown, Lucy Nguyen, Olivia Martin, and Samantha Chavez on Power BI.

## Why

The first-call list is the Monday call: low attendance, or a mean lab under 50 and a mean quiz under 50. The watch list is low attendance, or either mean under 50. Shape on the lists is Attendance, Assessment, or Both.

The cost of being wrong is a trainer's afternoon. On this intake that cost is most of the list. The flag is a list of who looks thin this week. It is not a list of who will fail.

## Rejected

- Both parts together, and only from week 4: attendance under 0.60 and a weak assessment (mean lab under 50, or mean quiz under 50, or two missed assessments). At week 4 that list was one Cloud learner, John Miller, who did not graduate. The other 20 non-graduates were missed. Week 5 was the same person. From week 6 that list was empty. It is accurate and it misses almost everyone, including all 14 on Power BI, because attendance there never falls under 0.60.

- Attendance to date under 0.60, with no score check and no wait until week 4. Cloud week 1 flags one graduate. Weeks 3 to 5 flag two learners, one of whom failed. From week 6 the list is empty. One Cloud non-graduate is ever caught, first in week 3. Power BI flags nobody.
- Attendance to date under 0.50. It catches none of the seven Cloud non-graduates. Power BI flags nobody.
- Attendance to date under 0.70. It catches three of the seven Cloud non-graduates, and it also flags graduates in those same weeks. Power BI flags nobody.
- Two or more missed labs or quizzes. It flags nobody, on either track, in any week. Every cell holds a number.
- A lab or quiz this week that sits 20 or more points below that learner's own earlier mean, once they have two earlier scores of that kind. This is the only candidate that eventually flags every non-graduate, with the first catch in weeks 3 to 6. The lists are too long. Power BI week 4 flags 60 learners, 12 of whom failed, which is a precision of 0.200. The highest precision in the table is Cloud week 8, 5 failures out of 17 calls, which is 0.294. Most of the people on these lists graduated.
- Any rule that reads graduation, certification, or a later week. The ending is how the list is judged after the intake is over. It cannot decide the call.
- Treating this intake as if a tighter activity rule were hiding in the same columns. The back-test does not show one.
