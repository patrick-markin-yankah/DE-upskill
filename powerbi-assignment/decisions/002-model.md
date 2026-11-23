# 002 — Model, as-of week, and the two cutoffs

**Status:** Accepted. The at-risk rule is decided in `003-at-risk.md`, after the back-test.

## Context

The report has to slice by intake, track, and week without an accidental join, and the Monday view has to move back to any earlier week of this finished intake. Graduation and certification are known only at the end. The week rates show no attendance week that collapsed, one Cloud quiz week that sits well below the others, and no class day whose median length looks like a broken session. The shortest class-day median is 46 minutes, on Cloud, 20 August 2024. Power BI class-day medians sit between 103.5 and 108 minutes.

## Decision

### Grain

| Table | Grain |
| --- | --- |
| `DimLearner` | One email in one cohort and one track. Display name and name key. No outcome columns. |
| `DimCohort` | One intake folder. Key, plus the derived label. |
| `DimTrack` | One track key, plus the display name. |
| `DimDate` | One calendar date. This is the date table. |
| `DimWeek` | One program week inside one cohort. `WeekKey` is the cohort key, a bar, and the week number. |
| `AsOfWeek` | One week number. No relationship to any other table. |
| `ClassDay` | One class date in one cohort and track. Holds the day's median minutes and `ShortClass`. |
| `FactAttendance` | One learner on one class date. Minutes are the sum for that day. `Attended` is that sum greater than 30. |
| `FactParticipation` | One matched learner on one class date. |
| `FactAssessment` | One learner, one program week, and one assessment type, Lab or Quiz. A blank score stays blank. A zero stays zero. |
| `FactOutcome` | One learner. Graduation and certification as recorded. |
| `FactException` | One unmatched or unreadable event. Hidden. |
| `TrackWeek` | One cohort, one track, one week. Median attendance and the median submitted lab and quiz. No learner names. Hidden. No relationships. |
| `SecurityUsers` | One director or trainer assignment. Hidden. No relationships. Loaded from the access list kept beside the trainer folders. |

Raw Zoom rows stay in a staging query that is not loaded. The loaded attendance fact is the day rollup from decision 001.

### Relationships

All of these are many-to-one, single direction, from the table in the first column to the table in the second. Any relationship the model guesses, beyond this list, is deleted.

| From | To |
| --- | --- |
| `DimLearner[CohortKey]` | `DimCohort[CohortKey]` |
| `DimLearner[TrackKey]` | `DimTrack[TrackKey]` |
| `FactAttendance[Email]` | `DimLearner[Email]` |
| `FactParticipation[Email]` | `DimLearner[Email]` |
| `FactAssessment[Email]` | `DimLearner[Email]` |
| `FactOutcome[Email]` | `DimLearner[Email]` |
| `FactAttendance[ClassDate]` | `DimDate[Date]` |
| `FactParticipation[ClassDate]` | `DimDate[Date]` |
| `ClassDay[ClassDate]` | `DimDate[Date]` |
| `FactAttendance[WeekKey]` | `DimWeek[WeekKey]` |
| `FactParticipation[WeekKey]` | `DimWeek[WeekKey]` |
| `FactAssessment[WeekKey]` | `DimWeek[WeekKey]` |
| `ClassDay[WeekKey]` | `DimWeek[WeekKey]` |

Cohort and track reach every fact through `DimLearner`. There is one active path. A second relationship from `DimCohort` or `DimTrack` onto a fact would make two paths and an ambiguous filter. `AsOfWeek`, `FactException`, `TrackWeek`, and `SecurityUsers` stay disconnected. `TrackWeek` is read with `TREATAS` from the cohort and track still visible, so a learner can be compared with their own track median without a second path between cohort and track, and without a list of classmates.

### As-of week

`AsOfWeek` is the Monday slicer. With no week selected, measures use the latest week number currently in the folders. Activity measures keep facts whose program week is less than or equal to that number. The flag is a measure, so the same learner can be flagged in one week and clear in another when the slicer moves.

Outcome measures do not read `AsOfWeek`. Graduation and certification are the ending of a finished intake. Moving the Monday slicer changes who is flagged and what the activity rates show. It does not rewrite the graduation rate. The flag does not read `FactOutcome`.

### Unusual week

A week is unusual when its attendance rate sits more than **0.15** below the attendance rate of that track's other weeks, or its mean quiz sits more than **10** points below the mean quiz of that track's other weeks. The comparison uses weeks up to the selected as-of week when that slicer is set.

On this intake the most negative attendance gap is 0.042, on Cloud week 3, and Power BI attendance does not vary. A gap of 0.15 marks no attendance week. Cloud week 5 is the only quiz week beyond 10 points: its mean quiz is 11.1 points below the other Cloud weeks. Power BI quiz gaps stay inside about 5 points. The overview will show Cloud week 5 and no other week.

### Short class

A class day is a short class when the median minutes on that day, across the learners in that track, are under **45**. This is a mark on the day, shown beside the flag so a short Zoom is not read as forty personal failures. It does not change the personal rule. A learner still counts as attended only when their own minutes that day are greater than 30.

This intake has no short class. The shortest day median is 46 minutes. Power BI day medians are all above 100.

## Why

One path from cohort and track through the learner is what stops a track slicer from reaching another track through a stray relationship. The disconnected week slicer is what makes "as of week 4" a view of the data known by week 4, rather than a filter that also rewrites the board's graduation rate.

The 0.15 attendance gap is wider than anything this intake does. Week-to-week attendance on Cloud moves by about four points, which is ordinary. Marking those weeks as unusual would send Abena looking for a bad week that the rates do not show. The 10-point quiz gap is just tight enough to keep Cloud week 5, whose quiz mean is 42.7, and to leave the five-point moves alone.

Forty-five minutes sits under the shortest real class median and above the personal attendance line of 30. A short class then means the whole track's middle learner was in the room for less than three-quarters of an hour, which this intake never did. The personal 30-minute rule still decides each learner's own day, including the 19 Cloud sessions of exactly 30 minutes.

## Rejected

- Relating cohort and track directly to each fact as well as through `DimLearner`.
- Letting the as-of slicer filter `FactOutcome`, or letting the flag read graduation.
- An attendance gap of 0.05. Cloud week 3 is already 0.042 below the other weeks, so 0.05 is ordinary movement.
- A quiz gap of 5 points. Cloud week 2 is 5.2 points below the other weeks, and Power BI moves by about that much in more than one week.
- A short-class cutoff of 60 minutes. That marks 17 of the 50 Cloud days. Cloud's usual day median is 62 minutes, so 60 describes the track's normal length.
- Using the short-class mark to change who personally counts as attended.
