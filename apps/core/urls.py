from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [

    # Instagram analyzer endpoints
    path('analyze-reel/', views.analyze_instagram_reel, name='analyze-reel'),
    path('test-analyzer/', views.test_analyzer_page, name='test-analyzer'),
]