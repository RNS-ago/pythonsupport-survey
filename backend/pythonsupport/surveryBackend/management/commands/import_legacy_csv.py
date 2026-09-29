"""One-off import of the old backend's CSV export.

    python manage.py import_legacy_csv Raw_customer_entries.csv --dry-run
    python manage.py import_legacy_csv Raw_customer_entries.csv
"""

import csv
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from surveryBackend.models import SatisfactionSurveyResponse, course_number_format, student_number_format

# The export's times are local wall-clock times with no offset.
EXPORT_TIMEZONE = ZoneInfo('Europe/Copenhagen')
# The old backend wrote True/False, with the odd Yes/No; '' means "not asked".
ANSWERS = {'true': True, 'yes': True, 'false': False, 'no': False, '': None}


def to_response(row):
    """Map one CSV row onto an unsaved response. Email and Title are ignored."""
    # The old backend put student numbers and staff initials in one column.
    identifier = row['Enter you student number'].strip().lower()
    is_student = student_number_format.regex.search(identifier)
    # Free text without a leading course code is dropped; the rest of the row is kept.
    course = row['Course Number'].strip()
    return SatisfactionSurveyResponse(
        student_number=identifier if is_student else '',
        username='' if is_student else identifier,
        satisfaction=row['Did you get the help you needed?'].strip(),
        course_number=course if course_number_format.regex.search(course) else '',
        building_number=row['Location'].strip(),
        workshop=ANSWERS.get(row['Workshop'].strip().lower(), row['Workshop']),
        used_ai=ANSWERS.get(row['Used AI'].strip().lower(), row['Used AI']),
        created_at=datetime.strptime(row['Completion time'].strip(), '%m/%d/%Y %I:%M %p').replace(tzinfo=EXPORT_TIMEZONE),
    )


class Command(BaseCommand):
    help = "Import responses from the old backend's CSV export. Run once per database."

    def add_arguments(self, parser):
        parser.add_argument('csv_path')
        parser.add_argument('--dry-run', action='store_true', help="Validate and report only; save nothing.")

    def handle(self, csv_path, dry_run, **options):
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))

        responses, skipped, blank_courses = [], [], []
        for line, row in enumerate(rows, start=2):  # line 1 is the header
            try:
                response = to_response(row)
                response.full_clean()
            except (ValidationError, ValueError) as exc:
                skipped.append(f"line {line}: {exc}")
                continue
            responses.append(response)
            if row['Course Number'].strip() and not response.course_number:
                blank_courses.append(f"line {line}: {row['Course Number']!r}")

        for message in skipped:
            self.stderr.write(f"skipped {message}")
        for message in blank_courses:
            self.stdout.write(f"course has no code, stored blank: {message}")
        self.stdout.write(f"{len(responses)} valid, {len(skipped)} skipped, {len(blank_courses)} courses blanked.")

        if not responses:
            raise CommandError("Nothing to import.")
        # The old data all predates the new backend, so any row in its time
        # range means this file was imported already.
        newest = max(response.created_at for response in responses)
        if SatisfactionSurveyResponse.objects.filter(created_at__lte=newest).exists():
            raise CommandError("The database already has responses from this CSV's time range; was it imported already?")
        if dry_run:
            self.stdout.write("Dry run: nothing saved.")
            return
        SatisfactionSurveyResponse.objects.bulk_create(responses)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(responses)} responses."))
