"""Self-check for the dashboard page: builds it from fake data, without a database, and runs its scripts in Node.js
(18 or later), with a stand-in for the browser. dashboard_page_check.js does the clicking and checking.

    uv run --group visualization python tests/test_dashboard_page.py
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

NOTEBOOK = Path(__file__).resolve().parent.parent / "visualization" / "dashboard.ipynb"
CHECK = Path(__file__).resolve().with_name("dashboard_page_check.js")
LINES = [f"Line {i:02d}" for i in range(56)]
COURSES = [f"0{i:04d} - Course {i}" for i in range(25)]


def fake_responses(n=3000):
    """Visits as dashboard.ipynb reads them from processed_responses: anonymous ones before autumn 2024, then student
    numbers, some not in the student data (Unknown), and educations without a study line (N/A)."""
    rng = np.random.default_rng(1)
    created = pd.Timestamp("2023-09-04", tz="UTC") + pd.to_timedelta(rng.integers(0, 1150 * 24 * 60, n), unit="min")
    local = created.tz_convert("Europe/Copenhagen")
    anonymous = created < pd.Timestamp("2024-09-01", tz="UTC")
    not_found = ~anonymous & (rng.random(n) < 0.12)
    found = ~anonymous & ~not_found
    education = rng.choice(["BSc Eng", "BEng", "MSc Eng", "MSc", "PhD", "Exchange student", "Single course"], n)
    weights = 1 / np.arange(1, len(LINES) + 1)
    line = rng.choice(LINES, n, p=weights / weights.sum())
    asked = created > pd.Timestamp("2025-09-01", tz="UTC")

    def student(values):
        return pd.Series(np.where(found, values, "Unknown")).where(~anonymous)

    return pd.DataFrame({
        "created_at": created,
        "visitor_id": np.where(anonymous, np.nan, rng.integers(0, 900, n)),
        "satisfaction": rng.integers(1, 6, n),
        "building_number": rng.choice(["101", "303", "308"], n),
        "gender": student(rng.choice(["Female", "Male"], n)),
        "education_EN": student(education),
        "direction_DK": student(np.where(np.isin(education, ["PhD", "Exchange student", "Single course"]), "N/A", line)),
        "weekday": local.day_name(),
        "time_slot": np.where(local.hour < 12, "Morning", "Afternoon"),
        "semester": np.where(local.month <= 8, "Spring ", "Fall ") + local.strftime("%y"),
        "study_start": student(rng.choice(["s23", "s24", "s25", "s22 and older"], n)),
        "verified": found,
        "ai": np.where(asked, rng.choice(["Yes", "No", "No answer"], n), None),
        "course": np.where(asked, rng.choice(COURSES + [None] * 5, n), None),
        "department": np.where(asked, rng.choice(["01 Department of Applied Mathematics", "10 Department of Physics"], n), None),
    })


def build_page(responses_df, page):
    """Runs the notebook's code cells, the database one replaced by the fake rows, and returns their variables."""
    cells = ["".join(cell["source"]) for cell in json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
             if cell["cell_type"] == "code"]
    fetched = pd.DataFrame({"table_name": ["students"], "fetched_at": pd.to_datetime(["2026-11-01"], utc=True)})
    namespace = {}
    cwd = os.getcwd()
    os.environ["DASHBOARD_HTML"] = str(page)
    os.chdir(NOTEBOOK.parent)  # the notebook reads its template, style and script from its folder, as in Jupyter
    try:
        for source in cells:
            if "get_pg_engine()" in source:
                namespace.update(responses_df=responses_df, fetched=fetched)
            else:
                exec(source, namespace)
    finally:
        os.chdir(cwd)
    return namespace


if __name__ == "__main__":
    node = shutil.which("node")
    assert node, "Node.js isn't on PATH"
    with tempfile.TemporaryDirectory() as folder:
        page = Path(folder) / "dashboard.html"
        variables = build_page(fake_responses(), page)
        df = variables["df"]
        dates = [pd.Timestamp("2025-09-03 12:00"), pd.Timestamp("2025-10-29 12:00")]  # mid-week, clear of week starts
        expected = {
            "visits": len(df),
            "unknown_line": int((df["direction_DK"] == "Unknown").sum()),
            "semester": variables["CURRENT"],
            "semester_visits": int((df["semester"] == variables["CURRENT"]).sum()),
            "dates": [f"{date:%Y-%m-%dT%H:%M:%S}" for date in dates],  # local time, as the page reads the weeks
            "dates_visits": int(df["week"].between(*dates).sum()),
            "timeline_width": variables["timeline"].width,
        }
        result = subprocess.run([node, str(CHECK), str(page), json.dumps(expected)],
                                capture_output=True, text=True, timeout=300)
        print(result.stdout, end="")
        assert result.returncode == 0, "see the FAIL above" if "FAIL" in result.stdout else result.stderr
    print("dashboard page ok")
