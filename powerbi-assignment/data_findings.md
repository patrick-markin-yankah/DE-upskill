# Data findings

The trainer folders reconcile. Every learner and every class day is present on every feed. The danger to Abena's Monday call is that this clean activity does not point at the learners who failed to graduate. A flag built from attendance, missed work, or a week-to-week score drop is weak on this intake. The rule itself stays open until the back-test decision.

The script is `scripts/diagnose_exports.py`. It is not part of the report refresh. Counts below are what the load has to match.

## Control totals

| Total | Cloud | Power BI | Both tracks |
| --- | --- | --- | --- |
| Learners | 40 | 100 | 140 |
| Class days | 50 | 50 | 50 calendar dates, 100 track-days |
| Zoom session rows, before any day rollup | 2,000 | 5,000 | 7,000 |
| Learner-days with more than one Zoom row | 0 | 0 | 0 |
| Lab rows after unpivot, including blanks | 400 | 1,000 | 1,400 |
| Quiz rows after unpivot, including blanks | 400 | 1,000 | 1,400 |
| Status rows | 40 | 100 | 140 |
| Unmatched participation names | 0 | 0 | 0 |

Cloud is one Zoom row per learner per class day (40 × 50). Power BI is the same (100 × 50). Labs and quizzes are one cell per learner per week (40 × 10 and 100 × 10). None of those cells are blank.

Endings, stored as recorded: Cloud 33 graduates and 7 non-graduates, of whom 24 are certified. Power BI 86 graduates and 14 non-graduates, of whom 68 are certified. Across both tracks that is 21 non-graduates and 27 graduates who were not certified. No row is certified without being a graduate.

## Every learner

The learner list is the union of emails on attendance, labs, quizzes, and status.

- Cloud: the same 40 emails on all four feeds. No duplicate status email. No email with two display names.
- Power BI: the same 100 emails on all four feeds. No duplicate status email. No email with two display names.
- No email appears on both tracks.

Participation is names only. Folded the same way as the planned name key (lower case, letters and spaces only), every name matches exactly one learner inside its own track. Cloud has 1,784 participation name-rows and Power BI has 4,253. None are unmatched, and none match more than one learner. The same cleaned name is not shared across the two tracks.

## Every class day

Both tracks run Monday 5 August 2024 through Friday 11 October 2024. That span is 50 weekdays. Each weekday has one attendance file and one participation date. There is no weekend file and no weekday gap.

The `Week N` folder matches the program week counted from 5 August. A file is never in the wrong week. Week 9 contains 30 September and 1–4 October because that program week crosses the month. The month boundary is not a misfile.

No learner-day has a second Zoom row, so adding minutes within a day does not change any attendance result on this intake. The add-the-minutes rule can stay in place for a later export. It has no effect here.

## What would move a Monday call

### 1. Activity does not separate the learners who failed to graduate

This is the finding that changes the call list. The other files can be loaded cleanly, and the flag will still be weak if it treats absence or a missed submission as the sign of dropping out.

Power BI sessions are all between 90 and 120 minutes. Every learner, graduate or not, is over 30 minutes on every class day, so the attendance rate is 1.000 in every week. Non-graduates also participated slightly more often than graduates (87.9% of learner-days against 84.6%). Their mean lab is 49.4 against 49.8 for graduates. Their mean quiz is 54.4 against 50.5, so the learners who failed scored a little higher, not lower. There are no blank labs or quizzes, so a rule that waits for two missed submissions never fires. An attendance threshold of 0.50, 0.60, or 0.70 flags nobody on this track, in any week. The combined rule (from week 4, attendance under 0.60, and a weak or missing assessment) also flags nobody. All 14 Power BI non-graduates are missed.

Cloud does have short sessions: 396 under 30 minutes, and 19 of exactly 30. The attendance rate by week sits between 0.755 and 0.865. That variation still points the wrong way. Non-graduates attended 80.9% of learner-days and graduates 78.9%. Non-graduates participated on 90.0% of days and graduates on 89.0%. Mean lab is 48.4 against 51.5, and mean quiz is 51.3 against 53.1. An attendance line at 0.60 flags at most two people and catches one of the seven non-graduates, and only in some weeks. A line at 0.50 catches none. The combined rule flags one learner in weeks 4 and 5, that learner did not graduate, and the other six non-graduates are missed.

A drop of 20 or more points against the learner's own earlier scores does eventually touch every non-graduate, and the first catch is usually week 3 or 4. It also flags about half the room. On Power BI in week 4 it raises 60 learners, 12 of whom did not graduate, and the precision is 0.200. On Cloud the same week raises 16 learners, 4 of whom did not graduate. That is the long noisy list the call budget cannot carry.

Effect on the flag: attendance, participation, and missed submissions are the wrong signs on this intake. A score-drop sign catches the non-graduates only by also flagging a large number of graduates. Stage 5 has to say so if no tighter rule appears. These comparisons use the ending as the test. They are not themselves a flag.

### 2. The two duration shapes will move attendance if they are read as one kind of cell

Power BI writes duration as clock text such as `1:46:00`. Cloud writes a whole number of minutes such as `66`, ranging from 5 to 117. Both shapes parsed. Neither track has an unreadable duration.

Left as recorded. The load has to decide from the value: a number is already minutes, and clock text converts to minutes. Reading Cloud's numbers as clock text, or Power BI's clock text as a raw number, would mark the wrong people present and would move every attendance rate and any attendance flag. The files do not need to be edited.

The 19 Cloud sessions of exactly 30 minutes are absent under the rule that attendance requires more than 30. They are a boundary, not a broken cell. Counting them as present would slightly raise Cloud attendance and would still not point at the non-graduates.

## Left as recorded

- Workbook names differ, including `Status of Participanat.xlsx` and `Labs & Quizes`. The feed comes from the folder, so the spelling does not change a rate or a flag.
- Score zeros are real scores: 4 Cloud labs, 2 Cloud quizzes, 13 Power BI labs, 11 Power BI quizzes. No score is blank, and none fall outside 0–100. Turning a zero into a missing submission would invent missed work.
- Graduates who are not certified (9 on Cloud, 18 on Power BI) match the meaning that certification is a graduate who also passed the external exam. No certified learner is a non-graduate. The status text is only `Graduate`, `Non Graduate`, `Certified`, and `Not Certified`.
- Every Zoom role is `Participant`. There is no host row to drop.
- Week folders that cross a calendar month match the program week. They are not misfiles.
- No class day has a median short enough to be a broken session if the cutoff is 45 minutes. The shortest Cloud day median is 46 minutes, on 20 August. Power BI day medians sit between 103.5 and 108. A cutoff of 60 minutes would mark 17 ordinary Cloud days and no Power BI day, so it would describe Cloud's usual length rather than a bad class.

## Week rates for the later cutoffs

Attendance rate here is attended learner-days divided by learners times class days. The gap is that week minus the average of the track's other weeks. Mean quiz is the mean of submitted scores.

Cloud attendance never sits 15 points below the other weeks. The widest quiz gap is week 5, 11.1 points below the other weeks (mean quiz 42.7). A quiz gap of about 10 points would mark that week and no other. Power BI attendance does not vary. Its quiz gaps stay inside about 5 points, so the same 10-point gap marks no Power BI week.

## Candidate flags

These tables are a back-test of possible Monday call lists. Each week's row uses only what Dare Careers would have known by the end of that week. Graduation is the scorecard afterward: whether the people on that week's list failed to graduate. It is not an input to the rule.

Flagged is the size of that week's call list. Of whom failed is how many of those people ended as non-graduates. Precision is that second number divided by the first. A precision of 0.200 means one in five calls would have been a real failure. A blank precision means the list was empty, so there is nothing to divide. Missed is how many non-graduates were off that week's list. Cloud has 7 non-graduates and Power BI has 14, so a missed count of 7 or 14 means the rule called none of them that week.

The catch line is separate from the weekly missed count. Of the non-graduates a rule ever flags, it is the first week each one appeared. A non-graduate the rule never flags has no catch week.

Full sensitivity for attendance at 0.50 and 0.70 is in the script output. On Power BI those lines flag nobody, because attendance to date stays at 1.000. On Cloud, 0.50 catches none of the seven non-graduates. A line at 0.70 catches three of them, and it also flags several graduates in the same weeks.

### Combined rule

The rule stays silent through week 3. From week 4 it calls a learner only when both parts hold: attendance to date is under 0.60, and the work looks weak (a mean lab under 50, or a mean quiz under 50, or at least two missed assessments).

| Week | Cloud flagged | Of whom failed | Cloud missed | Power BI flagged | Of whom failed | Power BI missed |
| --- | --- | --- | --- | --- | --- | --- |
| 1–3 | 0 | 0 | 7 | 0 | 0 | 14 |
| 4 | 1 | 1 | 6 | 0 | 0 | 14 |
| 5 | 1 | 1 | 6 | 0 | 0 | 14 |
| 6–10 | 0 | 0 | 7 | 0 | 0 | 14 |

On Cloud the list is one person in weeks 4 and 5, and that person did not graduate, so those two calls are accurate. Their first catch is week 4. In weeks 6–10 they leave the list and the missed count returns to 7. Across the intake the other six Cloud non-graduates are never flagged. On Power BI the rule flags nobody, so all 14 non-graduates are missed every week. Attendance on that track is 1.000, so the attendance half of the rule never holds.

### Attendance to date under 0.60

This is the attendance half of the combined rule, with no score requirement and no wait until week 4.

| Week | Cloud flagged | Of whom failed | Precision | Power BI flagged |
| --- | --- | --- | --- | --- |
| 1 | 1 | 0 | 0.000 | 0 |
| 2 | 0 | 0 |  | 0 |
| 3–5 | 2 | 1 | 0.500 | 0 |
| 6–10 | 0 | 0 |  | 0 |

Cloud's list is small and it does not stay on the same people. Week 1 flags one graduate, so precision is 0. Weeks 3–5 flag two learners, one of whom failed, so precision is 0.500. From week 6 the list is empty. One Cloud non-graduate is ever caught, first in week 3. Power BI flags nobody, because every learner's attendance to date stays at 1.000.

### Two or more missed labs or quizzes

A miss is a blank score. Every lab and quiz cell on both tracks holds a number, including the zeros, which are real scores. The rule flags nobody in any week, on either track.

### Score 20 or more points below the learner's own earlier mean

This week's lab is compared with that learner's own earlier lab mean, and this week's quiz with their earlier quiz mean. A score under 50 fires the rule only when it sits at least 20 points below that earlier mean. The comparison needs two earlier scores of the same kind, so weeks 1 and 2 do not fire.

| Week | Cloud flagged | Of whom failed | Precision | Power BI flagged | Of whom failed | Precision |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | 17 | 1 | 0.059 | 50 | 6 | 0.120 |
| 4 | 16 | 4 | 0.250 | 60 | 12 | 0.200 |
| 5 | 23 | 4 | 0.174 | 50 | 8 | 0.160 |
| 6 | 23 | 4 | 0.174 | 52 | 9 | 0.173 |
| 7 | 21 | 6 | 0.286 | 52 | 7 | 0.135 |
| 8 | 17 | 5 | 0.294 | 48 | 2 | 0.042 |
| 9 | 23 | 2 | 0.087 | 48 | 6 | 0.125 |
| 10 | 24 | 5 | 0.208 | 54 | 7 | 0.130 |

This is the only rule that eventually flags every non-graduate. The first catch for each of them falls in weeks 3 to 6. The lists are large. Cloud week 3 flags 17 learners and 1 of them failed (precision 0.059). Power BI week 4 flags 60 learners and 12 of them failed (precision 0.200). The highest precision in the table is Cloud week 8: 5 failures out of 17 calls, which is 0.294. Most of the people on these lists graduated.
