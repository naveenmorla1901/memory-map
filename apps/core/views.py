import logging

from django.db import connection, transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .categories import CATEGORIES
from .models import SavedLocation
from .serializers import (
    BulkSavedLocationSerializer,
    CategorySerializer,
    GeocodeResultSerializer,
    LocationStatsSerializer,
    ReelAnalysisRequestSerializer,
    ReelAnalysisResponseSerializer,
    SavedLocationSerializer,
)
from .services import geocoding
from .services.reels import analyze_reel_for_user
from .throttles import GeocodeThrottle, ReelAnalysisThrottle

logger = logging.getLogger(__name__)

TRUTHY = ('1', 'true', 'yes')
ORDERINGS = {
    'newest': '-created_at',
    'oldest': 'created_at',
    'name': 'name',
    'updated': '-updated_at',
}


@extend_schema(
    parameters=[
        OpenApiParameter('category', str, description='Filter by category key'),
        OpenApiParameter('favorite', bool),
        OpenApiParameter('visited', bool),
        OpenApiParameter('search', str, description='Matches name, address, description or notes'),
        OpenApiParameter('ordering', str, enum=list(ORDERINGS)),
    ]
)
class SavedLocationViewSet(viewsets.ModelViewSet):
    """The signed-in user's saved places. Every query is scoped to the user."""
    serializer_class = SavedLocationSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return SavedLocation.objects.none()
        queryset = SavedLocation.objects.filter(user=self.request.user)
        if self.action != 'list':
            return queryset

        params = self.request.query_params
        if params.get('category'):
            queryset = queryset.filter(category=params['category'])
        if params.get('favorite') is not None:
            queryset = queryset.filter(is_favorite=params['favorite'].lower() in TRUTHY)
        if params.get('visited') is not None:
            queryset = queryset.filter(visited=params['visited'].lower() in TRUTHY)
        if params.get('search'):
            term = params['search'].strip()
            queryset = queryset.filter(
                Q(name__icontains=term) | Q(address__icontains=term)
                | Q(description__icontains=term) | Q(notes__icontains=term)
            )
        return queryset.order_by(ORDERINGS.get(params.get('ordering'), '-created_at'))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(request=BulkSavedLocationSerializer, responses={201: SavedLocationSerializer(many=True)})
    @action(detail=False, methods=['post'])
    def bulk(self, request):
        """Save several places at once (e.g. every place found in one reel)."""
        serializer = BulkSavedLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            created = [
                SavedLocation.objects.create(user=request.user, **item)
                for item in serializer.validated_data['locations']
            ]
        return Response(SavedLocationSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=LocationStatsSerializer)
    @action(detail=False, methods=['get'])
    def stats(self, request):
        queryset = SavedLocation.objects.filter(user=request.user)
        totals = queryset.aggregate(
            total=Count('id'),
            favorites=Count('id', filter=Q(is_favorite=True)),
            visited=Count('id', filter=Q(visited=True)),
            from_instagram=Count('id', filter=Q(source=SavedLocation.SOURCE_INSTAGRAM)),
        )
        by_category = dict(queryset.values_list('category').annotate(count=Count('id')).order_by())
        return Response({**totals, 'by_category': by_category})


@extend_schema(responses=CategorySerializer(many=True))
@api_view(['GET'])
@permission_classes([AllowAny])
def categories(request):
    return Response([
        {'key': key, 'label': label, 'description': description}
        for key, label, description in CATEGORIES
    ])


@extend_schema(request=ReelAnalysisRequestSerializer, responses=ReelAnalysisResponseSerializer)
@api_view(['POST'])
@throttle_classes([ReelAnalysisThrottle])
def analyze_reel(request):
    """
    Find the places an Instagram reel's caption mentions. A reel that can't
    be read (private, blocked, no caption, no place named) is a normal
    `manual_required` response rather than an error, so the app can move
    straight to manual search.
    """
    serializer = ReelAnalysisRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response(analyze_reel_for_user(serializer.validated_data['url'], request.user))



def _coordinate(value, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


@extend_schema(
    parameters=[
        OpenApiParameter('q', str, required=True),
        OpenApiParameter('lat', OpenApiTypes.FLOAT, description='Bias results toward this point'),
        OpenApiParameter('lon', OpenApiTypes.FLOAT),
    ],
    responses=GeocodeResultSerializer(many=True),
)
@api_view(['GET'])
@throttle_classes([GeocodeThrottle])
def geocode_search(request):
    query = request.query_params.get('q', '')
    lat = _coordinate(request.query_params.get('lat'), -90, 90)
    lon = _coordinate(request.query_params.get('lon'), -180, 180)
    near = (lat, lon) if lat is not None and lon is not None else None
    try:
        return Response(geocoding.search(query, near=near))
    except geocoding.GeocodingError as e:
        return Response({'detail': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)



@extend_schema(
    parameters=[
        OpenApiParameter('lat', OpenApiTypes.FLOAT, required=True),
        OpenApiParameter('lon', OpenApiTypes.FLOAT, required=True),
    ],
    responses=GeocodeResultSerializer,
)
@api_view(['GET'])
@throttle_classes([GeocodeThrottle])
def geocode_reverse(request):
    lat = _coordinate(request.query_params.get('lat'), -90, 90)
    lon = _coordinate(request.query_params.get('lon'), -180, 180)
    if lat is None or lon is None:
        return Response({'detail': 'Valid lat and lon are required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        result = geocoding.reverse(lat, lon)
    except geocoding.GeocodingError as e:
        return Response({'detail': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if not result:
        # Middle of the ocean, say - still a valid place to drop a pin.
        result = {'id': f'{lat},{lon}', 'name': 'Dropped pin', 'address': '',
                  'latitude': lat, 'longitude': lon, 'category': 'other'}
    return Response(result)



def healthz(request):
    """Liveness/readiness probe for the hosting platform."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        logger.exception('Health check database query failed')
        return JsonResponse({'status': 'error', 'database': 'unreachable'}, status=503)
    return JsonResponse({'status': 'ok'})
