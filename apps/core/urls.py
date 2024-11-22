# apps/core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LocationViewSet,
    UserLocationViewSet,
    analyze_instagram_reel,
    test_firebase_connection,
    test_auth,
    sync_to_firebase,
    sync_from_firebase,
    analyze_and_save_reel
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
    
    # Firebase Sync
    path('sync/to-firebase/', sync_to_firebase, name='sync-to-firebase'),
    path('sync/from-firebase/', sync_from_firebase, name='sync-from-firebase'),
    
    # Testing and Verification
    path('test-firebase/', test_firebase_connection, name='test-firebase-connection'),
    path('test-auth/', test_auth, name='test-auth'),
]