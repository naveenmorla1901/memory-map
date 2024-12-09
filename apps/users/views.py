# apps/users/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import (
    MyTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    UserProfileSerializer,
    PasswordChangeSerializer
)
import logging

logger = logging.getLogger(__name__)

# API Views
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'profile': UserProfileSerializer(user.userprofile).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_data(request):
    """Get user data and profile information"""
    try:
        return Response({
            'user': UserSerializer(request.user).data,
            'profile': UserProfileSerializer(request.user.userprofile).data
        })
    except Exception as e:
        logger.error(f"Error fetching user data: {str(e)}")
        return Response({
            'error': 'Unable to fetch user data'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change user password"""
    serializer = PasswordChangeSerializer(data=request.data)
    if serializer.is_valid():
        user = request.user
        if not user.check_password(serializer.validated_data['current_password']):
            return Response({
                'current_password': ['Wrong password.']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Generate new tokens
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Password updated successfully',
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    """Logout user by blacklisting the refresh token"""
    try:
        refresh_token = request.data.get('refresh_token')
        if not refresh_token:
            return Response({
                'error': 'Refresh token is required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({
            'message': 'Successfully logged out.'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return Response({
            'error': 'Invalid token.'
        }, status=status.HTTP_400_BAD_REQUEST)

# Web Views
def login_view(request):
    """Handle web login"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            next_url = request.GET.get('next', 'core:index')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'users/login.html')

def signup_view(request):
    """Handle web signup"""
    if request.method == 'POST':
        form = RegisterSerializer(data=request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect('core:index')
        else:
            messages.error(request, 'Please correct the errors below.')
    return render(request, 'users/signup.html')

@login_required
def logout_view(request):
    """Handle web logout"""
    auth_logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('core:index')