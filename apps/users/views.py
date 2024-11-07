# apps/users/views.py
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.models import User
from .serializers import (
    MyTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
    UserProfileSerializer
)
from .models import UserProfile

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return UserProfile.objects.get(user=self.request.user)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_data(request):
    """Get user data and profile information"""
    user = request.user
    user_profile = UserProfile.objects.get(user=user)
    
    return Response({
        'user': UserSerializer(user).data,
        'profile': UserProfileSerializer(user_profile).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change user password"""
    user = request.user
    
    if not user.check_password(request.data.get('current_password')):
        return Response({
            'error': 'Current password is incorrect'
        }, status=status.HTTP_400_BAD_REQUEST)
        
    user.set_password(request.data.get('new_password'))
    user.save()
    
    return Response({
        'message': 'Password updated successfully'
    })