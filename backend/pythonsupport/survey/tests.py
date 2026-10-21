from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone


from .models import SatisfactionSurveyResponse, SurveyLink, SupporterProblemLog

PASSWORD = 'hunter2'

VALID = {
    'student_number': 's123456', 'satisfaction': 5,
    'course_number': '02525 - Introduction to Mathematics and Technology',
    'building_number': '358', 'workshop': False, 'used_ai': True,
}


def without(key):
    return {k: v for k, v in VALID.items() if k != key}


@override_settings(SURVEY_PASSWORD=PASSWORD)
class SubmitResponseTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.token = self.get_token(self.client, PASSWORD).json()['csrfToken']

    def get_token(self, client, password):
        return client.post('/api/csrf/', {'password': password}, content_type='application/json')

    def post(self, data, client=None, token=None):
        return (client or self.client).post(
            '/api/responses/', data, content_type='application/json',
            headers={'X-CSRFToken': token or self.token},
        )

    def test_submission_needs_password_and_token(self):
        stranger = Client(enforce_csrf_checks=True)
        self.assertEqual(self.get_token(stranger, 'wrong').status_code, 403)
        # A self-made cookie/header pair passes Django's CSRF check on its own.
        stranger.cookies['csrftoken'] = 'a' * 32
        response = self.post(VALID, stranger, 'a' * 32)
        self.assertEqual(response.status_code, 403)
        self.assertIn('password', response.json()['error'])  # our gate, not CsrfViewMiddleware
        # Right session, missing token.
        self.assertEqual(self.client.post('/api/responses/', VALID, content_type='application/json').status_code, 403)
        self.assertFalse(SatisfactionSurveyResponse.objects.exists())

    def test_one_time_link(self):
        stranger = Client(enforce_csrf_checks=True)
        stranger.cookies['csrftoken'] = 'a' * 32
        self.assertEqual(stranger.post('/api/links/', headers={'X-CSRFToken': 'a' * 32}).status_code, 403)
        token = self.client.post('/api/links/', headers={'X-CSRFToken': self.token}).json()['token']

        student = Client(enforce_csrf_checks=True)  # no session, no CSRF token
        def use(data, token=token):
            return student.post('/api/responses/', {**data, 'token': token}, content_type='application/json')
        self.assertEqual(use({'ping': True}).status_code, 200)
        self.assertEqual(use(without('satisfaction')).status_code, 400)  # does not use the link up
        self.assertEqual(use({**VALID, 'building_number': None}).status_code, 201)
        self.assertEqual(SatisfactionSurveyResponse.objects.get().building_number, 'Online')
        self.assertEqual(use(VALID).status_code, 403)
        self.assertEqual(use({'ping': True}).status_code, 403)

        SurveyLink.objects.create(token='old', building_number='Online', single_use=True, expires_at=timezone.now())
        self.assertIn('expired', use(VALID, 'old').json()['error'])
        self.assertEqual(SatisfactionSurveyResponse.objects.count(), 1)

    def test_qr_code(self):
        def issue(data, client=self.client, csrf_token=self.token):
            return client.post('/api/qr-codes/', data, content_type='application/json', headers={'X-CSRFToken': csrf_token})
        stranger = Client(enforce_csrf_checks=True)
        stranger.cookies['csrftoken'] = 'a' * 32
        self.assertEqual(issue({'building_number': 358, 'valid_days': 7}, stranger, 'a' * 32).status_code, 403)
        self.assertIn('valid_days', issue({'building_number': 358, 'valid_days': 0}).json()['errors'])
        self.assertIn('building_number', issue({'building_number': 991, 'valid_days': 7}).json()['errors'])

        token = issue({'building_number': 358, 'valid_days': 7}).json()['token']
        link = SurveyLink.objects.get(token=token)
        self.assertAlmostEqual(link.expires_at, timezone.now() + timedelta(days=7), delta=timedelta(minutes=1))

        student = Client(enforce_csrf_checks=True)  # no session, no CSRF token
        def use():
            data = {**VALID, 'building_number': None, 'token': token}
            return student.post('/api/responses/', data, content_type='application/json')
        self.assertEqual(use().status_code, 201)
        self.assertEqual(use().status_code, 201)  # a QR code is not used up
        self.assertEqual(set(SatisfactionSurveyResponse.objects.values_list('building_number', flat=True)), {'358'})
        link.expires_at = timezone.now()
        link.save()
        self.assertEqual(use().status_code, 403)

    @override_settings(FRONTEND_ORIGINS=['http://localhost:5500'])
    def test_frontend_origin_gets_cors_headers(self):
        origin = {'Origin': 'http://localhost:5500'}
        preflight = self.client.options('/api/responses/', headers=origin)
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight['Access-Control-Allow-Origin'], 'http://localhost:5500')
        # CSRF rejections must be readable too, or the frontend sees a network error.
        rejected = self.client.post('/api/responses/', VALID, content_type='application/json', headers=origin)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected['Access-Control-Allow-Credentials'], 'true')
        other = self.client.options('/api/responses/', headers={'Origin': 'https://evil.example'})
        self.assertNotIn('Access-Control-Allow-Origin', other)

    def test_valid_submission_is_saved(self):
        response = self.post(VALID)
        self.assertEqual(response.status_code, 201)
        saved = SatisfactionSurveyResponse.objects.get()
        self.assertEqual(response.json()['id'], saved.pk)
        self.assertIs(saved.workshop, False)
        # The frontend sends null when the optional course is left empty.
        self.assertEqual(self.post({**VALID, 'course_number': None}).status_code, 201)

    def test_bad_payloads_are_rejected(self):
        for field, data in [
            ('workshop', without('workshop')),
            ('used_ai', without('used_ai')),
            ('course_number', {**VALID, 'course_number': 'fysik'}),
            ('satisfaction', {**VALID, 'satisfaction': 11}),
            ('student_number', {**VALID, 'student_number': '1234567'}),
            ('student_number', {**VALID, 'student_number': 'S123456'}),
            ('student_number', {**VALID, 'student_number': 's12345'}),
            ('username', {**without('student_number'), 'username': 'TJOH'}),
            ('__all__', without('student_number')),
            ('__all__', {**VALID, 'username': 'tjoh'}),
        ]:
            response = self.post(data)
            self.assertEqual(response.status_code, 400, field)
            self.assertIn(field, response.json()['errors'])
        self.assertFalse(SatisfactionSurveyResponse.objects.exists())


@override_settings(SURVEY_PASSWORD=PASSWORD)
class SupporterProblemLogTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        response = self.client.post(
            '/api/csrf/', {'password': PASSWORD}, content_type='application/json',
        )
        self.token = response.json()['csrfToken']

    def post(self, data, client=None, token=None):
        return (client or self.client).post(
            '/api/problem-logs/', data, content_type='application/json',
            headers={'X-CSRFToken': token or self.token},
        )

    def test_submission_needs_supporter_session_and_csrf_token(self):
        stranger = Client(enforce_csrf_checks=True)
        stranger.cookies['csrftoken'] = 'a' * 32
        response = self.post({'problems': ['Antivirus']}, stranger, 'a' * 32)
        self.assertEqual(response.status_code, 403)
        self.assertIn('password', response.json()['error'])
        self.assertEqual(
            self.client.post(
                '/api/problem-logs/', {'problems': ['Antivirus']},
                content_type='application/json',
            ).status_code,
            403,
        )
        self.assertFalse(SupporterProblemLog.objects.exists())

    def test_selected_problems_and_note_are_saved(self):
        response = self.post({
            'problems': ['Files and Folders', 'MS Start App'],
            'other': '  Conda environment was not activated.  ',
        })
        self.assertEqual(response.status_code, 201)
        saved = SupporterProblemLog.objects.get()
        self.assertEqual(response.json()['id'], saved.pk)
        self.assertIs(saved.files_and_folders, True)
        self.assertIs(saved.ms_start_app, True)
        self.assertIs(saved.antivirus, False)
        self.assertEqual(saved.other, 'Conda environment was not activated.')

    def test_other_text_can_be_submitted_by_itself(self):
        self.assertEqual(self.post({'other': 'A new problem'}).status_code, 201)
        saved = SupporterProblemLog.objects.get()
        self.assertEqual(saved.other, 'A new problem')
        self.assertIs(saved.starting_idle, False)

    def test_empty_or_unknown_problem_is_rejected(self):
        for data in [
            {},
            {'problems': [], 'other': '   '},
            {'problems': ['Not a real option']},
            {'problems': 'Antivirus'},
            {'problems': [], 'other': ['not', 'text']},
        ]:
            self.assertEqual(self.post(data).status_code, 400, data)
        self.assertFalse(SupporterProblemLog.objects.exists())
