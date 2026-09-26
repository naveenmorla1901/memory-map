import logging
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.db import transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.throttles import AuthThrottle

from .serializers import (
    ChangePasswordSerializer,
    DeleteAccountSerializer,
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)

TokenPairSerializer = inline_serializer('TokenPair', {'access': serializers.CharField(), 'refresh': serializers.CharField()})
AuthResponseSerializer = inline_serializer('AuthResponse', {'user': UserSerializer(), 'tokens': TokenPairSerializer})


def tokens_for(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


def revoke_all_tokens(user):
    """Blacklist every outstanding refresh token - signs the user out everywhere."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [AuthThrottle]


class RefreshView(TokenRefreshView):
    throttle_classes = [AuthThrottle]


@extend_schema(request=RegisterSerializer, responses={201: AuthResponseSerializer})
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response({'user': UserSerializer(user).data, 'tokens': tokens_for(user)}, status=status.HTTP_201_CREATED)


@extend_schema(methods=['GET'], responses=UserSerializer)
@extend_schema(methods=['PATCH'], request=ProfileUpdateSerializer, responses=UserSerializer)
@extend_schema(methods=['DELETE'], request=DeleteAccountSerializer, responses={204: None})
@api_view(['GET', 'PATCH', 'DELETE'])
def me(request):
    user = request.user
    if request.method == 'GET':
        return Response(UserSerializer(user).data)

    if request.method == 'PATCH':
        serializer = ProfileUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(user).data)

    # DELETE: permanently delete the account and everything saved in it.
    # Required by the App Store / Play Store for apps with sign-up.
    serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        revoke_all_tokens(user)
        user.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=ChangePasswordSerializer, responses=inline_serializer('ChangePasswordResponse', {'tokens': TokenPairSerializer}))
@api_view(['POST'])
@throttle_classes([AuthThrottle])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    user = request.user
    user.set_password(serializer.validated_data['new_password'])
    user.save(update_fields=['password'])
    # Sign out every other device; this one gets fresh tokens.
    revoke_all_tokens(user)
    return Response({'tokens': tokens_for(user)})


@extend_schema(request=LogoutSerializer, responses={204: None})
@api_view(['POST'])
@permission_classes([AllowAny])  # Holding the refresh token is the proof; the access token may have expired.
def logout(request):
    refresh = request.data.get('refresh') or request.data.get('refresh_token')
    if refresh:
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            pass  # Already expired/blacklisted - the goal (signed out) is met.
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=PasswordResetRequestSerializer, responses=inline_serializer('PasswordResetResponse', {'detail': serializers.CharField()}))
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def password_reset(request):
    """
    Emails a reset link if the address has an account. Always responds the
    same way, so this can't be used to discover which emails are registered.
    """
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    form = PasswordResetForm({'email': serializer.validated_data['email']})
    if form.is_valid():
        base = urlparse(settings.PUBLIC_BASE_URL)
        try:
            form.save(
                domain_override=base.netloc,
                use_https=base.scheme == 'https',
                subject_template_name='registration/password_reset_subject.txt',
                email_template_name='registration/password_reset_email.txt',
                html_email_template_name='registration/password_reset_email.html',
                from_email=settings.DEFAULT_FROM_EMAIL,
            )
        except Exception:
            logger.exception('Failed to send password reset email')

    return Response({'detail': "If an account exists for that email, we've sent a link to reset your password."})
