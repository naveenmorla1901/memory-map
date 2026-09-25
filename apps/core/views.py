# apps/core/views.py
import logging
from datetime import datetime

from django.conf import settings
from django.db.models import Q
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .instagram.analyzer import InstagramReelAnalyzer
from .models import Location, UserLocation
from .serializers import (
    LocationAnalysisSerializer,
    LocationSerializer,
    SavedLocationWriteSerializer,
    UserLocationSerializer,
)

logger = logging.getLogger(__name__)

__all__ = [
    'LocationViewSet',
    'UserLocationViewSet',
    'analyze_instagram_reel',
    'analyze_and_save_reel',
]


def _parse_instagram_date(date_str):
    """Best-effort parse of the date the analyzer scrapes off an Instagram page."""
    if not date_str:
        return None
    for fmt in ('%B %d, %Y', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


class LocationViewSet(viewsets.ModelViewSet):
    """The shared catalog of places (name/coordinates/category - not per-user data)."""
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Location.objects.none()

        queryset = Location.objects.filter(is_deleted=False)

        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__iexact=category)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(address__icontains=search)
            )

        return queryset

    def perform_destroy(self, instance):
        instance.soft_delete()


class UserLocationViewSet(viewsets.ModelViewSet):
    """
    A user's personal saved locations. Reads return the saved location
    together with its place data (nested `location`); writes accept a flat
    body covering both, since the app always edits them together.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return UserLocation.objects.none()
        if not self.request.user.is_authenticated:
            return UserLocation.objects.none()

        queryset = UserLocation.objects.filter(user=self.request.user).select_related('location')

        is_favorite = self.request.query_params.get('is_favorite')
        if is_favorite is not None:
            queryset = queryset.filter(is_favorite=is_favorite.lower() in ('1', 'true', 'yes'))

        return queryset

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return SavedLocationWriteSerializer
        return UserLocationSerializer

    @swagger_auto_schema(
        operation_description="List the current user's saved locations, with their custom preferences.",
        manual_parameters=[
            openapi.Parameter(
                'is_favorite', openapi.IN_QUERY,
                description="Filter to favorite locations",
                type=openapi.TYPE_BOOLEAN, required=False
            )
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = SavedLocationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_location = self._create_saved_location(request.user, serializer.validated_data)
        return Response(UserLocationSerializer(user_location).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = SavedLocationWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user_location = self._apply_saved_location_update(instance, serializer.validated_data)
        return Response(UserLocationSerializer(user_location).data)

    @staticmethod
    def _create_saved_location(user, data):
        location = Location.objects.create(
            name=data['name'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            description=data.get('description', ''),
            category=data.get('category') or 'uncategorized',
            address=data.get('address', ''),
            is_instagram_source=data.get('is_instagram_source', False),
            instagram_url=data.get('instagram_url', ''),
        )
        return UserLocation.objects.create(
            user=user,
            location=location,
            custom_name=data.get('custom_name', ''),
            custom_description=data.get('custom_description', ''),
            custom_category=data.get('custom_category', ''),
            notes=data.get('notes', ''),
            is_favorite=data.get('is_favorite', False),
            notify_enabled=data.get('notify_enabled', False),
            notify_radius=data.get('notify_radius', 1.0),
        )

    @staticmethod
    def _apply_saved_location_update(user_location, data):
        location = user_location.location
        for field in ('name', 'latitude', 'longitude', 'description', 'category', 'address',
                      'is_instagram_source', 'instagram_url'):
            if field in data:
                setattr(location, field, data[field])
        location.save()

        for field in ('custom_name', 'custom_description', 'custom_category', 'notes',
                      'is_favorite', 'notify_enabled', 'notify_radius'):
            if field in data:
                setattr(user_location, field, data[field])
        user_location.save()
        return user_location

    @action(detail=False, methods=['get'])
    def favorites(self, request):
        queryset = self.get_queryset().filter(is_favorite=True)
        serializer = UserLocationSerializer(queryset, many=True)
        return Response(serializer.data)


@swagger_auto_schema(
    method='post',
    operation_description=(
        "Analyze an Instagram reel URL and extract locations without saving them. "
        "If the URL was already analyzed, returns the previously saved locations instead."
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['url'],
        properties={'url': openapi.Schema(type=openapi.TYPE_STRING, description='Instagram reel URL')},
    ),
    responses={200: 'Success', 400: 'Bad Request - invalid URL or parsing error'},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_instagram_reel(request):
    serializer = LocationAnalysisSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    url = serializer.validated_data['url']

    existing = Location.objects.filter(instagram_url=url, is_deleted=False)
    if existing.exists():
        return Response({
            'status': 'existing',
            'locations': LocationSerializer(existing, many=True).data,
        })

    try:
        analyzer = InstagramReelAnalyzer(settings.GOOGLE_API_KEY)
        result = analyzer.analyze_reel(url)
    except Exception as e:
        logger.error(f"Instagram analysis error: {e}", exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    if not result or not result.get('locations'):
        return Response({'error': 'Could not extract any locations from this reel'},
                         status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'status': 'new',
        'locations': result['locations'],
        'url': url,
        'metadata': {
            'date_posted': result.get('date_posted'),
            'description': result.get('description'),
        },
    })


@swagger_auto_schema(
    method='post',
    operation_description="Analyze an Instagram reel URL and immediately save all extracted locations for the current user.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['url'],
        properties={
            'url': openapi.Schema(type=openapi.TYPE_STRING, description='Instagram reel URL'),
            'category': openapi.Schema(type=openapi.TYPE_STRING, description='Default category for all locations'),
            'is_favorite': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Mark all locations as favorite'),
            'notify_radius': openapi.Schema(type=openapi.TYPE_NUMBER, description='Notification radius in km'),
        },
    ),
    responses={200: 'Success', 400: 'Bad Request - invalid URL, parsing error, or nothing to save'},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_and_save_reel(request):
    url = request.data.get('url')
    if not url:
        return Response({'error': 'URL is required'}, status=status.HTTP_400_BAD_REQUEST)

    category = request.data.get('category', 'uncategorized')
    is_favorite = bool(request.data.get('is_favorite', False))
    try:
        notify_radius = float(request.data.get('notify_radius', 1.0))
    except (TypeError, ValueError):
        notify_radius = 1.0

    existing = Location.objects.filter(instagram_url=url, is_deleted=False)
    if existing.exists():
        saved = []
        for location in existing:
            user_location, _ = UserLocation.objects.get_or_create(
                user=request.user, location=location,
                defaults={'is_favorite': is_favorite, 'notify_radius': notify_radius},
            )
            saved.append(UserLocationSerializer(user_location).data)
        return Response({
            'status': 'existing',
            'saved_locations': saved,
            'metadata': {'total_saved': len(saved), 'instagram_url': url},
        })

    try:
        analyzer = InstagramReelAnalyzer(settings.GOOGLE_API_KEY)
        result = analyzer.analyze_reel(url)
    except Exception as e:
        logger.error(f"Instagram analysis error: {e}", exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    if not result or not result.get('locations'):
        return Response({'error': 'No locations found in reel'}, status=status.HTTP_400_BAD_REQUEST)

    saved = []
    for loc in result['locations']:
        if not isinstance(loc, dict):
            continue
        coordinates = loc.get('coordinates') or {}
        latitude, longitude = coordinates.get('latitude'), coordinates.get('longitude')
        if latitude is None or longitude is None:
            logger.warning(f"Skipping location without coordinates: {loc.get('name')}")
            continue

        location = Location.objects.create(
            name=loc.get('name', 'Unnamed Location'),
            latitude=latitude,
            longitude=longitude,
            description=result.get('description', ''),
            category=loc.get('category') or category,
            address=loc.get('name', ''),
            is_instagram_source=True,
            instagram_url=url,
            date_posted=_parse_instagram_date(result.get('date_posted')),
        )
        user_location = UserLocation.objects.create(
            user=request.user,
            location=location,
            is_favorite=is_favorite,
            notify_radius=notify_radius,
        )
        saved.append(UserLocationSerializer(user_location).data)

    if not saved:
        return Response({'error': 'No valid locations to save'}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'status': 'saved',
        'saved_locations': saved,
        'metadata': {'total_saved': len(saved), 'instagram_url': url},
    })
