"""Inventory the Dare Careers exports. Not on the report refresh path.

Reads Module 7 Data and prints both tracks, then the combined totals.
Definitions match the planned folder scan and the fnCleanName / duration rules.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "Module 7 Data"
FEEDS = ("Zoom Attendance", "Participation", "Labs & Quizes", "Status of Learners")
MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def clean_name(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip().lower()
    letters = "".join(ch if ("a" <= ch <= "z" or ch == " ") else "" for ch in text)
    words = [word for word in letters.split(" ") if word]
    return " ".join(words) if words else None


def parse_dd_mon_yyyy(value) -> date | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    parts = text.split("-")
    if len(parts) != 3:
        return None
    day_text, month_text, year_text = parts
    month = MONTHS.get(month_text[:3].title())
    if month is None:
        return None
    try:
        return date(int(year_text), month, int(day_text))
    except ValueError:
        return None


def parse_minutes(value) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, timedelta):
        return value.total_seconds() / 60
    if isinstance(value, time):
        return value.hour * 60 + value.minute + value.second / 60
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if ":" in text:
        parts = [part.strip() for part in text.split(":")]
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            return None
        if len(numbers) == 3:
            return numbers[0] * 60 + numbers[1] + numbers[2] / 60
        if len(numbers) == 2:
            return numbers[0] * 60 + numbers[1]
        return None
    try:
        return float(text)
    except ValueError:
        return None


def norm_email(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip().lower()
    return text or None


def lower_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [str(column).strip().lower() for column in out.columns]
    return out


def track_key(folder_name: str) -> str:
    suffix = " Training"
    if folder_name.endswith(suffix):
        return folder_name[: -len(suffix)]
    return folder_name


def find_tracks(data_root: Path) -> list[Path]:
    tracks = []
    for path in sorted(data_root.iterdir()):
        if path.is_dir() and (path / "Zoom Attendance").is_dir():
            tracks.append(path)
    return tracks


def read_zoom(track_dir: Path) -> pd.DataFrame:
    rows = []
    zoom_root = track_dir / "Zoom Attendance"
    for week_dir in sorted(zoom_root.iterdir()):
        if not week_dir.is_dir() or not week_dir.name.startswith("Week "):
            continue
        try:
            folder_week = int(week_dir.name.replace("Week", "").strip())
        except ValueError:
            folder_week = None
        for csv_path in sorted(week_dir.glob("*.csv")):
            class_date = parse_dd_mon_yyyy(csv_path.stem)
            frame = lower_columns(pd.read_csv(csv_path, encoding="utf-8-sig"))
            for record in frame.to_dict(orient="records"):
                rows.append(
                    {
                        "file": csv_path.name,
                        "folder_week": folder_week,
                        "class_date": class_date,
                        "name": None if pd.isna(record.get("name")) else str(record.get("name")).strip(),
                        "email": norm_email(record.get("email")),
                        "duration_raw": record.get("duration"),
                        "minutes": parse_minutes(record.get("duration")),
                        "role": None if pd.isna(record.get("role")) else str(record.get("role")).strip(),
                    }
                )
    return pd.DataFrame(rows)


def read_assessments(track_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    folder = track_dir / "Labs & Quizes"
    notes = []
    labs = []
    quizzes = []
    for workbook in sorted(folder.glob("*.xlsx")):
        excel = pd.ExcelFile(workbook)
        notes.append(f"{workbook.name} sheets={excel.sheet_names}")
        for sheet in excel.sheet_names:
            kind = sheet.strip().lower()
            if kind not in {"labs", "quizzes"}:
                notes.append(f"ignored sheet {workbook.name} / {sheet}")
                continue
            frame = lower_columns(pd.read_excel(workbook, sheet_name=sheet))
            week_columns = [column for column in frame.columns if column.startswith("week")]
            for record in frame.to_dict(orient="records"):
                email = norm_email(record.get("email"))
                for column in week_columns:
                    try:
                        week = int(column.replace("week", "").strip())
                    except ValueError:
                        week = None
                    score = record.get(column)
                    if score is None or (isinstance(score, float) and math.isnan(score)) or str(score).strip() == "":
                        score_number = None
                    else:
                        try:
                            score_number = float(score)
                        except (TypeError, ValueError):
                            score_number = None
                    target = labs if kind == "labs" else quizzes
                    target.append(
                        {
                            "email": email,
                            "week": week,
                            "score": score_number,
                            "raw": score,
                            "sheet": sheet,
                            "file": workbook.name,
                        }
                    )
    return pd.DataFrame(labs), pd.DataFrame(quizzes), notes


def read_status(track_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    notes = []
    rows = []
    folder = track_dir / "Status of Learners"
    for workbook in sorted(folder.glob("*.xlsx")):
        excel = pd.ExcelFile(workbook)
        notes.append(f"{workbook.name} sheets={excel.sheet_names}")
        for sheet in excel.sheet_names:
            frame = lower_columns(pd.read_excel(workbook, sheet_name=sheet))
            required = {"email", "graduation status", "certification status"}
            if not required.issubset(frame.columns):
                notes.append(f"ignored sheet {workbook.name} / {sheet}")
                continue
            for record in frame.to_dict(orient="records"):
                graduation = record.get("graduation status")
                certification = record.get("certification status")
                graduation_text = None if pd.isna(graduation) else str(graduation).strip()
                certification_text = None if pd.isna(certification) else str(certification).strip()
                rows.append(
                    {
                        "email": norm_email(record.get("email")),
                        "graduation": graduation_text,
                        "certification": certification_text,
                        "graduated": None
                        if graduation_text is None
                        else graduation_text.lower() == "graduate",
                        "certified": None
                        if certification_text is None
                        else certification_text.lower() == "certified"
                        if certification_text.lower() in {"certified", "not certified"}
                        else None,
                        "file": workbook.name,
                    }
                )
    return pd.DataFrame(rows), notes


def read_participation(track_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    notes = []
    rows = []
    folder = track_dir / "Participation"
    for workbook in sorted(folder.glob("*.xlsx")):
        excel = pd.ExcelFile(workbook)
        notes.append(f"{workbook.name} sheets={excel.sheet_names}")
        for sheet in excel.sheet_names:
            frame = lower_columns(pd.read_excel(workbook, sheet_name=sheet))
            if "date" not in frame.columns or "participants" not in frame.columns:
                notes.append(f"ignored sheet {workbook.name} / {sheet}")
                continue
            for record in frame.to_dict(orient="records"):
                class_date = parse_dd_mon_yyyy(record.get("date"))
                raw_list = record.get("participants")
                if raw_list is None or (isinstance(raw_list, float) and math.isnan(raw_list)):
                    names = []
                else:
                    names = [part.strip() for part in str(raw_list).split(",") if part.strip()]
                for name in names:
                    rows.append(
                        {
                            "class_date": class_date,
                            "name": name,
                            "clean_name": clean_name(name),
                            "file": workbook.name,
                            "sheet": sheet,
                        }
                    )
    return pd.DataFrame(rows), notes


def emails_of(frame: pd.DataFrame) -> set[str]:
    if frame.empty or "email" not in frame.columns:
        return set()
    return {email for email in frame["email"].dropna().tolist() if email}


def print_samples(label: str, rows: list[str], limit: int = 8) -> None:
    print(f"{label}: {len(rows)}")
    for row in rows[:limit]:
        print(f"  {row}")
    if len(rows) > limit:
        print(f"  ... {len(rows) - limit} more")


def week_rates(zoom: pd.DataFrame, quizzes: pd.DataFrame, learners: set[str]) -> None:
    print("--- week rates (learner-day attendance, mean submitted quiz) ---")
    print("week class_days attendance_rate mean_quiz quiz_n gap_att gap_quiz")
    by_week = {}
    for week, days in zoom.groupby("folder_week"):
        class_days = days["class_date"].nunique()
        day_minutes = (
            days.dropna(subset=["email", "minutes"])
            .groupby(["email", "class_date"], as_index=False)["minutes"]
            .sum()
        )
        attended = int((day_minutes["minutes"] > 30).sum())
        possible = class_days * len(learners)
        rate = attended / possible if possible else None
        week_quiz = quizzes[(quizzes["week"] == week) & quizzes["score"].notna()]
        mean_quiz = float(week_quiz["score"].mean()) if len(week_quiz) else None
        by_week[int(week)] = (rate, mean_quiz, class_days, len(week_quiz))
    for week in sorted(by_week):
        rate, mean_quiz, class_days, quiz_n = by_week[week]
        other_rates = [by_week[other][0] for other in by_week if other != week and by_week[other][0] is not None]
        other_quiz = [by_week[other][1] for other in by_week if other != week and by_week[other][1] is not None]
        gap_att = rate - (sum(other_rates) / len(other_rates)) if rate is not None and other_rates else None
        gap_quiz = mean_quiz - (sum(other_quiz) / len(other_quiz)) if mean_quiz is not None and other_quiz else None
        print(
            f"{week:4} {class_days:10} "
            f"{'' if rate is None else f'{rate:.3f}':>16} "
            f"{'' if mean_quiz is None else f'{mean_quiz:.1f}':>9} {quiz_n:6} "
            f"{'' if gap_att is None else f'{gap_att:+.3f}':>8} "
            f"{'' if gap_quiz is None else f'{gap_quiz:+.1f}':>8}"
        )


def build_day_attendance(zoom: pd.DataFrame) -> pd.DataFrame:
    valid = zoom.dropna(subset=["email", "minutes", "class_date", "folder_week"])
    grouped = valid.groupby(["email", "class_date", "folder_week"], as_index=False)["minutes"].sum()
    grouped["attended"] = grouped["minutes"] > 30
    return grouped


def candidate_tables(track_key_name: str, learners: list[str], status: pd.DataFrame, zoom: pd.DataFrame, labs: pd.DataFrame, quizzes: pd.DataFrame) -> None:
    day = build_day_attendance(zoom)
    class_days = (
        zoom.dropna(subset=["class_date", "folder_week"])
        .groupby("folder_week")["class_date"]
        .nunique()
        .to_dict()
    )
    weeks = sorted(int(week) for week in class_days)
    graduated = {
        row.email: row.graduated
        for row in status.itertuples(index=False)
        if row.email
    }
    non_grads = [email for email in learners if graduated.get(email) is False]

    lab_lookup = {(row.email, int(row.week)): row.score for row in labs.itertuples(index=False) if row.email and row.week is not None and not (isinstance(row.week, float) and math.isnan(row.week))}
    quiz_lookup = {(row.email, int(row.week)): row.score for row in quizzes.itertuples(index=False) if row.email and row.week is not None and not (isinstance(row.week, float) and math.isnan(row.week))}
    attended_days = defaultdict(set)
    for row in day.itertuples(index=False):
        if row.attended:
            attended_days[row.email].add((int(row.folder_week), row.class_date))

    def snapshot(email: str, week: int) -> dict:
        expected = sum(class_days[item] for item in class_days if int(item) <= week)
        attended = len({class_date for item_week, class_date in attended_days[email] if item_week <= week})
        lab_scores = [lab_lookup.get((email, item)) for item in range(1, week + 1)]
        quiz_scores = [quiz_lookup.get((email, item)) for item in range(1, week + 1)]
        lab_present = [score for score in lab_scores if score is not None and not (isinstance(score, float) and math.isnan(score))]
        quiz_present = [score for score in quiz_scores if score is not None and not (isinstance(score, float) and math.isnan(score))]
        missed = sum(score is None or (isinstance(score, float) and math.isnan(score)) for score in lab_scores + quiz_scores)
        this_lab = lab_lookup.get((email, week))
        this_quiz = quiz_lookup.get((email, week))
        prior_labs = [lab_lookup.get((email, item)) for item in range(1, week)]
        prior_quizzes = [quiz_lookup.get((email, item)) for item in range(1, week)]
        prior_labs = [score for score in prior_labs if score is not None and not (isinstance(score, float) and math.isnan(score))]
        prior_quizzes = [score for score in prior_quizzes if score is not None and not (isinstance(score, float) and math.isnan(score))]
        return {
            "rate": attended / expected if expected else None,
            "avg_lab": sum(lab_present) / len(lab_present) if lab_present else None,
            "avg_quiz": sum(quiz_present) / len(quiz_present) if quiz_present else None,
            "missed": missed,
            "lab_fall": (
                this_lab is not None
                and not (isinstance(this_lab, float) and math.isnan(this_lab))
                and len(prior_labs) >= 2
                and this_lab <= (sum(prior_labs) / len(prior_labs)) - 20
            ),
            "quiz_fall": (
                this_quiz is not None
                and not (isinstance(this_quiz, float) and math.isnan(this_quiz))
                and len(prior_quizzes) >= 2
                and this_quiz <= (sum(prior_quizzes) / len(prior_quizzes)) - 20
            ),
        }

    rules = [
        (
            "D combination: week>=4, attendance<0.60, and (avg lab<50 or avg quiz<50 or missed>=2)",
            lambda week, snap: week >= 4
            and snap["rate"] is not None
            and snap["rate"] < 0.60
            and (
                (snap["avg_lab"] is not None and snap["avg_lab"] < 50)
                or (snap["avg_quiz"] is not None and snap["avg_quiz"] < 50)
                or snap["missed"] >= 2
            ),
        ),
        (
            "A attendance to date < 0.60",
            lambda week, snap: snap["rate"] is not None and snap["rate"] < 0.60,
        ),
        (
            "A2 attendance to date < 0.50",
            lambda week, snap: snap["rate"] is not None and snap["rate"] < 0.50,
        ),
        (
            "A3 attendance to date < 0.70",
            lambda week, snap: snap["rate"] is not None and snap["rate"] < 0.70,
        ),
        (
            "B missed labs or quizzes >= 2",
            lambda week, snap: snap["missed"] >= 2,
        ),
        (
            "C lab or quiz this week is 20+ points below the learner's own prior mean (2+ prior scores)",
            lambda week, snap: snap["lab_fall"] or snap["quiz_fall"],
        ),
    ]

    print(f"--- candidate flags {track_key_name} ---")
    print(f"non_graduates={len(non_grads)} learners={len(learners)}")
    cache = {week: {email: snapshot(email, week) for email in learners} for week in weeks}
    for label, rule in rules:
        print(f"RULE {label}")
        print("week flagged flagged_non_grad missed_non_grad precision")
        first_week = {}
        for week in weeks:
            flagged = [email for email in learners if rule(week, cache[week][email])]
            flagged_non = [email for email in flagged if email in non_grads]
            missed = [email for email in non_grads if email not in flagged]
            precision = len(flagged_non) / len(flagged) if flagged else None
            print(
                f"{week:4} {len(flagged):7} {len(flagged_non):16} {len(missed):15} "
                f"{'' if precision is None else f'{precision:.3f}':>9}"
            )
            for email in flagged_non:
                first_week.setdefault(email, week)
        caught = len(first_week)
        never = len(non_grads) - caught
        if first_week:
            ordered = sorted(first_week.values())
            median = ordered[len(ordered) // 2]
            counts = Counter(ordered)
            spread = ", ".join(f"w{week}:{counts[week]}" for week in sorted(counts))
            print(f"first_flag_among_caught median_week={median} caught={caught} never_flagged_non_grad={never} by_week={spread}")
        else:
            print(f"first_flag_among_caught caught=0 never_flagged_non_grad={never}")


def diagnose_track(track_dir: Path) -> dict:
    key = track_key(track_dir.name)
    print("=" * 78)
    print(f"TRACK {key} folder={track_dir.name} cohort={track_dir.parent.name}")
    zoom = read_zoom(track_dir)
    labs, quizzes, assessment_notes = read_assessments(track_dir)
    status, status_notes = read_status(track_dir)
    participation, participation_notes = read_participation(track_dir)

    zoom_emails = emails_of(zoom)
    lab_emails = emails_of(labs)
    quiz_emails = emails_of(quizzes)
    status_emails = emails_of(status)
    learners = zoom_emails | lab_emails | quiz_emails | status_emails

    print("--- files ---")
    for note in assessment_notes + status_notes + participation_notes:
        print(f"  {note}")

    print("--- control ---")
    multi = (
        zoom.dropna(subset=["email", "class_date"])
        .groupby(["email", "class_date"])
        .size()
        .reset_index(name="rows")
    )
    multi_days = multi[multi["rows"] > 1]
    print(f"learners {len(learners)}")
    print(f"class_days {zoom['class_date'].nunique()}")
    print(f"zoom_rows {len(zoom)}")
    print(f"multi_row_learner_days {len(multi_days)}")
    print(f"lab_rows {len(labs)}")
    print(f"quiz_rows {len(quizzes)}")
    print(f"status_rows {len(status)}")

    print("--- emails ---")
    print(f"attendance {len(zoom_emails)} labs {len(lab_emails)} quizzes {len(quiz_emails)} status {len(status_emails)}")
    print_samples("missing from attendance", sorted(learners - zoom_emails))
    print_samples("missing from labs", sorted(learners - lab_emails))
    print_samples("missing from quizzes", sorted(learners - quiz_emails))
    print_samples("missing from status", sorted(learners - status_emails))
    duplicate_status = status["email"].value_counts()
    duplicate_status = duplicate_status[duplicate_status > 1]
    print_samples("duplicate status emails", [f"{email} x{count}" for email, count in duplicate_status.items()])
    name_counts = (
        zoom.dropna(subset=["email"])
        .groupby("email")["name"]
        .nunique(dropna=True)
    )
    print_samples(
        "emails with more than one Zoom display name",
        [f"{email} names={int(count)}" for email, count in name_counts.items() if count > 1],
    )

    print("--- class days ---")
    file_days = (
        zoom.dropna(subset=["class_date"])
        [["class_date", "folder_week", "file"]]
        .drop_duplicates()
        .sort_values(["class_date", "folder_week"])
    )
    start = file_days["class_date"].min()
    end = file_days["class_date"].max()
    print(f"first {start} ({start.strftime('%A') if hasattr(start, 'strftime') else start}) last {end}")
    program_mismatch = []
    weekend = []
    for row in file_days.itertuples(index=False):
        program_week = (row.class_date - start).days // 7 + 1
        if program_week != row.folder_week:
            program_mismatch.append(f"{row.file} folder_week={row.folder_week} program_week={program_week}")
        if row.class_date.weekday() >= 5:
            weekend.append(row.file)
    print_samples("file date outside its Week folder's program block", program_mismatch)
    print_samples("weekend class files", weekend)
    expected = set()
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            expected.add(cursor)
        cursor = date.fromordinal(cursor.toordinal() + 1)
    present = set(file_days["class_date"])
    print_samples("weekday with no attendance file", [item.isoformat() for item in sorted(expected - present)])
    print_samples("attendance file outside the weekday span", [item.isoformat() for item in sorted(present - expected)])
    participation_dates = set(participation["class_date"].dropna())
    print_samples("class day with no participation date", [item.isoformat() for item in sorted(present - participation_dates)])
    print_samples("participation date with no attendance file", [item.isoformat() for item in sorted(participation_dates - present)])
    unparsed_participation_dates = int(participation["class_date"].isna().sum()) if len(participation) else 0
    print(f"participation name-rows with unparsed date {unparsed_participation_dates}")

    print("--- names ---")
    zoom_names = zoom.dropna(subset=["email"]).copy()
    zoom_names["clean_name"] = zoom_names["name"].map(clean_name)
    name_owners = (
        zoom_names.dropna(subset=["clean_name"])
        .groupby("clean_name")["email"]
        .nunique()
    )
    collisions = name_owners[name_owners > 1]
    print_samples("duplicate clean names in this track", [f"{name} emails={int(count)}" for name, count in collisions.items()])
    owners = {
        name: emails.iloc[0]
        for name, emails in zoom_names.dropna(subset=["clean_name"]).groupby("clean_name")["email"]
        if len(emails.unique()) == 1
    }
    participation = participation.copy()
    participation["match_count"] = participation["clean_name"].map(
        lambda name: int(name_owners.get(name, 0)) if name else 0
    )
    unmatched = participation[participation["match_count"] != 1]
    unique_unmatched = sorted({row.clean_name or row.name for row in unmatched.itertuples(index=False)})
    print(f"participation name-rows {len(participation)}")
    print(f"unmatched participation name-rows {len(unmatched)}")
    print(f"unmatched participation names {len(unique_unmatched)}")
    print_samples("unmatched participation names", unique_unmatched)

    print("--- duration and role ---")
    unparsed = zoom[zoom["minutes"].isna()]
    print_samples(
        "duration values that did not parse",
        [f"{row.file} {row.email} raw={row.duration_raw}" for row in unparsed.itertuples(index=False)],
    )
    exact = zoom[zoom["minutes"].notna() & ((zoom["minutes"] - 30).abs().round(4) == 0)]
    under = zoom[zoom["minutes"].notna() & (zoom["minutes"] < 30)]
    print(f"sessions of exactly 30 minutes {len(exact)}")
    print(f"sessions under 30 minutes {len(under)}")
    if len(zoom["minutes"].dropna()):
        print(f"minutes min {zoom['minutes'].min():.2f} max {zoom['minutes'].max():.2f}")
    roles = zoom["role"].fillna("(blank)").value_counts()
    print("roles " + ", ".join(f"{role}={count}" for role, count in roles.items()))
    print(f"learner-days with more than one Zoom row {len(multi_days)}")
    if len(multi_days):
        sample = multi_days.head(5)
        for row in sample.itertuples(index=False):
            detail = zoom[(zoom["email"] == row.email) & (zoom["class_date"] == row.class_date)]
            minutes = ", ".join(str(item) for item in detail["duration_raw"].tolist())
            print(f"  {row.email} {row.class_date} rows={row.rows} durations={minutes}")

    print("--- assessments ---")
    for label, frame in (("lab", labs), ("quiz", quizzes)):
        blank = int(frame["score"].isna().sum())
        zero = int((frame["score"] == 0).sum())
        outside = frame[frame["score"].notna() & ((frame["score"] < 0) | (frame["score"] > 100))]
        print(f"{label} rows={len(frame)} blank={blank} zero={zero} outside_0_100={len(outside)}")
        if len(outside):
            print_samples(
                f"{label} scores outside 0-100",
                [f"{row.email} week={row.week} score={row.score}" for row in outside.head(8).itertuples(index=False)],
            )
        bad_week = frame[frame["week"].isna()]
        print(f"{label} rows with an unparsed week {len(bad_week)}")

    print("--- status ---")
    print("graduation " + ", ".join(f"{value}={count}" for value, count in status["graduation"].value_counts(dropna=False).items()))
    print("certification " + ", ".join(f"{value}={count}" for value, count in status["certification"].value_counts(dropna=False).items()))
    disagree = status[(status["certified"] == True) & (status["graduated"] == False)]  # noqa: E712
    unknown = status[status["graduated"].isna() | status["certified"].isna()]
    print_samples(
        "certified and not a graduate",
        [f"{row.email} graduation={row.graduation} certification={row.certification}" for row in disagree.itertuples(index=False)],
    )
    print_samples(
        "status text outside Graduate / Non Graduate / Certified / Not Certified",
        [f"{row.email} graduation={row.graduation} certification={row.certification}" for row in unknown.itertuples(index=False)],
    )
    graduated_not_certified = int(((status["graduated"] == True) & (status["certified"] == False)).sum())  # noqa: E712
    print(f"graduates who are not certified {graduated_not_certified}")
    print(f"non_graduates {int((status['graduated'] == False).sum())}")  # noqa: E712

    medians = (
        zoom.dropna(subset=["minutes", "class_date"])
        .groupby("class_date")["minutes"]
        .median()
        .sort_values()
    )
    print("--- class-day median minutes ---")
    if len(medians):
        print(
            f"shortest {medians.index[0]} {medians.iloc[0]:.1f}  "
            f"p10 {medians.quantile(0.10):.1f}  median {medians.median():.1f}  "
            f"longest {medians.index[-1]} {medians.iloc[-1]:.1f}"
        )
        for cutoff in (45, 60, 75):
            short = medians[medians < cutoff]
            print(f"days with median under {cutoff}: {len(short)}")

    week_rates(zoom, quizzes, learners)
    print("--- hindsight, not a flag: mean score by ending ---")
    ending = status.set_index("email")["graduated"].to_dict()
    for label, frame in (("lab", labs), ("quiz", quizzes)):
        present = frame[frame["score"].notna()].copy()
        present["graduated"] = present["email"].map(ending)
        for graduated, group in present.groupby("graduated"):
            name = {True: "graduate", False: "non_graduate"}.get(graduated, "unknown")
            print(f"{label} {name} n={len(group)} mean={group['score'].mean():.1f}")
    day = build_day_attendance(zoom)
    day["graduated"] = day["email"].map(ending)
    for graduated, group in day.groupby("graduated"):
        name = {True: "graduate", False: "non_graduate"}.get(graduated, "unknown")
        rate = group["attended"].mean() if len(group) else None
        print(f"attendance {name} learner_days={len(group)} rate={rate:.3f}")
    zoom_names = zoom.dropna(subset=["email"]).copy()
    zoom_names["clean_name"] = zoom_names["name"].map(clean_name)
    name_to_email = (
        zoom_names.dropna(subset=["clean_name"])
        .groupby("clean_name")["email"]
        .agg(lambda series: series.iloc[0] if series.nunique() == 1 else None)
        .to_dict()
    )
    participated = participation.copy()
    participated["email"] = participated["clean_name"].map(name_to_email)
    participated = participated.dropna(subset=["email", "class_date"]).drop_duplicates(["email", "class_date"])
    possible_days = zoom.dropna(subset=["class_date"])["class_date"].nunique()
    for graduated_value, label in ((True, "graduate"), (False, "non_graduate")):
        people = [email for email, flag in ending.items() if flag is graduated_value]
        hits = participated[participated["email"].isin(people)]
        possible = len(people) * possible_days
        rate = len(hits) / possible if possible else None
        print(f"participation {label} name_days={len(hits)} possible={possible} rate={rate:.3f}")
    candidate_tables(key, sorted(learners), status, zoom, labs, quizzes)

    return {
        "key": key,
        "learners": learners,
        "class_days": set(zoom["class_date"].dropna()),
        "zoom_rows": len(zoom),
        "multi_row_learner_days": len(multi_days),
        "lab_rows": len(labs),
        "quiz_rows": len(quizzes),
        "status_rows": len(status),
        "unmatched_participation_names": len(unique_unmatched),
        "owners": owners,
    }


def main() -> None:
    tracks = find_tracks(DATA_ROOT)
    if not tracks:
        raise SystemExit(f"No track folders under {DATA_ROOT}")
    summaries = [diagnose_track(track) for track in tracks]
    print("=" * 78)
    print("COMBINED")
    print("--- control ---")
    for summary in summaries:
        print(
            f"{summary['key']} learners={len(summary['learners'])} class_days={len(summary['class_days'])} "
            f"zoom_rows={summary['zoom_rows']} multi_row_learner_days={summary['multi_row_learner_days']} "
            f"lab_rows={summary['lab_rows']} quiz_rows={summary['quiz_rows']} status_rows={summary['status_rows']} "
            f"unmatched_participation_names={summary['unmatched_participation_names']}"
        )
    print(
        "all learners "
        f"{sum(len(summary['learners']) for summary in summaries)} "
        "all class_days "
        f"{sum(len(summary['class_days']) for summary in summaries)}"
    )
    seen = defaultdict(list)
    for summary in summaries:
        for email in summary["learners"]:
            seen[email].append(summary["key"])
    shared = {email: keys for email, keys in seen.items() if len(keys) > 1}
    print_samples("emails on more than one track", [f"{email} {keys}" for email, keys in sorted(shared.items())])
    shared_names = defaultdict(set)
    for summary in summaries:
        for name, email in summary["owners"].items():
            shared_names[name].add((summary["key"], email))
    collisions = {name: owners for name, owners in shared_names.items() if len(owners) > 1}
    print_samples(
        "clean names used on more than one track",
        [f"{name} {sorted(owners)}" for name, owners in sorted(collisions.items())],
    )


if __name__ == "__main__":
    main()
