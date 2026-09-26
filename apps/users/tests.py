import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import SavedLocation

User = get_user_model()
PASSWORD = 'Correct-Horse-9'


def make_user(email='alice@example.com', password=PASSWORD, **extra):
    return User.objects.create_user(username=email, email=email, password=password, **extra)


class AuthTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def login(self, email='alice@example.com', password=PASSWORD):
        return self.client.post('/api/v1/auth/token/', {'email': email, 'password': password}, format='json')

    def authenticate(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')


class RegisterTests(AuthTestCase):
    def test_register_returns_user_and_tokens(self):
        response = self.client.post('/api/v1/auth/register/', {
            'name': 'Alice Liddell', 'email': ' Alice@Example.com ', 'password': PASSWORD,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['user']['email'], 'alice@example.com')
        self.assertEqual(response.data['user']['name'], 'Alice Liddell')
        self.assertEqual(response.data['user']['first_name'], 'Alice')
        self.assertEqual(set(response.data['tokens']), {'access', 'refresh'})

        self.authenticate(response.data['tokens']['access'])
        self.assertEqual(self.client.get('/api/v1/auth/me/').data['email'], 'alice@example.com')

    def test_duplicate_email_is_rejected_case_insensitively(self):
        make_user()
        response = self.client.post('/api/v1/auth/register/', {
            'name': 'Other', 'email': 'ALICE@example.com', 'password': PASSWORD,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data['errors'])
        self.assertTrue(response.data['detail'])

    def test_weak_password_is_rejected(self):
        response = self.client.post('/api/v1/auth/register/', {
            'name': 'Alice', 'email': 'new@example.com', 'password': '123',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data['errors'])


class LoginTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user(first_name='Alice')

    def test_login_with_email_any_case(self):
        response = self.login('ALICE@example.com')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['user']['email'], 'alice@example.com')
        self.assertIn('access', response.data)

    def test_wrong_password_has_a_friendly_message(self):
        response = self.login(password='wrong')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['detail'], 'Incorrect email or password.')

    def test_unknown_email_gets_the_same_message(self):
        response = self.login('nobody@example.com')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data['detail'], 'Incorrect email or password.')

    def test_refresh_rotates_and_logout_revokes(self):
        refresh = self.login().data['refresh']
        rotated = self.client.post('/api/v1/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(rotated.status_code, 200)
        new_refresh = rotated.data['refresh']
        self.assertNotEqual(new_refresh, refresh)
        # The rotated-out token is blacklisted.
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': refresh}, format='json').status_code, 401)

        self.assertEqual(self.client.post('/api/v1/auth/logout/', {'refresh': new_refresh}, format='json').status_code, 204)
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': new_refresh}, format='json').status_code, 401)

    def test_logout_is_idempotent(self):
        self.assertEqual(self.client.post('/api/v1/auth/logout/', {'refresh': 'garbage'}, format='json').status_code, 204)
        self.assertEqual(self.client.post('/api/v1/auth/logout/', {}, format='json').status_code, 204)

    def test_login_is_throttled(self):
        statuses = [self.login(password='wrong').status_code for _ in range(12)]
        self.assertEqual(statuses[-1], 429)


class ProfileTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user(first_name='Alice')
        self.authenticate(self.login().data['access'])

    def test_update_name_and_email(self):
        response = self.client.patch('/api/v1/auth/me/', {'name': 'Alice Kingsleigh', 'email': 'ak@example.com'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['name'], 'Alice Kingsleigh')
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, 'Kingsleigh')
        self.assertEqual(self.user.username, 'ak@example.com')
        self.assertEqual(self.login('ak@example.com').status_code, 200)

    def test_cannot_take_someone_elses_email(self):
        make_user('bob@example.com')
        response = self.client.patch('/api/v1/auth/me/', {'email': 'bob@example.com'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_change_password_signs_out_other_sessions(self):
        other_device_refresh = self.login().data['refresh']
        response = self.client.post('/api/v1/auth/change-password/', {
            'current_password': PASSWORD, 'new_password': 'Another-Strong-7',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': other_device_refresh}, format='json').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': response.data['tokens']['refresh']}, format='json').status_code, 200)
        self.assertEqual(self.login(password='Another-Strong-7').status_code, 200)

    def test_change_password_requires_current_password(self):
        response = self.client.post('/api/v1/auth/change-password/', {
            'current_password': 'wrong', 'new_password': 'Another-Strong-7',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_delete_account_requires_password_and_removes_everything(self):
        SavedLocation.objects.create(user=self.user, name='x', latitude=1, longitude=1)
        self.assertEqual(self.client.delete('/api/v1/auth/me/', {'password': 'wrong'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete('/api/v1/auth/me/', {'password': PASSWORD}, format='json').status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(SavedLocation.objects.count(), 0)


@override_settings(PUBLIC_BASE_URL='https://memorymap.example.com')
class PasswordResetTests(AuthTestCase):
    def test_sends_a_working_reset_link(self):
        make_user()
        response = self.client.post('/api/v1/auth/password-reset/', {'email': 'alice@example.com'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        link = re.search(r'https://memorymap\.example\.com(/reset/[^\s]+/)', body).group(1)

        form_page = self.client.get(link, follow=True)
        self.assertEqual(form_page.status_code, 200)
        set_password_url = form_page.redirect_chain[-1][0] if form_page.redirect_chain else link
        done = self.client.post(set_password_url, {
            'new_password1': 'Brand-New-Pass-4', 'new_password2': 'Brand-New-Pass-4',
        })
        self.assertRedirects(done, '/reset/done/')
        self.assertEqual(self.login(password='Brand-New-Pass-4').status_code, 200)

    def test_unknown_email_gets_the_same_response_and_no_mail(self):
        make_user()
        known = self.client.post('/api/v1/auth/password-reset/', {'email': 'alice@example.com'}, format='json')
        unknown = self.client.post('/api/v1/auth/password-reset/', {'email': 'ghost@example.com'}, format='json')
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)


class WebDeleteAccountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()

    def post(self, password=PASSWORD, **extra):
        return self.client.post('/delete-account/', {
            'email': 'alice@example.com', 'password': password, 'confirm': 'on', **extra,
        })

    def test_deletes_with_correct_credentials(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'deleted')
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_wrong_password_keeps_the_account(self):
        self.assertContains(self.post('wrong'), 'do not match')
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_requires_confirmation(self):
        response = self.client.post('/delete-account/', {'email': 'alice@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_rate_limited_after_repeated_failures(self):
        for _ in range(10):
            self.post('wrong')
        self.assertContains(self.post(), 'Too many attempts')
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
