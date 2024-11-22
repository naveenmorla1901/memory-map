# apps/core/tests/conftest.py

import pytest
import firebase_admin
from firebase_admin import credentials
from django.conf import settings
from apps.core.services.firebase_service import FirebaseService

@pytest.fixture(scope='session', autouse=True)
def setup_firebase():
    """Initialize Firebase for testing"""
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.FIREBASE_ADMIN_CREDENTIALS)
            firebase_admin.initialize_app(cred, {
                'databaseURL': settings.FIREBASE_DATABASE_URL
            })
    except Exception as e:
        pytest.fail(f"Failed to initialize Firebase: {e}")

@pytest.fixture(scope='function')
def firebase_service():
    """Provide FirebaseService instance"""
    return FirebaseService()

@pytest.fixture(autouse=True)
def cleanup_firebase(firebase_service):
    """Cleanup Firebase data after each test"""
    yield