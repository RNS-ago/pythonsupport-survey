"""Each study line's department, from DTU's study database, sdb.dtu.dk: the department of the line's head of studies.

A proxy: sdb.dtu.dk names no department a study line belongs to, but its head of studies is normally from the
department that runs it.
"""
import functools
import html
import re

import requests

from pis_lib.departments import short_name

BASE = "https://sdb.dtu.dk"
FIRST_YEAR = 2018  # the oldest year sdb.dtu.dk has
# The headings a year's page lists its programmes under, and what students.education_EN calls them.
EDUCATIONS = {
    "Bacheloruddannelsen": "BSc in Engineering",
    "Diplomingeniøruddannelsen": "Diplom / BEng",
    "Kandidatuddannelsen": "MSc in Engineering",
}
TITLE = re.compile(r'<div class="banner__title">\s*([^<]+?)\s*<')
PROGRAMME = re.compile(r'href="(https?://sdb\.dtu\.dk/\d{4}/\d+/\d+)">\s*([^<]+?)\s*</a>')
DISCONTINUED = re.compile(r'href="(https?://sdb\.dtu\.dk/discontinued/[\d/]+)"')
HEAD = re.compile(r'<h2 id="(?:Studieleder|Head_of_stud\w*)">[^<]*</h2>\s*<div>[^<]*</div>\s*<div>(?:<a[^>]*>)?([^<]+)')

# DTU's names for its study programmes -> the short label students.direction_DK gives them. update_static_data.ipynb
# maps static_data.study_programs with it too.
DIRECTION_LABELS = {
    "Computer Engineering"                        : "Computer eng.",
    "Kemi og Teknologi"                           : "Kemi og tek.",
    "Arktisk Byggeri og Infrastruktur"            : "Arktisk tek.",
    "Byggeri og Infrastruktur"                    : "Byggeri og infrast.",
    "Elektrisk Energiteknologi"                   : "Elektrisk energitek.",
    "Elektroteknologi"                            : "Elektrotek.",
    "Fødevaresikkerhed og -kvalitet"              : "Fødevareanaly.",
    "Global Business og Teknologi"                : "Global Biz og tek.",
    "Kemi- og Bioteknik"                          : "Kemi/biotek.",
    "Kemiteknik og International Business"        : "Kemitek./int. business",
    "Maritim Teknik"                              : "Maritim tek.",
    "Mobilitet, Transport og Logistik"            : "Mobilitet/transport",
    "Softwareteknologi"                           : "Softwaretek.",
    "Sundhedsteknologi"                           : "Sundhedstek.",
    "Anvendt Matematik"                           : "Matematik og tek",
    "Byggeteknologi"                              : "Byggetek.",
    "Cyberteknologi"                              : "Cybertek.",
    "Design og Innovation"                        : "Design og inn.",
    "Fysik og Ingeniørvidenskab"                  : "Fysik og ing.videnskab",
    "Geofysik og Rumteknologi"                    : "Geofysik og rumtek.",
    "Kvan. Biologi og Sygdomsmodel. (2020 og før)": "Kvantitativ biologi",
    "Life Science og Teknologi"                   : "Life Science",
    "Miljøteknologi"                              : "Miljøtek.",
    "Autonome Systemer"                           : "Autonome sys.",
    "Bioinformatik"                               : "Bioinfo. og systembio.",
    "Bæredygtig Energi"                           : "Bæredygtig energi",
    "Bæredygtige Energisystemer"                  : "Bæredygtig energisys.",
    "Bæredygtige Energiteknologier"               : "Bæredygtige energitek.",
    "Bæredygtigt Fiskeri og Akvakultur"           : "Bæredygtigt fisk. og akva.",
    "Biomaterialeteknologier til Medicin"         : "Biomaterialeteknologier til med.",
    "Farmateknologi"                              : "Farmatek.",
    "Fysik og Teknologi"                          : "Fysik og tek.",
    "Fødevareteknologi"                           : "Fødevaretek.",
    "Informationsteknologi"                       : "Informationstek.",
    "Kommunikationsteknologier og Systemdesign"   : "Kom.tek. og system",
    "Konstruktion og Mekanik"                     : "Konstruktion og mek.",
    "Lys og Teknologi"                            : "Lys og tek.",
    "Matematisk Modellering og Computing"         : "Mat. model. og computing",
    "Materiale- og Procesteknologi"               : "Materiale og procestek.",
    "Medicin og tek"                              : "Medicin og tek.",
    "Menneskeorienteret Kunstig Intelligens"      : "Menneskeorienteret AI",
    "Teknologisk Entreprenørskab"                 : "Tek. entreprenørskab",
    "Medicin og Teknologi"                        : "Medicin og tek.",
    "Industriel Økonomi og Teknologiledelse"      : "Industriel øko. og tekn. ledelse",
    "Kemisk og Biokemisk Teknologi"               : "Kemisk og biokemisk tek.",
    "Kvantitativ Biologi og Sygdomsmodellering"   : "Kvant. biologi og sygdomsmod.",
    "Lyd og Akustisk Teknologi"                   : "Lyd og akustisk tek.",
    "Anvendt Kemi"                                : "Anvendt kemi",
    "Business Analytics"                          : "Business analytics",
    "Bæredygtigt Energidesign"                    : "Bæredygtigt energidesign",
    "Data Science og Management"                  : "Data science og management",
    "General Engineering"                         : "General engineering",
    "IT og Økonomi"                               : "IT og økonomi",
    "Kunstig Intelligens og Data"                 : "Kunstig intelligens og data",
    "Marin Ingeniørvidenskab"                     : "Marin ingeniørvidenskab",
    "Proces og Innovation"                        : "Proces og innovation",
    "Teknisk Biomedicin"                          : "Teknisk biomedicin",
    "Transport og Logistik"                       : "Transport og logistik",
    "Olie- og Gasteknologi"                       : "Olie- og gastek.",
    "Skibsteknik og Maritimt Design"              : "Skibsteknik",
    "Mekanisk Design og Teknologi"                : "Prod. og konst.",
    "Eksport og Teknologi"                        : "Eksporting.",           # former programmes
    "Fysik og Nanoteknologi"                      : "Fysik og nanotek.",
    "Strategisk Analyse og Systemdesign"          : "Strategisk analyse og des.",
}


def session():
    s = requests.Session()
    s.request = functools.partial(s.request, timeout=30)  # requests has no default timeout
    s.headers["User-Agent"] = "Mozilla/5.0 (study line scraper)"
    return s


def sections(page):
    """Education -> (its programmes as (name, url), the url of its discontinued ones, if listed), off a year's page."""
    parts = TITLE.split(page)
    found = {}
    for title, body in zip(parts[1::2], parts[2::2]):
        discontinued = DISCONTINUED.search(body)
        found[EDUCATIONS[html.unescape(title)]] = (
            [(html.unescape(name), url) for url, name in PROGRAMME.findall(body)], discontinued and discontinued.group(1),
        )
    return found


def programmes(page):
    """(name, url) of each programme on a page of discontinued ones."""
    return [(html.unescape(name), url) for url, name in PROGRAMME.findall(page)]


def head_department(page):
    """The short name of the department of the head of studies on a programme's page; None if it names none."""
    found = HEAD.search(page)
    return found and short_name(html.unescape(found.group(1)).strip())


def direction(name):
    """students.direction_DK's label for a programme: `Anvendt matematik  (tidl. Matematik og teknologi)` ->
    `Matematik og tek`. A former name, a year or a campus after the name is dropped; a name DIRECTION_LABELS lacks is
    its own label, as for `Bygningsdesign`."""
    plain = re.sub(r"\s*\(tidl\..*?\)|\s+20\d\d$|,\s*\w+$", "", name).strip()
    return next((label for key, label in DIRECTION_LABELS.items() if key.lower() == plain.lower()), plain)


def study_lines(s, last_year):
    """{(education_EN, direction_DK): department} for every programme sdb.dtu.dk lists, also discontinued ones.

    Newest year first: an older year only adds the lines newer ones lack, so a line keeps its current department.
    A programme page without a head of studies adds nothing.
    """
    found = {}
    for year in range(last_year, FIRST_YEAR - 1, -1):
        for education, (listed, discontinued) in sections(s.get(f"{BASE}/{year}").text).items():
            if discontinued:
                listed = listed + programmes(s.get(discontinued).text)
            for name, url in listed:
                key = (education, direction(name))
                if key not in found:
                    department = head_department(s.get(url).text)
                    if department:
                        found[key] = department
    return found
