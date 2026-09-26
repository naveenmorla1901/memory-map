from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameModelBackend(ModelBackend):
    """Sign in with either an email address or a username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        User = get_user_model()
        identifier = username.strip()
        user = (
            User.objects.filter(email__iexact=identifier).order_by('id').first()
            or User.objects.filter(username__iexact=identifier).first()
        )
        if user is None:
            # Hash anyway so "no such account" takes as long as "wrong
            # password" - otherwise response timing reveals which emails exist.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
