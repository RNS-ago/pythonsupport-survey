"""Self-check for the study line scraper and the department names, on page snippets shaped like sdb.dtu.dk's.

    uv run --group courses python tests/test_study_lines.py
"""
from pis_lib import study_lines
from pis_lib.departments import short_name

YEAR_PAGE = """
<div class="banner__title">
    Diplomingeni&#248;ruddannelsen
</div>
<div class="banner__item"><a href="http://sdb.dtu.dk/2026/150/2685">
Softwareteknologi                        </a></div>
<div class="banner__title">
    Bacheloruddannelsen
    <span class="banner__subtitle"><a href="http://sdb.dtu.dk/discontinued/2026/149">Bacheloruddannelser</a></span>
</div>
<div class="banner__item"><a href="http://sdb.dtu.dk/2026/149/2663">
Anvendt matematik  (tidl. Matematik og teknologi)                        </a></div>
<div class="banner__item"><a href="http://sdb.dtu.dk/2026/149/2688">
Mobilitet, Transport og Logistik                        </a></div>
"""
DANISH_PAGE = ('<h2 id="Studieleder">Studieleder</h2><div>Jane Doe</div><div><a href="http://www.fysik.dtu.dk">'
               'DTU Fysik</a></div><div>Bygning:303B</div>')
ENGLISH_PAGE = ('<h2 id="Head_of_study">Head of study</h2><div>Jane Doe</div><div><a href="https://electro.dtu.dk">'
                'DTU Electro</a></div>')


def check():
    sections = study_lines.sections(YEAR_PAGE)
    assert sections == {
        "Diplom / BEng": ([("Softwareteknologi", "http://sdb.dtu.dk/2026/150/2685")], None),
        "BSc in Engineering": ([("Anvendt matematik  (tidl. Matematik og teknologi)", "http://sdb.dtu.dk/2026/149/2663"),
                                ("Mobilitet, Transport og Logistik", "http://sdb.dtu.dk/2026/149/2688")],
                               "http://sdb.dtu.dk/discontinued/2026/149"),
    }, sections

    assert study_lines.head_department(DANISH_PAGE) == "DTU Physics"
    assert study_lines.head_department(ENGLISH_PAGE) == "DTU Electro"
    assert study_lines.head_department("<h2>Regler</h2>") is None

    assert study_lines.direction("Anvendt matematik  (tidl. Matematik og teknologi)") == "Matematik og tek"
    assert study_lines.direction("Teknisk Biomedicin 2024") == "Teknisk biomedicin"
    assert study_lines.direction("Skibsteknik og maritimt design, Lyngby") == "Skibsteknik"
    assert study_lines.direction("Kunstig Intelligens og data") == "Kunstig intelligens og data"  # any case
    assert study_lines.direction("Mobilitet, Transport og Logistik") == "Mobilitet/transport"  # a comma, no campus
    assert study_lines.direction("Bygningsdesign") == "Bygningsdesign"  # its own label

    assert short_name("01 Department of Applied Mathematics and Computer Science") == "DTU Compute"
    assert short_name("62 Department of Engineering Technology and Didactics") == "DTU Engineering Technology"
    assert short_name("DTU National Food Institute") == "DTU Food"
    assert short_name("DTU Compute") == "DTU Compute"
    print("study lines ok")


if __name__ == "__main__":
    check()
