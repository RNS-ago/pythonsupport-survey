"""Self-check: parse a saved course page and assert the fields we care about."""
import datetime
import io

import requests

from pis_lib.courses import scrape


def check_progress():
    out = io.StringIO()
    p = scrape.Progress(3, stream=out)
    p.tick(found=True)
    p.tick(found=False)
    p.tick(found=False, error="02002: Read timed out")
    p.close()
    assert out.getvalue() == ("\r1 / 3 courses, 0 skipped\r2 / 3 courses, 1 skipped\r3 / 3 courses, 2 skipped\n"
                              "failed 02002: Read timed out\n"), out.getvalue()
    # only finished exam periods, newest first, and only last year's two
    assert scrape.finished_semesters(datetime.date(2026, 9, 22)) == ["Summer-2026", "Winter-2025"]
    assert scrape.finished_semesters(datetime.date(2026, 1, 15)) == ["Summer-2025", "Winter-2024"]
    # December's winter exams have no numbers yet, so last year's winter period counts
    assert scrape.finished_semesters(datetime.date(2026, 12, 31)) == ["Summer-2026", "Winter-2025"]
    assert scrape.finished_semesters(datetime.date(2027, 2, 1)) == ["Winter-2026", "Summer-2026"]
    assert scrape.finished_semesters(datetime.date(2027, 7, 31)) == ["Winter-2026", "Summer-2026"]

    assert scrape.semesters([{"slot": "E4A"}, {"slot": "E1B"}]) == ["Autumn"]
    assert scrape.semesters([{"slot": "F4A"}, {"slot": "E4A"}]) == ["Autumn", "Spring"]
    assert scrape.semesters([]) == []  # three-week courses hold no weekly slot

    codes = ["01001", "02450", "02999", "MA722"]
    assert scrape.select_range(codes, "02000-02999") == ["02450", "02999"]
    assert scrape.select_range(codes, None) == codes  # no range means every code
    print("progress ok")


GRID = {"E1A": {"day": "Monday", "start": "08:00", "end": "12:00"}}


def check_enrolment_failure():
    """A course page that loaded is kept when karakterer.dtu.dk fails or shows no number, and the failure is listed."""
    class Page:
        status_code = 200
        text = ('<div id="pagecontents"><h2>02002 Computer Programming</h2>'
                "<table><tr><td><label>Schedule</label></td><td>Autumn E1A</td></tr></table></div>")

    class Blank(Page):
        text = "<table><tr><td>Antal tilmeldte</td><td>-</td></tr></table>"

    def down(url):
        raise requests.ConnectionError("karakterer.dtu.dk is down")

    for grades, failure in [(down, "karakterer.dtu.dk is down"),
                            (lambda url: Blank(), "invalid literal for int() with base 10: '-'")]:
        class Session:
            def get(self, url):
                return grades(url) if url.startswith(scrape.GRADES) else Page()

        original, scrape.thread_session = scrape.thread_session, lambda language: Session()
        try:
            progress = scrape.Progress(1, stream=io.StringIO())
            course = scrape.fetch("02002", GRID, progress, "en-GB", ["Summer-2026"])
        finally:
            scrape.thread_session = original
        assert course["name"] == "Computer Programming" and "enrolled" not in course, course
        assert progress.failures == [f"02002 enrolment: {failure}"], progress.failures
    print("enrolment failure ok")


def check_enrolment_skipped():
    """A course without a weekly slot can't go on the schedule, so karakterer.dtu.dk isn't asked."""
    class Page:
        text = '<div id="pagecontents"><h2>02002 Computer Programming</h2></div>'

    class Session:
        def get(self, url):
            assert not url.startswith(scrape.GRADES), url
            return Page()

    original, scrape.thread_session = scrape.thread_session, lambda language: Session()
    try:
        course = scrape.fetch("02002", GRID, scrape.Progress(1, stream=io.StringIO()), "en-GB", ["Summer-2026"])
    finally:
        scrape.thread_session = original
    assert course["schedule_slots"] == [] and "enrolled" not in course, course
    print("enrolment skipped ok")


if __name__ == "__main__":
    check_progress()
    check_enrolment_failure()
    check_enrolment_skipped()
    s = scrape.session()
    course = scrape.parse(s.get("https://kurser.dtu.dk/course/2024-2025/02450").text, "02450")
    assert course["name"] == "Introduction to Machine Learning and Data Mining", course["name"]
    assert course["Language of instruction"] == "English"
    assert course["Schedule"].startswith("Spring F4A"), course["Schedule"]
    assert course["Content"].startswith("Structured data modelling"), course["Content"][:100]
    assert course["General course objectives"].startswith("To provide"), course["General course objectives"][:60]
    known = scrape.departments(s)
    # the form submits values that differ from the numbers it displays
    assert known["56"][0] == "59" and known["56"][1] == "DTU Nanolab", known["56"]
    assert known["62"][0] == "IHK", known["62"]
    assert known["01"][0] == "1", known["01"]
    assert len(known) > 20, len(known)
    nanolab = scrape.course_codes(s, ["56"])
    assert 0 < len(nanolab) < len(scrape.course_codes(s)), len(nanolab)

    grid = scrape.slot_grid(s)
    assert grid["E1A"] == {"day": "Monday", "start": "08:00", "end": "12:00"}, grid["E1A"]
    assert grid["F5B"] == {"day": "Wednesday", "start": "13:00", "end": "17:00"}, grid["F5B"]
    assert grid["E7"] == {"day": "Tuesday", "start": "18:00", "end": "22:00"}, grid["E7"]
    assert "Pause" not in grid
    assert scrape.schedule_slots("Spring F4A (Tues 13-17) Autumn E4A", grid) == [
        {"slot": "F4A", "day": "Tuesday", "start": "13:00", "end": "17:00"},
        {"slot": "E4A", "day": "Tuesday", "start": "13:00", "end": "17:00"},
    ]
    # a bare slot means both halves, and repeats collapse
    assert [s["slot"] for s in scrape.schedule_slots("Scheme A: E1A, E2, E2", grid)] == ["E1A", "E2A", "E2B"]
    assert scrape.schedule_slots("January, 3 week period", grid) == []

    semesters = scrape.finished_semesters()
    signed_up = scrape.enrolment(s, "01001", semesters)
    assert signed_up["enrolled"] > 100, signed_up  # 01001 is a first-year course
    assert signed_up["enrolled_semester"] in semesters, signed_up
    assert scrape.enrolment(s, "99999", semesters) == {}  # no such course

    codes = scrape.course_codes(s)
    assert len(codes) > 1000 and "01001" in codes, len(codes)
    print(f"ok, {len(codes)} course codes")
