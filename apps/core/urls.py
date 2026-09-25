# apps/core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LocationViewSet,
    UserLocationViewSet,
    analyze_instagram_reel,
    analyze_and_save_reel,
)

app_name = 'core-api'

router = DefaultRouter()
router.register(r'locations', LocationViewSet, basename='location')
router.register(r'user-locations', UserLocationViewSet, basename='user-location')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),

    # Instagram Analysis
    path('analyze-reel/', analyze_instagram_reel, name='analyze-reel'),
    path('analyze-save-reel/', analyze_and_save_reel, name='analyze-save-reel'),
]
