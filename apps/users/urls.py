from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'users'

urlpatterns = [
    # API endpoints
    path('token/', views.MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('me/', views.get_user_data, name='user_data'),
    path('change-password/', views.change_password, name='change-password'),
    path('logout/', views.logout, name='logout'),
    
    # Web views
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
]