# app/core/views.py
from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from django.db.models import Q
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Location, UserLocation
from .serializers import LocationSerializer, UserLocationSerializer, LocationAnalysisSerializer
from .instagram.analyzer import InstagramReelAnalyzer
import logging
from rest_framework.response import Response
from .services.sync_service import SyncService
import firebase_admin
from firebase_admin import auth
from rest_framework import viewsets, status
from .services.firebase_service import FirebaseService, FirebaseServiceError
from asgiref.sync import async_to_sync
from datetime import datetime

logger = logging.getLogger(__name__)

__all__ = [
    'LocationViewSet',
    'UserLocationViewSet',
    'analyze_instagram_reel',
    'test_firebase_connection',
    'test_auth',
    'sync_to_firebase',
    'sync_from_firebase'
]
# Define reusable response schemas
location_response_schema = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'id': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
        'name': openapi.Schema(type=openapi.TYPE_STRING),
        'latitude': openapi.Schema(type=openapi.TYPE_NUMBER, format=openapi.FORMAT_FLOAT),
        'longitude': openapi.Schema(type=openapi.TYPE_NUMBER, format=openapi.FORMAT_FLOAT),
        'description': openapi.Schema(type=openapi.TYPE_STRING),
        'category': openapi.Schema(type=openapi.TYPE_STRING),
        'address': openapi.Schema(type=openapi.TYPE_STRING),
        'is_instagram_source': openapi.Schema(type=openapi.TYPE_BOOLEAN),
        'instagram_url': openapi.Schema(type=openapi.TYPE_STRING),
        'created_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
        'updated_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
    }
)

class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer
    # permission_classes = [IsAuthenticated]
    permission_classes = [AllowAny] 
    firebase_service = FirebaseService()

    @swagger_auto_schema(
        operation_description="List all locations with optional filtering",
        manual_parameters=[
            openapi.Parameter(
                'category',
                openapi.IN_QUERY,
                description="Filter by category",
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                'search',
                openapi.IN_QUERY,
                description="Search in name, description, and address",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={
            200: openapi.Response(
                description="Successful response",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Unique identifier for the location",
                                example="550e8400-e29b-41d4-a716-446655440000"
                            ),
                            'name': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Name of the location",
                                example="Grand Canyon"
                            ),
                            'latitude': openapi.Schema(
                                type=openapi.TYPE_NUMBER,
                                description="Latitude coordinate",
                                example=36.0544
                            ),
                            'longitude': openapi.Schema(
                                type=openapi.TYPE_NUMBER,
                                description="Longitude coordinate",
                                example=-112.1401
                            ),
                            'description': openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Location description",
                                example="Beautiful view point of the canyon"
                            ),
                            'user_location': openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'custom_name': openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description="User's custom name for location"
                                    ),
                                    'is_favorite': openapi.Schema(
                                        type=openapi.TYPE_BOOLEAN,
                                        description="Whether location is marked as favorite"
                                    ),
                                    'notify_radius': openapi.Schema(
                                        type=openapi.TYPE_NUMBER,
                                        description="Notification radius in kilometers"
                                    )
                                }
                            )
                        }
                    )
                ),
                examples={
                    'application/json': [
                        {
                            'id': '550e8400-e29b-41d4-a716-446655440000',
                            'name': 'Grand Canyon',
                            'latitude': 36.0544,
                            'longitude': -112.1401,
                            'description': 'Beautiful view point',
                            'user_location': {
                                'custom_name': 'My Favorite Spot',
                                'is_favorite': True,
                                'notify_radius': 1.0
                            }
                        }
                    ]
                }
            ),
            401: 'Authentication credentials were not provided',
            404: 'Not found',
            500: 'Internal server error'
        }
    )
    @action(detail=False, methods=['GET'])
    def search(self, request):
        """Search locations by query"""
        try:
            query = request.query_params.get('query', '')
            
            @async_to_sync
            async def search_locations():
                return await self.firebase_service.search_locations(
                    query=query,
                    user_id=str(request.user.id)
                )

            results = search_locations()
            return Response(results)
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['POST'])
    def add_from_search(self, request):
        """Add location from search results"""
        try:
            @async_to_sync
            async def save_searched_location():
                location_data = {
                    **request.data,
                    'user_id': str(request.user.id),
                    'source_type': 'search',
                    'category': request.data.get('category', 'uncategorized')
                }
                return await self.firebase_service.save_location(location_data)

            location_id, location = save_searched_location()
            return Response({
                'id': location_id,
                'data': location
            })
        except Exception as e:
            logger.error(f"Error saving searched location: {str(e)}")
            return Response({'error': str(e)}, status=400)
    @action(detail=False)
    async def nearby(self, request):
        """Find nearby locations within radius"""
        lat = float(request.query_params.get('lat'))
        lng = float(request.query_params.get('lng'))
        radius = float(request.query_params.get('radius', 1.0))
        
        locations = await self.firebase_service.get_locations_in_radius(
            lat, lng, radius
        )
        return Response(locations)

    @action(detail=True)
    async def share(self, request, pk):
        """Share location with other users"""
        users = request.data.get('users', [])
        await self.firebase_service.share_location(pk, users)
        return Response({'status': 'shared'})
    

    def list(self, request):
        """List user locations with Firebase integration"""
        try:
            @async_to_sync
            async def get_locations():
                user_id = str(request.user.id)
                return await self.firebase_service.get_user_locations(user_id)

            locations = get_locations()
            return Response(locations)
        except Exception as e:
            logger.error(f"Error fetching user locations: {str(e)}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def update(self, request, pk=None):
        """Update location"""
        try:
            @async_to_sync
            async def update_location():
                return await self.firebase_service.update_location(
                    pk, 
                    str(request.user.id), 
                    request.data
                )

            updated_location = update_location()
            return Response(updated_location)

        except Exception as e:
            logger.error(f"Error updating location: {str(e)}", exc_info=True)
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


    def create(self, request):
        """Create a new location"""
        try:
            @async_to_sync
            async def save_location():
                location_data = {
                    **request.data,
                    'user_id': str(request.user.id)
                }
                return await self.firebase_service.save_location(location_data)

            location_id, location = save_location()
            return Response({
                'id': location_id,
                'message': 'Location created successfully',
                'data': location
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating location: {str(e)}", exc_info=True)
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def analyze_reel(self, request):
        """Your existing analyze_reel implementation"""
        pass
    def get_queryset(self):
        return Location.objects.all()

    def destroy(self, request, pk=None):
        """Delete location"""
        try:
            @async_to_sync
            async def delete_location():
                return await self.firebase_service.delete_location(
                    pk, 
                    str(request.user.id)
                )

            delete_location()
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error deleting location: {str(e)}", exc_info=True)
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'])
    def me(self, request):
        """Get current user's locations"""
        try:
            @async_to_sync
            async def get_my_locations():
                return await self.firebase_service.get_user_locations(
                    str(request.user.id)
                )

            locations = get_my_locations()
            return Response(locations)

        except Exception as e:
            logger.error(f"Error fetching user locations: {str(e)}", exc_info=True)
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    

class UserLocationViewSet(viewsets.ModelViewSet):
    serializer_class = UserLocationSerializer
    permission_classes = [IsAuthenticated]

    

    def get_queryset(self):
        """Get queryset with swagger schema generation handling"""
        # Check if this is a schema generation request
        if getattr(self, 'swagger_fake_view', False):
            # Return empty queryset for schema generation
            return UserLocation.objects.none()
            
        # Normal request handling
        if not self.request.user.is_authenticated:
            return UserLocation.objects.none()
            
        return UserLocation.objects.filter(user=self.request.user)
    @swagger_auto_schema(
        operation_description="""
        List user's saved locations with custom preferences.
        
        Returns:
        - Custom names and descriptions
        - Favorite status
        - Notification settings
        - Original location data
        """,
        manual_parameters=[
            openapi.Parameter(
                'is_favorite',
                openapi.IN_QUERY,
                description="Filter favorite locations",
                type=openapi.TYPE_BOOLEAN,
                required=False
            )
        ],
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_STRING),
                            'user_id': openapi.Schema(type=openapi.TYPE_STRING),
                            'location_id': openapi.Schema(type=openapi.TYPE_STRING),
                            'custom_name': openapi.Schema(type=openapi.TYPE_STRING),
                            'custom_description': openapi.Schema(type=openapi.TYPE_STRING),
                            'category': openapi.Schema(type=openapi.TYPE_STRING),
                            'is_favorite': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'notify_radius': openapi.Schema(type=openapi.TYPE_NUMBER),
                            'notifications_enabled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'saved_at': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
                            'last_updated': openapi.Schema(type=openapi.TYPE_STRING, format='date-time')
                        }
                    )
                )
            ),
            401: 'Unauthorized'
        }
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.list(request)
    @action(detail=False, methods=['get'])
    def favorites(self, request):
        queryset = self.get_queryset().filter(is_favorite=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


@swagger_auto_schema(
    method='post',
    operation_description="""
    Analyze Instagram reel URL and extract locations without saving.
    
    This endpoint will:
    1. Check if URL already exists in database
    2. If new URL, extract locations from description
    3. Return locations without saving
    """,
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['url'],
        properties={
            'url': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Instagram reel URL',
                example='https://www.instagram.com/reel/ABC123/'
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Success",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        enum=['existing', 'new'],
                        description="Whether URL was previously analyzed"
                    ),
                    'locations': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'name': openapi.Schema(type=openapi.TYPE_STRING),
                                'type': openapi.Schema(type=openapi.TYPE_STRING),
                                'coordinates': openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                                        'longitude': openapi.Schema(type=openapi.TYPE_NUMBER)
                                    }
                                ),
                                'category': openapi.Schema(type=openapi.TYPE_STRING)
                            }
                        )
                    ),
                    'url': openapi.Schema(type=openapi.TYPE_STRING),
                    'metadata': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'date_posted': openapi.Schema(type=openapi.TYPE_STRING),
                            'description': openapi.Schema(type=openapi.TYPE_STRING)
                        }
                    )
                }
            ),
            examples={
                'application/json': {
                    'status': 'new',
                    'locations': [
                        {
                            'name': 'Grand Canyon National Park',
                            'type': 'national_park',
                            'coordinates': {
                                'latitude': 36.0544,
                                'longitude': -112.1401
                            },
                            'category': 'nature'
                        }
                    ],
                    'url': 'https://www.instagram.com/reel/ABC123/',
                    'metadata': {
                        'date_posted': '2024-11-19',
                        'description': 'Beautiful day at the Grand Canyon!'
                    }
                }
            }
        ),
        400: 'Bad Request - Invalid URL or parsing error',
        500: 'Server Error - Analysis failed'
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_instagram_reel(request):
    """Analyze Instagram reel URL and extract/save locations"""
    try:
        serializer = LocationAnalysisSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        url = serializer.validated_data['url']
        firebase_service = FirebaseService()
        
        @async_to_sync
        async def analyze_only():
            # Check existing first
            existing = await firebase_service.get_locations_by_instagram_url(url)
            if existing:
                return {
                    'status': 'existing',
                    'locations': existing
                }
            
            # Analyze new
            analyzer = InstagramReelAnalyzer(settings.GOOGLE_API_KEY)
            result = analyzer.analyze_reel(url)
            
            if not result or 'locations' not in result:
                raise ValueError("Invalid analyzer result")
                
            return {
                'status': 'new',
                'locations': result['locations'],
                'url': url,
                'metadata': {
                    'date_posted': result.get('date_posted'),
                    'description': result.get('description')
                }
            }

        result = analyze_only()
        return Response(result)
        
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        return Response({'error': str(e)}, status=400)
@swagger_auto_schema(
    method='post',
    operation_description="""
    Analyze Instagram reel URL and immediately save extracted locations.
    
    This endpoint will:
    1. Extract locations from Instagram reel
    2. Save all extracted locations
    3. Create user location references
    """,
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['url'],  # Only specify required fields in this array
        properties={
            'url': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Instagram reel URL',
                example='https://www.instagram.com/reel/ABC123/'
            ),
            'category': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Default category for all locations'
            ),
            'is_favorite': openapi.Schema(
                type=openapi.TYPE_BOOLEAN,
                description='Mark all locations as favorite',
                default=False
            ),
            'notify_radius': openapi.Schema(
                type=openapi.TYPE_NUMBER,
                description='Notification radius in km',
                default=1.0
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Success",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'saved_locations': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_STRING),
                                'name': openapi.Schema(type=openapi.TYPE_STRING),
                                'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'longitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'description': openapi.Schema(type=openapi.TYPE_STRING),
                                'category': openapi.Schema(type=openapi.TYPE_STRING),
                                'is_instagram_source': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'instagram_url': openapi.Schema(type=openapi.TYPE_STRING),
                                'user_location': openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'is_favorite': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                        'notify_radius': openapi.Schema(type=openapi.TYPE_NUMBER)
                                    }
                                )
                            }
                        )
                    ),
                }
            ),
            examples={
                'application/json': {
                    'saved_locations': [
                        {
                            'id': 'loc_123',
                            'name': 'Grand Canyon',
                            'latitude': 36.0544,
                            'longitude': -112.1401,
                            'category': 'nature',
                            'is_instagram_source': True,
                            'user_location': {
                                'is_favorite': False,
                                'notify_radius': 1.0
                            }
                        }
                    ],
                    'metadata': {
                        'total_saved': 1,
                        'instagram_url': 'https://www.instagram.com/reel/ABC123/',
                        'date_processed': '2024-11-19T12:00:00Z'
                    }
                }
            }
        ),
        400: 'Bad Request - Invalid URL or parsing error',
        500: 'Server Error - Save failed'
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_and_save_reel(request):
    try:
        url = request.data.get('url')
        if not url:
            return Response({'error': 'URL is required'}, status=400)
            
        category = request.data.get('category', 'uncategorized')
        is_favorite = request.data.get('is_favorite', False)
        notify_radius = float(request.data.get('notify_radius', 1.0))
        
        firebase_service = FirebaseService()
        
        @async_to_sync
        async def process_and_save():
            # First check if URL exists
            existing = await firebase_service.get_locations_by_instagram_url(url)
            if existing:
                return {
                    'status': 'existing',
                    'saved_locations': existing,
                    'metadata': {
                        'total_saved': len(existing),
                        'instagram_url': url,
                        'date_processed': datetime.now().isoformat()
                    }
                }
            
            # Analyze new URL
            analyzer = InstagramReelAnalyzer(settings.GOOGLE_API_KEY)
            result = analyzer.analyze_reel(url)
            
            logger.debug(f"Analyzer result: {result}")  # Debug log
            
            if not result or not isinstance(result, dict):
                raise ValueError("Invalid analyzer result format")
                
            locations = result.get('locations', [])
            if not locations:
                raise ValueError("No locations found in reel")
            
            # Prepare locations with user settings
            locations_to_save = []
            for loc in locations:
                if not isinstance(loc, dict):
                    logger.warning(f"Skipping invalid location data: {loc}")
                    continue
                    
                loc_data = {
                    **loc,  # Original location data
                    'latitude': loc.get('coordinates', {}).get('latitude') if loc.get('coordinates') else None,
                    'longitude': loc.get('coordinates', {}).get('longitude') if loc.get('coordinates') else None,
                    'user_settings': {
                        'is_favorite': is_favorite,
                        'notify_radius': notify_radius,
                        'category': category
                    }
                }
                locations_to_save.append(loc_data)
            
            if not locations_to_save:
                raise ValueError("No valid locations to save")
            
            # Save all locations
            saved = await firebase_service.save_instagram_locations(
                locations=locations_to_save,
                user_id=str(request.user.id),
                instagram_url=url
            )
            
            return {
                'status': 'saved',
                'saved_locations': saved,
                'metadata': {
                    'total_saved': len(saved),
                    'instagram_url': url,
                    'date_processed': datetime.now().isoformat()
                }
            }

        result = process_and_save()
        return Response(result)
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return Response({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error processing and saving reel: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)
@swagger_auto_schema(
    method='post',
    operation_description="Sync local data to Firebase",
    responses={
        200: openapi.Response(
            description="Success",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        example="Sync completed successfully"
                    )
                }
            )
        )
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_instagram_locations(request):
    """Second step: Save analyzed locations after user review"""
    try:
        locations = request.data.get('locations', [])
        url = request.data.get('url')
        
        if not locations or not url:
            return Response({'error': 'Missing data'}, status=400)
            
        firebase_service = FirebaseService()
        
        @async_to_sync
        async def save_locations():
            return await firebase_service.save_instagram_locations(
                locations=locations,
                instagram_url=url,
                user_id=str(request.user.id)
            )

        saved = save_locations()
        return Response(saved)
        
    except Exception as e:
        logger.error(f"Save error: {str(e)}")
        return Response({'error': str(e)}, status=400)
@action(detail=False, methods=['GET', 'POST'])
def categories(self, request):
    """Manage user-defined categories"""
    try:
        if request.method == 'GET':
            @async_to_sync
            async def get_categories():
                return await self.firebase_service.get_user_categories(
                    str(request.user.id)
                )
            return Response(get_categories())
            
        elif request.method == 'POST':
            category = request.data.get('category')
            if not category:
                return Response(
                    {'error': 'Category name required'}, 
                    status=400
                )
                
            @async_to_sync
            async def add_category():
                return await self.firebase_service.add_user_category(
                    str(request.user.id),
                    category
                )
            return Response(add_category())
            
    except Exception as e:
        logger.error(f"Category error: {str(e)}")
        return Response({'error': str(e)}, status=400)
# Sync Endpoints
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_to_firebase(request):
    """Sync local data to Firebase"""
    try:
        sync_service = SyncService()
        
        # Get data to sync
        locations = Location.objects.filter(sync_status__in=[0, 1])
        user_locations = UserLocation.objects.filter(
            user=request.user,
            sync_status__in=[0, 1]
        )
        
        # Sync locations
        location_results = []
        for location in locations:
            success = sync_service.sync_location_to_firebase(location)
            location_results.append({
                'id': str(location.id),
                'success': success
            })
            
        # Sync user locations
        user_location_results = []
        for user_location in user_locations:
            success = sync_service.sync_user_location_to_firebase(user_location)
            user_location_results.append({
                'id': str(user_location.id),
                'success': success
            })
            
        return Response({
            'success': True,
            'locations_synced': location_results,
            'user_locations_synced': user_location_results
        })
        
    except Exception as e:
        logger.error(f"Sync to Firebase error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_from_firebase(request):
    """Sync data from Firebase to local database"""
    try:
        sync_service = SyncService()
        success = sync_service.sync_from_firebase(request.user.id)
        
        if success:
            return Response({
                'success': True,
                'message': 'Successfully synced from Firebase'
            })
        else:
            return Response({
                'success': False,
                'message': 'Failed to sync from Firebase'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Sync from Firebase error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#for the test    
@api_view(['GET'])
@permission_classes([AllowAny])
def test_firebase_connection(request):
    """Test endpoint for Firebase connection"""
    try:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            
            try:
                decoded_token = auth.verify_id_token(token)
                return Response({
                    'success': True,
                    'message': 'Firebase connection successful',
                    'user_id': decoded_token.get('uid'),
                    'user_email': decoded_token.get('email')
                })
            except Exception as e:
                logger.error(f"Token verification error: {str(e)}")
                return Response({
                    'success': False,
                    'error': 'Invalid token'
                }, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({
                'success': False,
                'error': 'No token provided'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
    except Exception as e:
        logger.error(f"Test Firebase error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def test_auth(request):
    """Test authentication status"""
    try:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            
            try:
                decoded_token = auth.verify_id_token(token)
                return Response({
                    'success': True,
                    'authenticated': True,
                    'user_id': decoded_token.get('uid'),
                    'email': decoded_token.get('email')
                })
            except Exception as e:
                logger.error(f"Token verification error: {str(e)}")
                return Response({
                    'success': False,
                    'error': 'Invalid token'
                }, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({
                'success': False,
                'error': 'No token provided'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
    except Exception as e:
        logger.error(f"Test auth error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)