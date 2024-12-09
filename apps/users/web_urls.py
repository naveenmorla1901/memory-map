from django.urls import path
from . import views

app_name = 'users-web'

urlpatterns = [
    # Web views
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
]