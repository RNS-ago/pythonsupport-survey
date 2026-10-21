import json
import secrets
from datetime import timedelta

from django import forms
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST

from .models import SatisfactionSurveyResponse, SupporterProblemLog, SurveyLink

ONE_TIME_LINK_LIFETIME = timedelta(hours=24)
# The old backend recorded one-time link submissions under this building too.
ONE_TIME_LINK_BUILDING = 'Online'
NEED_PASSWORD = "Request a CSRF token with the survey password first."
LINK_GONE = "This link has expired or was already used."
PROBLEM_FIELDS = {
    'Files and Folders': 'files_and_folders',
    'Trust issues VS Code': 'trust_issues_vs_code',
    'MS Powershell / Mini Forge Prompt': 'ms_powershell_mini_forge_prompt',
    'Starting Idle': 'starting_idle',
    'MS Start App': 'ms_start_app',
    'Antivirus': 'antivirus',
}


class SatisfactionSurveyResponseForm(forms.ModelForm):
    # The model allows used_ai empty for rows imported from the old backend;
    # new submissions must answer it.
    used_ai = forms.BooleanField(required=False)

    class Meta:
        model = SatisfactionSurveyResponse
        fields = [
            'student_number', 'username', 'satisfaction', 'course_number',
            'building_number', 'workshop', 'used_ai',
        ]

    def clean(self):
        # A missing checkbox means False to Django; for an API it means the
        # client forgot the answer, so require the key to be present.
        for name in ('workshop', 'used_ai'):
            if name not in self.data:
                self.add_error(name, "This field is required.")
        return super().clean()

class SupporterProblemLogForm(forms.ModelForm):
    class Meta:
        model = SupporterProblemLog
        fields = [*PROBLEM_FIELDS.values(), 'other']

    def clean(self):
        cleaned = super().clean()
        cleaned['other'] = (cleaned.get('other') or '').strip()
        if not cleaned['other'] and not any(cleaned.get(field) for field in PROBLEM_FIELDS.values()):
            raise forms.ValidationError("Select at least one problem or describe another problem.")
        return cleaned


class QrCodeForm(forms.Form):
    building_number = forms.IntegerField(min_value=0, max_value=990)  # the QR dialog's range
    valid_days = forms.IntegerField(min_value=1, max_value=365)


def read_json_object(request):
    """The request body as a dict, or None when it is not a JSON object."""
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None

# Exempt because the caller has no token yet; handing one out is the point.
@csrf_exempt
@require_POST
def request_csrf_token(request):
    try:
        password = json.loads(request.body)['password']
    except (ValueError, KeyError, TypeError):
        password = None
    expected = settings.SURVEY_PASSWORD
    if not (expected and password and constant_time_compare(password, expected)):
        return JsonResponse({'error': "Wrong password."}, status=403)

    request.session.cycle_key()
    # Django never checks that a CSRF cookie was issued by the server, so the
    # token alone proves nothing; this flag is what the password unlocks.
    request.session['survey_authorized'] = True
    return JsonResponse({'csrfToken': get_token(request)})


@require_POST
def issue_link(request):
    if not request.session.get('survey_authorized'):
        return JsonResponse({'error': NEED_PASSWORD}, status=403)
    return create_link(ONE_TIME_LINK_LIFETIME, building_number=ONE_TIME_LINK_BUILDING, single_use=True)


@require_POST
def issue_qr_code(request):
    if not request.session.get('survey_authorized'):
        return JsonResponse({'error': NEED_PASSWORD}, status=403)
    form = QrCodeForm(read_json_object(request) or {})
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    return create_link(
        timedelta(days=form.cleaned_data['valid_days']),
        building_number=str(form.cleaned_data['building_number']), single_use=False,
    )


def create_link(lifetime, **fields):
    now = timezone.now()
    SurveyLink.objects.filter(expires_at__lte=now).delete()  # dead links are never needed again
    link = SurveyLink.objects.create(token=secrets.token_urlsafe(), expires_at=now + lifetime, **fields)
    return JsonResponse({'token': link.token}, status=201)


# Exempt because a link's student has no session or CSRF token; the link token
# is their credential. Everyone else is CSRF-checked in submit_with_session.
@csrf_exempt
@require_POST
def submit_response(request):
    payload = read_json_object(request)
    if payload is None:
        return JsonResponse({'error': "Request body must be a JSON object."}, status=400)
    if payload.get('token'):
        return submit_with_link(payload)
    return submit_with_session(request, payload)


@csrf_protect
def submit_with_session(request, payload):
    if not request.session.get('survey_authorized'):
        return JsonResponse({'error': NEED_PASSWORD}, status=403)
    return save_response(payload)


def submit_with_link(payload):
    link = SurveyLink.objects.filter(token=str(payload['token']), expires_at__gt=timezone.now()).first()
    if link is None:
        return JsonResponse({'error': LINK_GONE}, status=403)
    if payload.get('ping'):  # the survey page checks its link before showing the form
        return JsonResponse({})
    data = {**payload, 'building_number': link.building_number}
    return save_response(data, link if link.single_use else None)


def save_response(data, single_use_link=None):
    form = SatisfactionSurveyResponseForm(data)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    with transaction.atomic():
        # Deleting the link uses it up; of two submits racing on one link, only one deletes it.
        if single_use_link is not None and not single_use_link.delete()[0]:
            return JsonResponse({'error': LINK_GONE}, status=403)
        return JsonResponse({'id': form.save().pk}, status=201)


@require_POST
@csrf_protect
def submit_supporter_problem(request):
    """Save one internal supporter problem log using the existing staff session."""
    if not request.session.get('survey_authorized'):
        return JsonResponse({'error': NEED_PASSWORD}, status=403)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': "Request body must be valid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'error': "Request body must be a JSON object."}, status=400)

    problems = payload.get('problems', [])
    if not isinstance(problems, list) or any(not isinstance(problem, str) for problem in problems):
        return JsonResponse({'errors': {'problems': ['Must be a list of problem names.']}}, status=400)
    unknown = sorted(set(problems) - PROBLEM_FIELDS.keys())
    if unknown:
        return JsonResponse({'errors': {'problems': [f"Unknown problem: {problem}" for problem in unknown]}}, status=400)

    other = payload.get('other', '')
    if not isinstance(other, str):
        return JsonResponse({'errors': {'other': ['Must be text.']}}, status=400)

    selected = set(problems)
    form = SupporterProblemLogForm({
        **{field: label in selected for label, field in PROBLEM_FIELDS.items()},
        'other': other,
    })
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    return JsonResponse({'id': form.save().pk}, status=201)
