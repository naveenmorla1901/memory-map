#apps/users/test.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth.models import User
from .models import UserProfile

class AuthenticationTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user_data = {
            'username': 'testuser',
            'password': 'TestPass123!',
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
        self.user = User.objects.create_user(
            username=self.user_data['username'],
            password=self.user_data['password'],
            email=self.user_data['email']
        )
        UserProfile.objects.create(user=self.user)

    def test_user_registration(self):
        """Test user registration process"""
        url = reverse('users:register')
        data = {
            'username': 'newuser',
            'password': 'NewPass123!',
            'password2': 'NewPass123!',
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'User'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('tokens', response.data)
        self.assertIn('user', response.data)
        self.assertIn('profile', response.data)

    def test_user_login(self):
        """Test user login process"""
        url = reverse('users:token_obtain_pair')
        data = {
            'username': self.user_data['username'],
            'password': self.user_data['password']
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)

    def test_password_change(self):
        """Test password change process"""
        # First login to get token
        login_url = reverse('users:token_obtain_pair')
        login_data = {
            'username': self.user_data['username'],
            'password': self.user_data['password']
        }
        response = self.client.post(login_url, login_data, format='json')
        token = response.data['access']

        # Try password change
        url = reverse('users:change_password')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        data = {
            'current_password': self.user_data['password'],
            'new_password': 'NewTestPass123!',
            'new_password2': 'NewTestPass123!'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)

    def test_get_user_data(self):
        """Test getting user data"""
        # First login to get token
        login_url = reverse('users:token_obtain_pair')
        login_data = {
            'username': self.user_data['username'],
            'password': self.user_data['password']
        }
        response = self.client.post(login_url, login_data, format='json')
        token = response.data['access']

        # Get user data
        url = reverse('users:user_data')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)
        self.assertIn('profile', response.data)