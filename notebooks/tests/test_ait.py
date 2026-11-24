"""Self-check for parse_ait_rows; uses fixed answers, no network."""
from xml.sax.saxutils import escape

from pis_lib.connect import parse_ait_rows

ROWS = (
    '<row xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    '<stads_studentcode>s123456</stads_studentcode><retning_dk>Kemi &amp; bio</retning_dk>'
    '<retning_uk xsi:nil="true" /><uddannelse_dk></uddannelse_dk></row>'
    '<row xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    '<stads_studentcode>s654321</stads_studentcode><retning_dk>Elektro</retning_dk>'
    '<retning_uk>Electrical Engineering</retning_uk><uddannelse_dk>bachelor</uddannelse_dk></row>'
)
EXPECTED = [
    {"stads_studentcode": "s123456", "retning_dk": "Kemi & bio", "retning_uk": None, "uddannelse_dk": ""},
    {"stads_studentcode": "s654321", "retning_dk": "Elektro", "retning_uk": "Electrical Engineering",
     "uddannelse_dk": "bachelor"},
]


def expect_error(answer, text):
    try:
        parse_ait_rows(answer)
    except RuntimeError as error:
        assert text in str(error), error
    else:
        raise AssertionError("no error raised")


if __name__ == "__main__":
    # The rows as escaped text inside <string>, and as XML inside it.
    escaped = f'<?xml version="1.0" encoding="utf-8"?><string xmlns="http://www.arcanic.dk/">{escape(ROWS)}</string>'
    nested = f'<?xml version="1.0" encoding="utf-8"?><string xmlns="http://www.arcanic.dk/">{ROWS}</string>'
    for answer in (escaped, nested):
        data = parse_ait_rows(answer.encode())
        assert data.to_dict("records") == EXPECTED, data.to_dict("records")
        assert (data.dtypes == object).all(), data.dtypes

    expect_error(b"<Error>Invalid object name 'View_X'.</Error>", "Invalid object name")
    expect_error(f'<string xmlns="http://www.arcanic.dk/">{escape("<Error>Login failed</Error>")}</string>'.encode(),
                 "Login failed")
    assert parse_ait_rows(b'<string xmlns="http://www.arcanic.dk/"></string>').empty
    print("ok")
