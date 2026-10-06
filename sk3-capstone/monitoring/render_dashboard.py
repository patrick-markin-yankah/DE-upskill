"""Render monitoring/dashboard.html from the queries in dashboard.json.

Usage: python render_dashboard.py

Reads ops.pipeline_runs through WAREHOUSE_* and writes the HTML next to this file.
"""
import html
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent
SPEC_PATH = HERE / "dashboard.json"
OUT_PATH = HERE / "dashboard.html"
DISPLAYS = {"line", "series", "bar", "rate"}
COLORS = ("#1f4e79", "#2e7d32", "#c62828", "#ef6c00")


def warehouse_conn():
    return psycopg2.connect(
        host=os.environ["WAREHOUSE_HOST"],
        port=os.environ["WAREHOUSE_PORT"],
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
    )


def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text())
    widgets = spec.get("widgets")
    if not isinstance(widgets, list) or not widgets:
        raise SystemExit("dashboard.json needs a non-empty widgets list")
    for widget in widgets:
        if widget.get("display") not in DISPLAYS:
            raise SystemExit(f"unknown display for {widget.get('title')}: {widget.get('display')}")
        query = widget.get("query", "").lstrip().lower()
        if not query.startswith("select"):
            raise SystemExit(f"query for {widget.get('title')} must be a SELECT")
    return spec


def fetch(conn, query: str) -> tuple[list[str], list[tuple]]:
    with conn.cursor() as cur:
        cur.execute(query)
        columns = [desc.name for desc in cur.description]
        return columns, cur.fetchall()


def as_number(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        if text in {"", "-"}:
            text = "0"
        return text
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _scale(values: list[float]) -> float:
    peak = max(values) if values else 0
    return peak if peak > 0 else 1


def _svg_frame(y_label: str, y_max: float) -> list[str]:
    ticks = [0, y_max / 2, y_max]
    lines = [
        '<svg viewBox="0 0 720 240" role="img">',
        '<line x1="48" y1="16" x2="48" y2="200" stroke="#c5cdd6"/>',
        '<line x1="48" y1="200" x2="700" y2="200" stroke="#c5cdd6"/>',
    ]
    for tick in ticks:
        y = 200 - (tick / y_max) * 176
        lines.append(f'<line x1="48" y1="{y:.1f}" x2="700" y2="{y:.1f}" stroke="#e6ebf0"/>')
        lines.append(
            f'<text x="42" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#5c6b7a">'
            f"{format_value(int(tick) if tick == int(tick) else round(tick, 2))}</text>"
        )
    lines.append(
        f'<text x="16" y="120" font-size="11" fill="#5c6b7a" transform="rotate(-90 16 120)">'
        f"{html.escape(y_label)}</text>"
    )
    return lines


def chart_line(columns: list[str], rows: list[tuple], y_label: str, series: bool) -> str:
    if not rows:
        return "<p>No runs in the last 30 days.</p>"
    y_start = 1
    y_names = columns[y_start:]
    peaks = [as_number(row[index]) for row in rows for index in range(y_start, len(columns))]
    y_max = _scale(peaks)
    parts = _svg_frame(y_label, y_max)
    slot = 652 / max(len(rows) - 1, 1)
    for series_index, name in enumerate(y_names):
        color = COLORS[series_index % len(COLORS)]
        coords = []
        for row_index, row in enumerate(rows):
            x = 48 if len(rows) == 1 else 48 + row_index * slot
            y = 200 - (as_number(row[y_start + series_index]) / y_max) * 176
            coords.append(f"{x:.1f},{y:.1f}")
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(coords)}"/>'
        )
    for row_index, row in enumerate(rows):
        x = 48 if len(rows) == 1 else 48 + row_index * slot
        label = format_value(row[0])
        parts.append(
            f'<text x="{x:.1f}" y="220" text-anchor="middle" font-size="11" fill="#5c6b7a">'
            f"{html.escape(label)}</text>"
        )
    if series:
        for series_index, name in enumerate(y_names):
            color = COLORS[series_index % len(COLORS)]
            x = 80 + series_index * 120
            parts.append(f'<rect x="{x}" y="4" width="10" height="10" fill="{color}"/>')
            parts.append(
                f'<text x="{x + 14}" y="13" font-size="11" fill="#243140">{html.escape(name)}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def chart_bar(columns: list[str], rows: list[tuple], y_label: str) -> str:
    if not rows:
        return "<p>No runs in the last 30 days.</p>"
    y_max = _scale([as_number(row[1]) for row in rows])
    parts = _svg_frame(y_label, y_max)
    width = 80
    gap = 560 / max(len(rows), 1)
    for index, row in enumerate(rows):
        value = as_number(row[1])
        height = (value / y_max) * 176
        x = 80 + index * gap
        y = 200 - height
        color = COLORS[index % len(COLORS)]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width}" height="{height:.1f}" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x + width / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-size="12" fill="#243140">'
            f"{html.escape(format_value(row[1]))}</text>"
        )
        parts.append(
            f'<text x="{x + width / 2:.1f}" y="220" text-anchor="middle" font-size="11" fill="#5c6b7a">'
            f"{html.escape(format_value(row[0]))}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def data_table(columns: list[str], rows: list[tuple]) -> str:
    head = "".join(f"<th>{html.escape(name)}</th>" for name in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(format_value(value))}</td>" for value in row)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def rate_note(rows: list[tuple]) -> str:
    if not rows:
        return ""
    passed = sum(1 for row in rows if as_number(row[1]) == 100)
    share = (passed / len(rows)) * 100
    share_text = format_value(Decimal(str(share)))
    return f"<p>{passed} of {len(rows)} runs passed ({share_text}%).</p>"


def render_widget(widget: dict, columns: list[str], rows: list[tuple]) -> str:
    display = widget["display"]
    y_label = widget.get("y_label", "")
    if display == "bar":
        picture = chart_bar(columns, rows, y_label)
        note = ""
    elif display == "rate":
        picture = chart_line(columns, rows, y_label, series=False)
        note = rate_note(rows)
    else:
        picture = chart_line(columns, rows, y_label, series=(display == "series"))
        note = ""
    query = html.escape(widget["query"])
    return f"""
<section>
  <h2>{html.escape(widget["title"])}</h2>
  {note}
  {picture}
  {data_table(columns, rows)}
  <details><summary>Query</summary><pre>{query}</pre></details>
</section>
"""


def main() -> None:
    spec = load_spec()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sections = []
    conn = warehouse_conn()
    try:
        for widget in spec["widgets"]:
            columns, rows = fetch(conn, widget["query"])
            print(f"[dashboard] {widget['title']}: {len(rows)} points")
            sections.append(render_widget(widget, columns, rows))
    finally:
        conn.close()

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FinCore pipeline</title>
  <style>
    body {{ font-family: Georgia, serif; color: #243140; margin: 2rem auto; max-width: 760px; }}
    h1 {{ font-size: 1.6rem; margin-bottom: 0.2rem; }}
    p.meta {{ color: #5c6b7a; }}
    section {{ margin-top: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
    th, td {{ border-bottom: 1px solid #e6ebf0; text-align: left; padding: 0.3rem 0.5rem; font-family: ui-monospace, monospace; font-size: 0.85rem; }}
    pre {{ white-space: pre-wrap; font-size: 0.8rem; }}
    svg {{ width: 100%; height: auto; }}
  </style>
</head>
<body>
  <h1>FinCore pipeline</h1>
  <p class="meta">ops.pipeline_runs, last {int(spec.get("window_days", 30))} days. Generated {generated}.</p>
  {''.join(sections)}
</body>
</html>
"""
    OUT_PATH.write_text(page)
    print(f"[dashboard] wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
