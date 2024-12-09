#apps/core/middleware/firebase_auth.py
from firebase_admin import auth
from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
import logging

logger = logging.getLogger(__name__)

class FirebaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            return None

        try:
            # Extract the token
            id_token = auth_header.split(' ').pop()
            # Verify the token
            decoded_token = auth.verify_id_token(id_token)
            
            # Get or create user
            try:
                user = User.objects.get(username=decoded_token['uid'])
            except User.DoesNotExist:
                user = User.objects.create_user(
                    username=decoded_token['uid'],
                    email=decoded_token.get('email', ''),
                    password=None  # No password as using Firebase auth
                )
                logger.info(f"Created new user from Firebase: {user.username}")

            return (user, None)

        except Exception as e:
            logger.error(f"Firebase auth error: {str(e)}")
            raise AuthenticationFailed(str(e))

    def authenticate_header(self, request):
        return 'Bearer'