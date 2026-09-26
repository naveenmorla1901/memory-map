from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'core-api'

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register(r'locations', views.SavedLocationViewSet, basename='location')

urlpatterns = [
    path('', include(router.urls)),
    path('categories/', views.categories, name='categories'),
    path('reels/analyze/', views.analyze_reel, name='analyze-reel'),
    path('geocode/search/', views.geocode_search, name='geocode-search'),
    path('geocode/reverse/', views.geocode_reverse, name='geocode-reverse'),
]
