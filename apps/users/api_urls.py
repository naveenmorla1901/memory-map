from django.urls import path

from . import views

app_name = 'users-api'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('token/', views.LoginView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', views.RefreshView.as_view(), name='token_refresh'),
    path('logout/', views.logout, name='logout'),
    path('me/', views.me, name='me'),
    path('change-password/', views.change_password, name='change_password'),
    path('password-reset/', views.password_reset, name='password_reset'),
]
