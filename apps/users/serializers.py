from django.contrib.auth import get_user_model, password_validation
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


def split_name(name: str):
    parts = ' '.join((name or '').split()).split(' ', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''


def email_in_use(email: str, exclude_pk=None) -> bool:
    queryset = User.objects.filter(email__iexact=email)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.exists()


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'name', 'first_name', 'last_name', 'date_joined')
        read_only_fields = fields

    def get_name(self, user) -> str:
        return user.get_full_name() or user.email.split('@')[0]


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if email_in_use(value):
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Please enter your name.')
        return value

    def validate(self, attrs):
        first_name, last_name = split_name(attrs['name'])
        candidate = User(username=attrs['email'], email=attrs['email'], first_name=first_name, last_name=last_name)
        try:
            password_validation.validate_password(attrs['password'], candidate)
        except Exception as e:
            raise serializers.ValidationError({'password': list(getattr(e, 'messages', [str(e)]))})
        return attrs

    def create(self, validated_data):
        first_name, last_name = split_name(validated_data['name'])
        return User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=first_name,
            last_name=last_name,
        )


class ProfileUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False, trim_whitespace=True)
    email = serializers.EmailField(max_length=254, required=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if email_in_use(value, exclude_pk=self.instance.pk):
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Name cannot be blank.')
        return value

    def update(self, user, validated_data):
        if 'name' in validated_data:
            user.first_name, user.last_name = split_name(validated_data['name'])
        if 'email' in validated_data and validated_data['email'] != user.email:
            if user.username.lower() == user.email.lower():
                user.username = validated_data['email']
            user.email = validated_data['email']
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Your current password is incorrect.')
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context['request'].user)
        return value


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False)

    def validate_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Incorrect password.')
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Accepts `email` (or the legacy `username` field) plus `password`."""

    default_error_messages = {'no_active_account': 'Incorrect email or password.'}

    def __init__(self, *args, **kwargs):
        data = kwargs.get('data')
        if data is not None and 'username' not in data and 'email' in data:
            data = dict(data.items())
            data['username'] = data['email']
            kwargs['data'] = data
        super().__init__(*args, **kwargs)

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data
