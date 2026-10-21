from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

student_number_format = RegexValidator(r'^s[0-9]{6}\Z', "Student number must be a lowercase 's' followed by 6 digits.")
username_format = RegexValidator(r'^[a-z]+\Z', "Username must be lowercase letters (staff initials).")
course_number_format = RegexValidator(r'^[0-9]{5}\b', "Course must start with its 5-digit course number.")


class SatisfactionSurveyResponse(models.Model):
    """One submitted survey. Rows imported from the old backend may lack course and used_ai."""

    # Students give a student number, staff give their initials; exactly one is set.
    student_number = models.CharField(max_length=7, blank=True, validators=[student_number_format])
    username = models.CharField(max_length=32, blank=True, validators=[username_format])
    satisfaction = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)])
    course_number = models.CharField(max_length=100, blank=True, validators=[course_number_format])
    building_number = models.CharField(max_length=10)
    workshop = models.BooleanField()
    used_ai = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(student_number='') ^ models.Q(username=''),
                name='student_number_xor_username',
                violation_error_message="Give either a student number or a username, not both.",
            ),
        ]

    def __str__(self):
        return f"#{self.pk} {self.student_number or self.username}"


class SurveyLink(models.Model):
    """A survey link a supporter hands out: a one-time link for Discord, or a QR code for a building.

    Responses through a link get the link's building. A single-use link is deleted once used.
    """

    token = models.CharField(max_length=43, primary_key=True)
    building_number = models.CharField(max_length=10)
    single_use = models.BooleanField()
    expires_at = models.DateTimeField()


class SupporterProblemLog(models.Model):
    """Log of problems reported by supporters."""

    files_and_folders = models.BooleanField(default=False)
    trust_issues_vs_code = models.BooleanField(default=False)
    ms_powershell_mini_forge_prompt = models.BooleanField(default=False)
    starting_idle = models.BooleanField(default=False)
    ms_start_app = models.BooleanField(default=False)
    antivirus = models.BooleanField(default=False)
    other = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Problem log #{self.pk}"
