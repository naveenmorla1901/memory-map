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
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=location_response_schema
                )
            )
        }
    )
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
    def create(self, request):
        """Create a new location"""
        try:
            location_id = self.firebase_service.save_location({
                **request.data,
                'user_id': request.user.id
            })
            return Response({
                'id': location_id,
                'message': 'Location created successfully'
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    async def list(self, request):
        """List user's locations"""
        try:
            locations = await self.firebase_service.get_user_locations(request.user.id)
            return Response(locations)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    async def update(self, request, pk=None):
        try:
            updated_location = await self.firebase_service.update_with_optimistic_lock(
                pk, 
                request.user.id, 
                request.data
            )
            return Response(updated_location)
        except FirebaseServiceError as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_409_CONFLICT
            )

    @swagger_auto_schema(
        operation_description="Create a new location",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['name', 'latitude', 'longitude'],
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING),
                'latitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                'longitude': openapi.Schema(type=openapi.TYPE_NUMBER),
                'description': openapi.Schema(type=openapi.TYPE_STRING),
                'category': openapi.Schema(type=openapi.TYPE_STRING),
                'address': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={
            201: openapi.Response(
                description="Created",
                schema=location_response_schema
            )
        }
    )

    def get_queryset(self):
        return Location.objects.all()

    async def destroy(self, request, pk=None):
        """Delete location"""
        try:
            await self.firebase_service.delete_location(pk, request.user.id)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'])
    def me(self, request):
        """Get current user's locations"""
        locations = self.get_queryset().filter(created_by=request.user)
        serializer = self.get_serializer(locations, many=True)
        return Response(serializer.data)
    
    

class UserLocationViewSet(viewsets.ModelViewSet):
    serializer_class = UserLocationSerializer
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List user's saved locations",
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
                            'location': location_response_schema,
                            'custom_name': openapi.Schema(type=openapi.TYPE_STRING),
                            'custom_description': openapi.Schema(type=openapi.TYPE_STRING),
                            'is_favorite': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'notify_enabled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'notify_radius': openapi.Schema(type=openapi.TYPE_NUMBER),
                        }
                    )
                )
            )
        }
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        return UserLocation.objects.filter(
            user=self.request.user
        ).select_related('location')

    @swagger_auto_schema(
        operation_description="Get user's favorite locations",
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_STRING),
                            'location': location_response_schema,
                            'is_favorite': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        }
                    )
                )
            )
        }
    )
    @action(detail=False, methods=['get'])
    def favorites(self, request):
        queryset = self.get_queryset().filter(is_favorite=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

@swagger_auto_schema(
    method='post',
    operation_description="Analyze Instagram reel URL",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['url'],
        properties={
            'url': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Instagram reel URL'
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Success",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'url': openapi.Schema(type=openapi.TYPE_STRING),
                    'likes': openapi.Schema(type=openapi.TYPE_STRING),
                    'comments': openapi.Schema(type=openapi.TYPE_STRING),
                    'date_posted': openapi.Schema(type=openapi.TYPE_STRING),
                    'locations': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=location_response_schema
                    )
                }
            )
        )
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
        async def process_reel():
            # First check existing locations
            existing_locations = await firebase_service.get_locations_by_instagram_url(url)
            
            if existing_locations:
                logger.info(f"Found existing locations for URL: {url}")
                return existing_locations
            
            # Analyze the reel
            analyzer = InstagramReelAnalyzer(settings.GOOGLE_API_KEY)
            result = analyzer.analyze_reel(url)
            
            if not result:
                logger.error("Failed to analyze reel")
                return None
            
            if not isinstance(result, dict) or 'locations' not in result:
                logger.error(f"Invalid analyzer result structure: {result}")
                return None
            
            logger.info(f"Successfully analyzed reel with {len(result.get('locations', []))} locations")
            
            # Convert user.id to string for Firebase
            user_id = str(request.user.id)
            
            # Process and save locations
            locations = await firebase_service.process_instagram_locations(
                result,
                user_id
            )
            return locations

        # Process the reel
        result = process_reel()
        
        if result:
            return Response(result)
        
        return Response(
            {'error': 'Failed to analyze or save reel locations'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
        
    except FirebaseServiceError as e:
        logger.error(f"Firebase service error: {str(e)}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f"Error analyzing reel: {str(e)}", exc_info=True)
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

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