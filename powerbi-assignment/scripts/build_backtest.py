"""Build the stage 8 Data Engineering track and a tiny second intake.

`hold` writes them under scripts/stage8-add, which Power BI does not scan.
Move each folder into Backtest only at the step in the stage 8 guide.
`track` and `sibling` write straight into Backtest. DataRoot must point at
Backtest while those folders are there, and Backtest is removed before the
last refresh.
"""
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(r"c:\Users\PatrickMarkin-Yankah\Documents\GitHub\DE-upskill\powerbi-assignment")
BACKTEST = ROOT / "Backtest"
DE = BACKTEST / "Module 7 Data" / "Data Engineering Training"
SIBLING = BACKTEST / "Spring 2025 Intake" / "Cloud Training"

WEEKS = {
    1: [date(2024, 8, 5), date(2024, 8, 6), date(2024, 8, 7), date(2024, 8, 8), date(2024, 8, 9)],
    2: [date(2024, 8, 12), date(2024, 8, 13), date(2024, 8, 14), date(2024, 8, 15), date(2024, 8, 16)],
    3: [date(2024, 8, 19), date(2024, 8, 20), date(2024, 8, 21), date(2024, 8, 22), date(2024, 8, 23)],
    4: [date(2024, 8, 26), date(2024, 8, 27), date(2024, 8, 28), date(2024, 8, 29), date(2024, 8, 30)],
    5: [date(2024, 9, 2), date(2024, 9, 3), date(2024, 9, 4), date(2024, 9, 5), date(2024, 9, 6)],
    6: [date(2024, 9, 9), date(2024, 9, 10), date(2024, 9, 11), date(2024, 9, 12), date(2024, 9, 13)],
    7: [date(2024, 9, 16), date(2024, 9, 17), date(2024, 9, 18), date(2024, 9, 19), date(2024, 9, 20)],
    8: [date(2024, 9, 23), date(2024, 9, 24), date(2024, 9, 25), date(2024, 9, 26), date(2024, 9, 27)],
    9: [date(2024, 9, 30), date(2024, 10, 1), date(2024, 10, 2), date(2024, 10, 3), date(2024, 10, 4)],
    10: [date(2024, 10, 7), date(2024, 10, 8), date(2024, 10, 9), date(2024, 10, 10), date(2024, 10, 11)],
}

# last week the learner still appears in Zoom, unless a week is skipped
LEARNERS = [
    {"email": "ada.mensah@de.test", "name": "Ada Mensah", "last": 10, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Graduate", "cert": "Certified", "lab": 75, "quiz": 78},
    {"email": "kojo.boateng@de.test", "name": "Kojo Boateng", "last": 10, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Graduate", "cert": "Not Certified", "lab": 72, "quiz": 74},
    {"email": "ama.serwaa@de.test", "name": "Ama Serwaa", "last": 10, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Graduate", "cert": "Certified", "lab": 80, "quiz": 82},
    {"email": "yaw.owusu@de.test", "name": "Yaw Owusu", "last": 10, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Graduate", "cert": "Certified", "lab": 76, "quiz": 79},
    {"email": "efua.asante@de.test", "name": "Efua Asante", "last": 2, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Non Graduate", "cert": "Not Certified", "lab": 70, "quiz": 72},
    {"email": "kofi.mensah@de.test", "name": "Kofi Mensah", "last": 5, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Non Graduate", "cert": "Not Certified", "lab": 68, "quiz": 71},
    {"email": "akua.darko@de.test", "name": "Akua Darko", "last": 8, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Non Graduate", "cert": "Not Certified", "lab": 74, "quiz": 73},
    {"email": "nana.yaa@de.test", "name": "Nana Yaa", "last": 10, "skip": set(), "nolist": {4}, "listonly": set(), "grad": "Graduate", "cert": "Certified", "lab": 77, "quiz": 80},
    {"email": "kwame.boateng@de.test", "name": "Kwame Boateng", "last": 10, "skip": {6}, "nolist": set(), "listonly": set(), "grad": "Graduate", "cert": "Not Certified", "lab": 75, "quiz": 78},
    {"email": "abena.darko@de.test", "name": "Abena Darko", "last": 10, "skip": set(), "nolist": set(), "listonly": {7}, "grad": "Graduate", "cert": "Certified", "lab": 81, "quiz": 77},
    {"email": "kwesi.appiah@de.test", "name": "Kwesi Appiah", "last": 10, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Non Graduate", "cert": "Not Certified", "lab": "low", "quiz": "low"},
    {"email": "esi.mensah@de.test", "name": "Esi Mensah", "last": 4, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Non Graduate", "cert": "Not Certified", "lab": 70, "quiz": 72, "score_all": True},
    {"email": "adjoa.owusu@de.test", "name": "Adjoa Owusu", "last": 10, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Graduate", "cert": "Not Certified", "lab": 40, "quiz": 70},
    {"email": "yaw.darko@de.test", "name": "Yaw Darko", "last": 4, "skip": set(), "nolist": set(), "listonly": set(), "grad": "Graduate", "cert": "Certified", "lab": 80, "quiz": 80, "score_all": True},
]

# 13 people are still in the room on these week-3 days. Efua has already stopped.
WEEK3 = [p for p in LEARNERS if p["last"] >= 3 and 3 not in p["skip"]]
SHORT_DAY = {
    email: minutes
    for email, minutes in zip(
        [p["email"] for p in WEEK3],
        [10, 20, 30, 31, 35, 38, 40, 42, 44, 50, 80, 90, 100],
    )
}
EXACT_45 = {
    email: minutes
    for email, minutes in zip(
        [p["email"] for p in WEEK3],
        [40, 42, 43, 44, 44, 45, 45, 46, 50, 60, 70, 80, 90],
    )
}
TWO_SHORT = {
    email: minutes
    for email, minutes in zip(
        [p["email"] for p in WEEK3],
        [15, 20, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100],
    )
}
KWESI_LAB = {1: 40, 2: 40, 3: 40, 4: 40, 5: 0, 6: 40, 7: 40, 8: 40, 9: None, 10: 40}
KWESI_QUIZ = {1: 42, 2: 42, 3: 42, 4: 42, 5: 42, 6: 42, 7: 42, 8: None, 9: 42, 10: 42}


def stamp(day):
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{day.day:02d}-{months[day.month - 1]}-{day.year}"


def clock(minutes):
    hours, mins = divmod(int(minutes), 60)
    return f"{hours}:{mins:02d}:00"


def in_room(person, week):
    return week <= person["last"] and week not in person["skip"]


def zoom_minutes(person, week, day):
    if not in_room(person, week):
        return None
    if week in person["listonly"]:
        return None
    if day == date(2024, 8, 21):
        return SHORT_DAY[person["email"]]
    if day == date(2024, 8, 20):
        return EXACT_45[person["email"]]
    if day == date(2024, 8, 19):
        return TWO_SHORT[person["email"]]
    if day == date(2024, 8, 22) and person["email"] in {"ada.mensah@de.test", "kojo.boateng@de.test"}:
        return None
    return 80


def score(person, kind, week):
    if week in person["skip"]:
        return None
    if week > person["last"] and not person.get("score_all"):
        return None
    if person["email"] == "kwesi.appiah@de.test":
        return (KWESI_LAB if kind == "lab" else KWESI_QUIZ)[week]
    return person[kind]


def col_name(index):
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def sheet_xml(rows):
    body = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row, start=1):
            if value is None or value == "":
                continue
            ref = f"{col_name(c)}{r}"
            if isinstance(value, int):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData></worksheet>'
    )


def write_xlsx(path, sheets):
    path.parent.mkdir(parents=True, exist_ok=True)
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    ]
    workbook_rels = []
    workbook_sheets = []
    for i, (name, _) in enumerate(sheets, start=1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        )
        workbook_sheets.append(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(overrides)
        + "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>'
    )
    workbook_rel_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(workbook_rels)
        + "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as book:
        book.writestr("[Content_Types].xml", content_types)
        book.writestr("_rels/.rels", root_rels)
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", workbook_rel_xml)
        for i, (_, rows) in enumerate(sheets, start=1):
            book.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(rows))


def write_track():
    for week, days in WEEKS.items():
        folder = DE / "Zoom Attendance" / f"Week {week}"
        folder.mkdir(parents=True, exist_ok=True)
        for day in days:
            lines = ["Name,Email,Join Time,Leave Time,Duration,Role"]
            for person in LEARNERS:
                if day == date(2024, 8, 22) and person["email"] == "ada.mensah@de.test":
                    parts = [(20, "18:00", "18:20"), (25, "18:40", "19:05")]
                elif day == date(2024, 8, 22) and person["email"] == "kojo.boateng@de.test":
                    parts = [(10, "18:00", "18:10"), (20, "18:30", "18:50")]
                else:
                    minutes = zoom_minutes(person, week, day)
                    parts = [] if minutes is None else [(minutes, "18:00", "19:20")]
                for minutes, join, leave in parts:
                    duration = clock(minutes) if week == 2 else str(minutes)
                    lines.append(f"{person['name']},{person['email']},{join},{leave},{duration},Participant")
            (folder / f"{stamp(day)}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    participation = [["Date", "Participants"]]
    for week, days in WEEKS.items():
        for day in days:
            names = []
            for person in LEARNERS:
                if not in_room(person, week) or week in person["nolist"]:
                    if week in person["listonly"] and week <= person["last"]:
                        names.append(person["name"])
                    continue
                if week in person["listonly"]:
                    names.append(person["name"])
                    continue
                label = "Ama  Serwaa" if person["email"] == "ama.serwaa@de.test" and day == date(2024, 8, 5) else person["name"]
                names.append(label)
            if day == date(2024, 8, 6):
                names.append("Guest Speaker")
            participation.append([stamp(day), ", ".join(names)])
    write_xlsx(DE / "Participation" / "participation.xlsx", [("Sheet1", participation)])

    header = ["Email"] + [f"Week {n}" for n in range(1, 11)]
    labs = [header]
    quizzes = [header]
    for person in LEARNERS:
        labs.append([person["email"]] + [score(person, "lab", n) for n in range(1, 11)])
        quizzes.append([person["email"]] + [score(person, "quiz", n) for n in range(1, 11)])
    write_xlsx(DE / "Labs & Quizes" / "labs_and_quizzes.xlsx", [("Labs", labs), ("Quizzes", quizzes)])

    status = [["Email", "Graduation Status", "Certification Status"]]
    for person in LEARNERS:
        status.append([person["email"], person["grad"], person["cert"]])
    write_xlsx(DE / "Status of Learners" / "participant_status.xlsx", [("Sheet1", status)])
    print(DE)


def write_sibling():
    day = date(2025, 1, 6)
    folder = SIBLING / "Zoom Attendance" / "Week 1"
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["Name,Email,Join Time,Leave Time,Duration,Role"]
    people = [("Spring One", "spring.one@intake.test"), ("Spring Two", "spring.two@intake.test")]
    for name, email in people:
        lines.append(f"{name},{email},18:00,19:30,90,Participant")
    (folder / f"{stamp(day)}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_xlsx(
        SIBLING / "Participation" / "participation.xlsx",
        [("Sheet1", [["Date", "Participants"], [stamp(day), "Spring One, Spring Two"]])],
    )
    write_xlsx(
        SIBLING / "Labs & Quizes" / "labs_and_quizzes.xlsx",
        [
            ("Labs", [["Email", "Week 1"], ["spring.one@intake.test", 70], ["spring.two@intake.test", 65]]),
            ("Quizzes", [["Email", "Week 1"], ["spring.one@intake.test", 72], ["spring.two@intake.test", 68]]),
        ],
    )
    write_xlsx(
        SIBLING / "Status of Learners" / "participant_status.xlsx",
        [("Sheet1", [
            ["Email", "Graduation Status", "Certification Status"],
            ["spring.one@intake.test", "Graduate", "Certified"],
            ["spring.two@intake.test", "Non Graduate", "Not Certified"],
        ])],
    )
    print(SIBLING)


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "hold"
    if which == "hold":
        hold = ROOT / "scripts" / "stage8-add"
        DE = hold / "Data Engineering Training"
        SIBLING = hold / "Spring 2025 Intake" / "Cloud Training"
    if which in {"track", "both", "hold"}:
        write_track()
    if which in {"sibling", "both", "hold"}:
        write_sibling()
