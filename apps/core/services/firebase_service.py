# apps/core/services/firebase_service.py
import firebase_admin
from firebase_admin import credentials, db, auth
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from typing import Dict, List, Optional, Tuple, ClassVar
from datetime import datetime, timedelta, timezone
from .firebase_logging import firebase_operation_logger
from math import sin, cos, sqrt, atan2, radians
import json
import random
import logging
import iso8601
import asyncio
from functools import wraps
import functools
from asgiref.sync import sync_to_async
import uuid

logger = logging.getLogger(__name__)

class FirebaseServiceError(Exception):
    """Base exception class for Firebase service errors"""
    pass
class FirebaseError(Exception):
    """Base exception for Firebase-related errors"""
    pass
class FirebaseAuthenticationError(FirebaseServiceError):
    """Raised when there are authentication issues"""
    pass

class FirebaseDataError(FirebaseServiceError):
    """Raised when there are data validation or processing issues"""
    pass

class FirebaseConnectionError(FirebaseServiceError):
    """Raised when there are connection issues"""
    pass
class FirebaseSyncError(FirebaseError):
    """Raised when there are sync-related issues"""
    pass
def safe_cache_operation(operation):
    """Safely execute cache operations"""
    try:
        return operation()
    except Exception as e:
        logger.warning(f"Cache operation failed: {str(e)}")
        return None

def handle_firebase_operation(operation_name: str, max_retries: int = 3):
    """Enhanced decorator for handling Firebase operations"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retry_count = 0
            last_error = None
            
            while retry_count < max_retries:
                try:
                    start_time = datetime.now()
                    result = await func(*args, **kwargs)
                    duration = (datetime.now() - start_time).total_seconds()
                    
                    logger.info(
                        f"Firebase operation '{operation_name}' completed in {duration}s",
                        extra={
                            'operation': operation_name,
                            'duration': duration,
                            'success': True
                        }
                    )
                    return result
                    
                except ConnectionError as e:
                    last_error = e
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                    continue
                    
                except ValueError as e:
                    # Don't retry business logic errors
                    raise FirebaseDataError(str(e))
                    
                except Exception as e:
                    logger.error(
                        f"Firebase operation '{operation_name}' failed (attempt {retry_count + 1}/{max_retries}): {str(e)}",
                        exc_info=True
                    )
                    last_error = e
                    retry_count += 1
                    if retry_count == max_retries:
                        raise FirebaseServiceError(f"Operation failed after {max_retries} attempts: {str(last_error)}")
                    await asyncio.sleep(2 ** retry_count)
                    
            return None
            
        return wrapper
    return decorator

class FirebaseService:
    _instance = None
    # Class level constants
    TEST_USER_ID: ClassVar[str] = "test_user_123" 
     # Update test user constants
    TEST_USER_IDS = ['test_user_123', 'test_user_id']  # List of all test user IDs
    DEFAULT_TEST_USER_ID = 'test_user_123' # Default test user ID
    def __init__(self):
        """Initialize Firebase service"""
        self._initialize()
        self.test_user_id = self.TEST_USER_ID

    def _parse_date(self, date_str: str) -> datetime:
        """Parse ISO date string to datetime"""
        try:
            return iso8601.parse_date(date_str)
        except Exception:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    async def process_instagram_locations(self, reel_data: Dict, user_id: str) -> List[Dict]:
        """Process Instagram locations with URL check"""
        try:
            # Convert user_id to string and get current time
            user_id = str(user_id)
            current_time = datetime.now(timezone.utc).isoformat()

            # First check for existing locations
            existing_locations = await self.get_locations_by_instagram_url(reel_data['url'])
            if existing_locations:
                logger.info(f"Returning {len(existing_locations)} existing locations")
                return existing_locations

            @sync_to_async
            def save_locations():
                saved_locations = []
                
                try:
                    for location in reel_data.get('locations', []):
                        # Get coordinates safely
                        coordinates = location.get('coordinates', {})
                        if coordinates is None:
                            coordinates = {}

                        # 1. Create Location record
                        location_id = str(uuid.uuid4())
                        
                        location_data = {
                            'id': location_id,
                            'name': location.get('name', ''),
                            'latitude': coordinates.get('latitude', None),
                            'longitude': coordinates.get('longitude', None),
                            'description': reel_data.get('description', ''),
                            'address': location.get('name', ''),
                            'is_instagram_source': True,
                            'instagram_url': reel_data.get('url', ''),
                            'date_posted': reel_data.get('date_posted', current_time),
                            'source_type': location.get('type', 'instagram'),
                            'created_at': current_time,
                            'created_by': user_id,
                            'version': 1
                        }
                        
                        # Validate and save location
                        self._validate_location_data(location_data)
                        self.db.child('locations').child(location_id).set(location_data)
                        logger.debug(f"Saved location: {location_id}")
                        
                        # 2. Create UserLocation record
                        user_location_id = str(uuid.uuid4())
                        user_location_data = {
                            'id': user_location_id,
                            'user_id': user_id,
                            'location_id': location_id,
                            'custom_name': '',
                            'custom_description': '',
                            'category': location.get('category', 'uncategorized'),
                            'is_favorite': False,
                            'notify_radius': 1.0,
                            'notifications_enabled': False,
                            'saved_at': current_time,
                            'last_updated': current_time
                        }
                        
                        # Validate and save user location
                        self._validate_user_location_data(user_location_data)
                        self.db.child('user_locations')\
                            .child(user_id)\
                            .child(user_location_id)\
                            .set(user_location_data)
                        
                        # Create combined response
                        saved_location = {
                            **location_data,
                            'user_location': user_location_data
                        }
                        saved_locations.append(saved_location)
                        
                        logger.info(f"Saved location {location_id} with user location {user_location_id}")
                    
                    if saved_locations:
                        logger.info(f"Successfully saved {len(saved_locations)} locations")
                        return saved_locations
                    else:
                        raise FirebaseServiceError("No locations were saved successfully")
                    
                except Exception as e:
                    logger.error(f"Error saving locations: {str(e)}", exc_info=True)
                    raise FirebaseServiceError(f"Failed to save locations: {str(e)}")

            return await save_locations()
            
        except Exception as e:
            logger.error(f"Failed to process Instagram locations: {str(e)}", exc_info=True)
            raise FirebaseServiceError(str(e))
    async def save_instagram_locations(
        self, 
        locations: List[Dict], 
        user_id: str, 
        instagram_url: str
    ) -> List[Dict]:
        """Save multiple locations from Instagram with user preferences"""
        try:
            saved_locations = []
            current_time = datetime.now(timezone.utc).isoformat()

            for location in locations:
                # Safely get coordinates
                coordinates = location.get('coordinates', {})
                if coordinates is None:
                    coordinates = {}
                
                # Generate location ID
                location_id = str(uuid.uuid4())

                # Prepare location data with safe defaults
                location_data = {
                    'id': location_id,
                    'name': location.get('name', 'Unnamed Location'),
                    'latitude': coordinates.get('latitude') or location.get('latitude'),
                    'longitude': coordinates.get('longitude') or location.get('longitude'),
                    'description': location.get('description', ''),
                    'category': location.get('category', 'uncategorized'),
                    'address': location.get('address', ''),
                    'is_instagram_source': True,
                    'instagram_url': instagram_url,
                    'type': location.get('type', 'unknown'),
                    'created_by': user_id,
                    'created_at': current_time,
                    'version': 1,
                    'is_deleted': False,
                    'last_modified': current_time
                }

                # Log the data for debugging
                logger.debug(f"Preparing to save location: {location_data}")

                # Save main location
                try:
                    self.db.child('locations').child(location_id).set(location_data)
                    logger.debug(f"Saved location: {location_id}")

                    # Create user location record
                    user_location_id = str(uuid.uuid4())
                    user_settings = location.get('user_settings', {})
                    if user_settings is None:
                        user_settings = {}

                    user_location_data = {
                        'id': user_location_id,
                        'user_id': user_id,
                        'location_id': location_id,
                        'custom_name': user_settings.get('custom_name', ''),
                        'custom_description': user_settings.get('custom_description', ''),
                        'category': user_settings.get('category') or location.get('category', 'uncategorized'),
                        'is_favorite': user_settings.get('is_favorite', False),
                        'notify_enabled': user_settings.get('notify_enabled', False),
                        'notify_radius': float(user_settings.get('notify_radius', 1.0)),
                        'saved_at': current_time,
                        'last_updated': current_time
                    }

                    # Save user location
                    self.db.child('user_locations')\
                        .child(user_id)\
                        .child(user_location_id)\
                        .set(user_location_data)

                    # Add to saved locations list
                    saved_location = {
                        **location_data,
                        'user_location': user_location_data
                    }
                    saved_locations.append(saved_location)
                    logger.info(f"Successfully saved location {location_id} with user location {user_location_id}")

                except Exception as loc_error:
                    logger.error(f"Error saving location {location.get('name')}: {str(loc_error)}")
                    continue

            if not saved_locations:
                raise FirebaseDataError("No locations were saved successfully")

            return saved_locations

        except Exception as e:
            logger.error(f"Failed to save Instagram locations: {str(e)}", exc_info=True)
            raise FirebaseServiceError(f"Failed to save Instagram locations: {str(e)}")
    def _validate_location_data(self, location_data: Dict) -> None:
        """Validate location data before saving"""
        required_fields = {
            'name': str,
            'created_by': str,
            'created_at': str
        }
        
        for field, field_type in required_fields.items():
            if field not in location_data:
                raise FirebaseDataError(f"Missing required field: {field}")
            if not isinstance(location_data[field], field_type):
                raise FirebaseDataError(
                    f"Invalid type for {field}. Expected {field_type.__name__}"
                )

        # Validate coordinates if present
        if location_data.get('latitude') is not None:
            try:
                lat = float(location_data['latitude'])
                if not -90 <= lat <= 90:
                    raise FirebaseDataError("Latitude must be between -90 and 90")
            except ValueError:
                raise FirebaseDataError("Invalid latitude value")

        if location_data.get('longitude') is not None:
            try:
                lng = float(location_data['longitude'])
                if not -180 <= lng <= 180:
                    raise FirebaseDataError("Longitude must be between -180 and 180")
            except ValueError:
                raise FirebaseDataError("Invalid longitude value")
            
    def _validate_user_location_data(self, user_location_data: Dict) -> None:
        """Validate user location data before saving"""
        required_fields = {
            'user_id': str,
            'location_id': str,
            'saved_at': str,
            'last_updated': str
        }
        
        for field, field_type in required_fields.items():
            if field not in user_location_data:
                raise FirebaseDataError(f"Missing required field: {field}")
            if not isinstance(user_location_data[field], field_type):
                raise FirebaseDataError(
                    f"Invalid type for {field}. Expected {field_type.__name__}"
                )

        # Validate notify_radius if present
        if user_location_data.get('notify_radius') is not None:
            try:
                radius = float(user_location_data['notify_radius'])
                if radius <= 0:
                    raise FirebaseDataError("Notify radius must be greater than 0")
            except ValueError:
                raise FirebaseDataError("Invalid notify radius value")    
    async def delete_user_location(self, user_id: str, location_id: str) -> bool:
        """Delete user location while preserving the main location"""
        try:
            @sync_to_async
            def perform_delete():
                # Find the user location record
                user_locations = self.db.child('user_locations')\
                    .child(user_id)\
                    .order_by_child('location_id')\
                    .equal_to(location_id)\
                    .get()

                if not user_locations:
                    raise FirebaseServiceError("User location not found")

                # Delete only the user location record
                for ul_id in user_locations.keys():
                    self.db.child('user_locations')\
                        .child(user_id)\
                        .child(ul_id)\
                        .remove()

                return True

            return await perform_delete()

        except Exception as e:
            logger.error(f"Failed to delete user location: {str(e)}", exc_info=True)
            raise FirebaseServiceError(str(e))
    def _initialize(self):
        """Initialize Firebase Admin SDK and setup test configuration"""
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(settings.FIREBASE_ADMIN_CREDENTIALS)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': settings.FIREBASE_DATABASE_URL
                })
            self.db = db.reference()
            
            # Get test user ID from settings or use default
            self.test_user_id = getattr(settings, 'FIREBASE_TEST_USER_ID', self.TEST_USER_ID)
            
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.error(f"Firebase initialization error: {str(e)}")
            raise FirebaseConnectionError(f"Failed to initialize Firebase: {str(e)}")
    async def get_locations_by_instagram_url(self, url: str) -> List[Dict]:
        """Get existing locations by Instagram URL"""
        try:
            @sync_to_async
            def fetch_locations():
                # Get all locations
                locations_ref = self.db.child('locations').get()
                if not locations_ref:
                    return []

                matching_locations = []
                for loc_id, loc_data in locations_ref.items():
                    # Check if the location has matching Instagram URL
                    if isinstance(loc_data, dict) and loc_data.get('instagram_url') == url:
                        # Get associated user locations
                        user_locations_ref = self.db.child('user_locations').get()
                        user_location_data = None
                        
                        if user_locations_ref:
                            for user_id, user_locs in user_locations_ref.items():
                                if isinstance(user_locs, dict):
                                    for ul_id, ul_data in user_locs.items():
                                        if ul_data.get('location_id') == loc_id:
                                            user_location_data = {
                                                'id': ul_id,
                                                **ul_data
                                            }
                                            break

                        matching_locations.append({
                            'id': loc_id,
                            **loc_data,
                            'user_location': user_location_data
                        })

                logger.info(f"Found {len(matching_locations)} existing locations for URL: {url}")
                return matching_locations

            return await fetch_locations()

        except Exception as e:
            logger.error(f"Error fetching locations by URL: {str(e)}")
            raise FirebaseServiceError(str(e))
            
        
    def validate_location_data(self, location_data: Dict) -> None:
        """Enhanced location data validation"""
        try:
            # Check required fields with detailed error messages
            required_fields = {
                'name': 'string',
                'latitude': 'number',
                'longitude': 'number',
                'user_id': 'string'
            }
            
            missing_fields = []
            invalid_fields = []
            
            for field, field_type in required_fields.items():
                if field not in location_data:
                    missing_fields.append(field)
                    continue
                
                value = location_data[field]
                
                if field_type == 'number':
                    try:
                        float_value = float(value)
                        # Validate coordinate ranges
                        if field == 'latitude' and not (-90 <= float_value <= 90):
                            invalid_fields.append(f"{field} must be between -90 and 90")
                        elif field == 'longitude' and not (-180 <= float_value <= 180):
                            invalid_fields.append(f"{field} must be between -180 and 180")
                    except (ValueError, TypeError):
                        invalid_fields.append(f"{field} must be a valid number")
                elif field_type == 'string' and not isinstance(value, str):
                    invalid_fields.append(f"{field} must be a string")

            if missing_fields:
                raise FirebaseDataError(f"Missing required fields: {', '.join(missing_fields)}")
            
            if invalid_fields:
                raise FirebaseDataError(f"Validation failed: {'; '.join(invalid_fields)}")
                
        except FirebaseDataError:
            raise
        except Exception as e:
            raise FirebaseDataError(f"Validation error: {str(e)}")
    # Improve real-time updates handling
    def setup_realtime_listeners(self):
        """Setup listeners for real-time updates"""
        try:
            def location_callback(event):
                if event.type == 'put':
                    self._handle_location_update(event.path, event.data)
                    
            def user_location_callback(event):
                if event.type == 'put':
                    self._handle_user_location_update(event.path, event.data)
            
            # Setup listeners
            self.db.child('locations').listen(location_callback)
            self.db.child('user_locations').listen(user_location_callback)
            
        except Exception as e:
            logger.error(f"Failed to setup listeners: {str(e)}")
            raise FirebaseServiceError("Failed to setup real-time listeners")
    def _setup_database_listeners(self):
        """Setup Firebase Realtime Database listeners"""
        try:
            # Listen for location changes
            self.db.child('locations').listen(self._handle_location_change)
            
            # Listen for user location changes
            self.db.child('userLocations').listen(self._handle_user_location_change)
            
        except Exception as e:
            logger.error(f"Failed to setup database listeners: {str(e)}")
    def handle_firebase_operation(operation_name: str, max_retries: int = 3, base_delay: float = 0.5):
        """Enhanced decorator for handling Firebase operations with exponential backoff"""
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                retry_count = 0
                last_error = None
                
                while retry_count < max_retries:
                    try:
                        result = await func(*args, **kwargs)
                        return result
                        
                    except (ConnectionError, TimeoutError) as e:
                        retry_count += 1
                        last_error = e
                        
                        if retry_count < max_retries:
                            # Exponential backoff with jitter
                            delay = base_delay * (2 ** (retry_count - 1)) * (0.5 + random.random())
                            logger.warning(
                                f"Retry {retry_count}/{max_retries} for {operation_name} "
                                f"after {delay:.2f}s delay. Error: {str(e)}"
                            )
                            await asyncio.sleep(delay)
                        continue
                        
                    except Exception as e:
                        logger.error(f"Operation {operation_name} failed: {str(e)}")
                        raise FirebaseServiceError(f"Operation failed: {str(e)}")
                        
                raise FirebaseServiceError(
                    f"Operation {operation_name} failed after {max_retries} retries: {str(last_error)}"
                )
                
            return wrapper
        return decorator
    def _handle_location_change(self, event):
        """Handle location change events from Firebase"""
        try:
            if event.event_type == 'put':
                location_id = event.path.split('/')[-1]
                try:
                    # Try to use cache if Redis is available
                    cache_key = f'location_{location_id}'
                    if event.data is None:
                        cache.delete(cache_key)
                    else:
                        cache.set(cache_key, event.data, timeout=3600)
                except Exception as cache_error:
                    logger.warning(f"Cache operation failed: {str(cache_error)}")
                    
        except Exception as e:
            logger.error(f"Error handling location change: {str(e)}")

    def _handle_user_location_change(self, event):
        """Handle user location change events from Firebase"""
        try:
            if event.event_type == 'put':
                path_parts = event.path.split('/')
                if len(path_parts) >= 2:
                    user_id = path_parts[-2]
                    location_id = path_parts[-1]
                    try:
                        # Try to use cache if Redis is available
                        cache_key = f'user_locations_{user_id}'
                        cache.delete(cache_key)  # Invalidate the cache for this user's locations
                    except Exception as cache_error:
                        logger.warning(f"Cache operation failed: {str(cache_error)}")
                        
        except Exception as e:
            logger.error(f"Error handling user location change: {str(e)}")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize Firebase Admin SDK"""
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(settings.FIREBASE_ADMIN_CREDENTIALS)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': settings.FIREBASE_DATABASE_URL
                })
            self.db = db.reference()
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.error(f"Firebase initialization error: {str(e)}")
            raise
    def _matches_text_search(self, location: Dict, query: str) -> bool:
        """Helper to perform text search"""
        searchable_text = ' '.join([
            str(location.get('name', '')),
            str(location.get('description', '')),
            str(location.get('category', '')),
            str(location.get('address', ''))
        ]).lower()
        return query.lower() in searchable_text

    async def search_locations(
        self,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        query: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Dict]:
        """Enhanced search with precise filtering"""
        try:
            locations_ref = self.db.child('locations')
            
            # Use category index if available
            if category:
                results = locations_ref.order_by_child('category')\
                    .equal_to(category)\
                    .get()
            else:
                results = locations_ref.get()

            if not results:
                return []

            filtered_locations = []
            for loc_id, loc_data in results.items():
                if not isinstance(loc_data, dict):
                    continue

                loc_data['id'] = loc_id

                # Apply spatial filter
                if all(x is not None for x in [center_lat, center_lng, radius_km]):
                    try:
                        distance = self._calculate_distance(
                            float(center_lat),
                            float(center_lng),
                            float(loc_data['latitude']),
                            float(loc_data['longitude'])
                        )
                        
                        # Only include if within radius
                        if distance > float(radius_km):
                            continue
                            
                        loc_data['distance'] = round(distance, 3)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Distance calculation error for {loc_id}: {e}")
                        continue

                # Apply text search
                if query and not self._matches_text_search(loc_data, query):
                    continue

                filtered_locations.append(loc_data)

            # Sort by distance if spatial search
            if center_lat and center_lng:
                filtered_locations.sort(key=lambda x: x.get('distance', float('inf')))

            return filtered_locations

        except Exception as e:
            logger.error(f"Search error: {e}")
            raise FirebaseServiceError(f"Search failed: {e}")
        
    def _matches_all_criteria(
        self,
        location: Dict,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        query: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> bool:
        """Check if location matches all search criteria"""
        try:
            # Check spatial criteria
            if not self._location_matches_criteria(
                location,
                center_lat,
                center_lng,
                radius_km
            ):
                return False

            # Check text search
            if query:
                query = query.lower()
                searchable_fields = [
                    str(location.get('name', '')),
                    str(location.get('description', '')),
                    str(location.get('category', '')),
                    str(location.get('address', ''))
                ]
                searchable_text = ' '.join(searchable_fields).lower()
                
                if query not in searchable_text:
                    return False

            # Check date range
            if date_from or date_to:
                loc_date_str = location.get('createdAt')
                if not loc_date_str:
                    return False
                
                try:
                    loc_date = self._parse_date(loc_date_str)
                    
                    if date_from:
                        from_date = self._parse_date(date_from)
                        if loc_date < from_date:
                            return False
                            
                    if date_to:
                        to_date = self._parse_date(date_to)
                        if loc_date > to_date:
                            return False
                            
                except Exception as date_error:
                    logger.warning(f"Date comparison error: {str(date_error)}")
                    return False

            return True
            
        except Exception as e:
            logger.warning(f"Criteria matching error: {str(e)}")
            return False
        
    def _location_matches_criteria(
        self,
        location: Dict,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        query: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> bool:
        """Check if location matches all search criteria"""
        try:
            # Check spatial criteria
            if center_lat is not None and center_lng is not None and radius_km is not None:
                try:
                    loc_lat = float(location.get('latitude', 0))
                    loc_lng = float(location.get('longitude', 0))
                    
                    distance = self._calculate_distance(
                        center_lat, center_lng,
                        loc_lat, loc_lng
                    )
                    
                    if distance > radius_km:
                        logger.debug(f"Location out of range: distance={distance}, radius={radius_km}")
                        return False
                        
                except (ValueError, TypeError) as e:
                    logger.warning(f"Distance calculation error: {e}")
                    return False

            # Rest of the criteria checking...
            # ... (keep the existing code for other criteria)

            return True
                
        except Exception as e:
            logger.warning(f"Criteria matching error: {str(e)}")
            return False

    async def create_user_profile(self, user_id: str, user_data: Dict) -> Dict:
        """Create user profile according to Firebase schema"""
        try:
            profile_data = {
                'email': user_data['email'],
                'username': user_data.get('username', ''),
                'displayName': user_data.get('display_name', ''),  # Add this back
                'lastLogin': datetime.now().isoformat()
            }

            # Save user profile
            self.db.child('users')\
                .child(user_id)\
                .child('profile')\
                .set(profile_data)

            return profile_data
        except Exception as e:
            logger.error(f"Failed to create user profile: {str(e)}")
            raise

    async def save_user(self, user_data: dict) -> str:
        """Save user data to Firebase"""
        user_ref = self.db.child('users').child(user_data['id'])
        user_ref.set({
            'profile': {
                'email': user_data['email'],
                'displayName': user_data.get('display_name', ''),
                'photoURL': user_data.get('photo_url'),
                'createdAt': datetime.now().isoformat(),
                'lastLogin': datetime.now().isoformat()
            },
            'settings': {
                'defaultMapView': {
                    'latitude': 0,
                    'longitude': 0,
                    'zoom': 10
                },
                'notifications': True,
                'syncFrequency': 300  # 5 minutes
            }
        })
        return user_data['id']

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance in kilometers using Haversine formula"""
        from math import sin, cos, sqrt, atan2, radians

        R = 6371  # Earth's radius in kilometers

        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c

    @handle_firebase_operation("save_location")
    async def save_location(self, location_data: Dict) -> Tuple[str, Dict]:
        """Save location with schema validation"""
        try:
            # Validate data first
            self.validate_location_data(location_data)
            
            # Generate new location ID
            location_id = self.db.child('locations').push().key
            
            # Get current timestamp
            current_time = datetime.now(timezone.utc)
            
            # Prepare location record according to schema
            location_record = {
                'name': str(location_data['name']),
                'latitude': float(location_data['latitude']),
                'longitude': float(location_data['longitude']),
                'description': str(location_data.get('description', '')),
                'address': str(location_data.get('address', '')),
                'category': str(location_data.get('category', 'uncategorized')),
                'isInstagramSource': bool(location_data.get('is_instagram_source', False)),
                'instagramUrl': str(location_data.get('instagram_url', '')),
                'datePosted': current_time.isoformat(),
                'createdAt': current_time.isoformat(),
                'createdBy': str(location_data['user_id']),
                'version': 1,
                'isDeleted': False,
                'version': 1,
                'lastModified': current_time.isoformat()
            }
            location_data.update({
            'source_type': location_data.get('source_type', 'manual'),
            'added_from': location_data.get('added_from', 'map'), # 'map' or 'search'
            'user_defined_category': location_data.get('category', 'uncategorized')
            })
            # Add Instagram data if present
            if location_data.get('instagram_data'):
                location_record['instagramData'] = location_data['instagram_data']

            # Save location
            self.db.child('locations').child(location_id).set(location_record)

            # Create user location record
            user_location_record = {
                'customName': str(location_data.get('custom_name', '')),
                'customDescription': str(location_data.get('custom_description', '')),
                'customCategory': str(location_data.get('custom_category', '')),
                'notes': str(location_data.get('notes', '')),
                'isFavorite': bool(location_data.get('is_favorite', False)),
                'notifyEnabled': bool(location_data.get('notify_enabled', False)),
                'notifyRadius': float(location_data.get('notify_radius', 1.0)),
                'savedAt': current_time.isoformat(),
                'lastUpdated': current_time.isoformat()
            }
            def transaction_update(current_data):
                if current_data is not None:
                    raise FirebaseDataError("Location already exists")
                return location_record
            # Save user location reference
            self.db.child('user_locations')\
                .child(location_data['user_id'])\
                .child(location_id)\
                .set(user_location_record)
            
            # Update cache
            cache_key = f'location_{location_id}'
            safe_cache_operation(
                lambda: cache.set(cache_key, location_record, timeout=3600)
            )

            return location_id, location_record

        except FirebaseDataError:
            raise
        except Exception as e:
            logger.error(f"Failed to save location: {str(e)}", exc_info=True)
            raise FirebaseServiceError(f"Failed to save location: {str(e)}")

    def get_location(self, location_id):
        """Get location from Firebase"""
        try:
            return self.db.child('locations').child(location_id).get()
        except Exception as e:
            logger.error(f"Error getting location: {str(e)}")
            raise

    async def delete_location(self, location_id: str, user_id: str) -> bool:
        """Delete location with permission check"""
        try:
            # Get location data first
            location_ref = self.db.child('locations').child(location_id)
            location_data = location_ref.get()

            if not location_data:
                raise FirebaseDataError("Location not found")

            # Check permissions
            if location_data.get('createdBy') != user_id:
                raise FirebaseDataError("Unauthorized to delete this location")

            # Delete location
            location_ref.delete()

            # Delete user location reference
            self.db.child('user_locations')\
                .child(user_id)\
                .child(location_id)\
                .delete()

            return True

        except FirebaseDataError as e:
            raise FirebaseServiceError(str(e))
        except Exception as e:
            logger.error(f"Failed to delete location: {str(e)}")
            raise FirebaseServiceError(f"Failed to delete location: {str(e)}")

    def sync_user_data(self, user_id, data):
        """Sync user data to Firebase"""
        try:
            self.db.child('users').child(user_id).set(data)
            return True
        except Exception as e:
            logger.error(f"Error syncing user data: {str(e)}")
            raise

    @handle_firebase_operation("get_user_locations")
    async def get_user_locations(self, user_id: str) -> List[Dict]:
        """Get all locations for a user"""
        try:
            @sync_to_async
            def fetch_locations():
                # Get user's location references
                user_locations_ref = self.db.child('user_locations').child(user_id).get()
                if not user_locations_ref:
                    return []

                locations = []
                for ul_id, ul_data in user_locations_ref.items():
                    if not isinstance(ul_data, dict):
                        continue

                    # Get the main location data
                    location_id = ul_data.get('location_id')
                    if not location_id:
                        continue

                    location_data = self.db.child('locations').child(location_id).get()
                    if not location_data:
                        continue

                    # Combine the data
                    combined_data = {
                        **location_data,
                        'user_location': {
                            'id': ul_id,
                            **ul_data
                        }
                    }
                    locations.append(combined_data)

                return locations

            return await fetch_locations()

        except Exception as e:
            logger.error(f"Failed to get user locations: {str(e)}", exc_info=True)
            raise FirebaseServiceError(str(e))
    # Add new method for handling optimistic locking
    async def update_with_optimistic_lock(self, location_id: str, user_id: str, data: Dict) -> Dict:
        """Update with optimistic locking to prevent conflicts"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Get current version
                location_ref = self.db.child('locations').child(location_id)
                current_data = location_ref.get()
                
                if not current_data:
                    raise FirebaseDataError("Location not found")
                    
                current_version = current_data.get('version', 1)
                
                # Prepare update with version increment
                update_data = {
                    **data,
                    'version': current_version + 1,
                    'lastModified': datetime.now(timezone.utc).isoformat()
                }
                
                # Try to update with version check
                def transaction_update(transaction_data):
                    if transaction_data.get('version') != current_version:
                        return None  # Abort transaction
                    return update_data
                
                success = location_ref.transaction(transaction_update)
                
                if success:
                    return update_data
                    
                retry_count += 1
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                
            except Exception as e:
                logger.error(f"Update failed: {str(e)}")
                raise FirebaseServiceError(f"Update failed: {str(e)}")
                
        raise FirebaseServiceError("Max retries reached for optimistic locking")
    
    async def create_test_user(self, user_id: Optional[str] = None) -> str:
        """Create a test user with proper profile"""
        try:
            user_id = user_id or self.DEFAULT_TEST_USER_ID
            
            user_profile = {
                'profile': {
                    'displayName': 'Test User',
                    'email': 'test@example.com',
                    'lastLogin': datetime.now(timezone.utc).isoformat(),
                    'username': ''
                }
            }
            
            # Save user profile
            self.db.child('users').child(user_id).set(user_profile)
            logger.info(f"Created test user profile: {user_id}")
            
            return user_id
            
        except Exception as e:
            logger.error(f"Failed to create test user: {e}")
            raise
    async def get_test_user_locations(self) -> List[Dict]:
        """Get locations for test user"""
        return await self.get_user_locations(self.test_user_id)
    @classmethod
    def is_test_user_id(cls, user_id: str) -> bool:
        """Check if a user ID is a test user ID"""
        return user_id in cls.TEST_USER_IDS
    @classmethod
    def get_test_user_id(cls) -> str:
        """Get test user ID - useful for tests"""
        return cls.TEST_USER_ID
    async def create_test_data(self, num_locations: int = 3) -> List[str]:
        """Create test locations for testing"""
        location_ids = []
        try:
            base_location = {
                "name": "Test Location",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "user_id": self.test_user_id,
                "description": "Test location for unit tests",
                "category": "test"
            }

            for i in range(num_locations):
                location_data = {
                    **base_location,
                    "name": f"Test Location {i}",
                    "latitude": base_location["latitude"] + (i * 0.001),
                    "longitude": base_location["longitude"] + (i * 0.001)
                }
                
                location_id, _ = await self.save_location(location_data)
                location_ids.append(location_id)
                logger.info(f"Created test location: {location_id}")

            return location_ids

        except Exception as e:
            logger.error(f"Failed to create test data: {e}")
            raise
    def sync_location(self, location, user_id=None):
        """Sync location between Django and Firebase"""
        try:
            location_data = {
                'id': str(location.id),
                'name': location.name,
                'latitude': float(location.latitude),
                'longitude': float(location.longitude),
                'description': location.description,
                'category': location.category,
                'address': location.address,
                'is_instagram_source': location.is_instagram_source,
                'instagram_url': location.instagram_url,
                'created_at': location.created_at.isoformat(),
                'updated_at': location.updated_at.isoformat(),
            }

            if location.firebase_id:
                # Update existing location
                self.update_location(location.firebase_id, location_data)
            else:
                # Create new location
                firebase_id = self.save_location(location_data)
                location.firebase_id = firebase_id
                location.save(update_fields=['firebase_id'])

            return True
        except Exception as e:
            logger.error(f"Error syncing location: {str(e)}")
            raise
    

    @handle_firebase_operation("update_location")
    async def update_location(self, location_id: str, user_id: str, update_data: Dict) -> Dict:
        """Update location with proper version handling"""
        try:
            current_time = datetime.now(timezone.utc)
            location_ref = self.db.child('locations').child(location_id)
            current_data = location_ref.get()

            if not current_data:
                raise FirebaseDataError("Location not found")

            if current_data.get('createdBy') != user_id:
                raise FirebaseDataError("Unauthorized to update this location")

            # Version checking
            current_version = current_data.get('version', 1)
            update_version = update_data.get('version')

            if update_version is not None and update_version != current_version:
                raise FirebaseDataError("Location was updated by another user")

            # Prepare update
            updated_data = {
                **current_data,
                **update_data,
                'lastUpdated': current_time.isoformat(),
                'version': current_version + 1
            }

            # Save update
            location_ref.set(updated_data)

            # Update cache
            try:
                cache_key = f'location_{location_id}'
                cache.set(cache_key, updated_data, timeout=3600)
            except Exception as cache_error:
                logger.warning(f"Cache operation failed: {str(cache_error)}")

            return updated_data

        except FirebaseDataError:
            raise
        except Exception as e:
            logger.error(f"Failed to update location: {str(e)}")
            raise FirebaseServiceError(f"Update failed: {str(e)}")
        
    async def cleanup_test_data(self):
        """Complete cleanup of all test data"""
        try:
            # 1. Clean up locations first
            locations_ref = self.db.child('locations')
            users_ref = self.db.child('users')
            user_locations_ref = self.db.child('user_locations')
            
            # Delete all test locations
            test_locations = locations_ref.get()
            if test_locations:
                for loc_id, loc_data in test_locations.items():
                    if isinstance(loc_data, dict) and \
                    loc_data.get('createdBy') in self.TEST_USER_IDS:
                        try:
                            # Delete location using delete method
                            locations_ref.child(loc_id).delete()
                            logger.debug(f"Deleted location: {loc_id}")
                        except Exception as e:
                            logger.warning(f"Failed to delete location {loc_id}: {e}")

            # 2. Clean up all test users' data
            for test_user_id in self.TEST_USER_IDS:
                try:
                    # Delete user locations
                    user_locations_ref.child(test_user_id).delete()
                    
                    # Delete user profile
                    users_ref.child(test_user_id).delete()
                    
                    logger.debug(f"Deleted data for test user: {test_user_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete user data for {test_user_id}: {e}")

            # 3. Verify cleanup
            await self.verify_cleanup()

            logger.info("Completed test data cleanup")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)
            raise

    @handle_firebase_operation("verify_cleanup")
    async def verify_cleanup(self):
        """Verify that all test data has been cleaned up"""
        try:
            # Check locations
            locations = self.db.child('locations').get()
            if locations:
                for loc_id, loc_data in locations.items():
                    if isinstance(loc_data, dict) and loc_data.get('createdBy') in self.TEST_USER_IDS:
                        logger.warning(f"Found remaining location: {loc_id}")
                        self.db.child('locations').child(loc_id).delete()

            # Check user_locations
            for test_user_id in self.TEST_USER_IDS:
                user_locs = self.db.child('user_locations').child(test_user_id).get()
                if user_locs:
                    logger.warning(f"Found remaining user_locations for: {test_user_id}")
                    self.db.child('user_locations').child(test_user_id).delete()

            # Check users
            for test_user_id in self.TEST_USER_IDS:
                user = self.db.child('users').child(test_user_id).get()
                if user:
                    logger.warning(f"Found remaining user: {test_user_id}")
                    self.db.child('users').child(test_user_id).delete()

            return True

        except Exception as e:
            logger.error(f"Cleanup verification failed: {e}")
            return False
        
    async def force_cleanup(self):
        """Force cleanup of all data"""
        try:
            # Force reset the entire database
            self.db.set(None)
            logger.info("Forced complete database cleanup")
        except Exception as e:
            logger.error(f"Force cleanup failed: {e}")
            raise
    async def delete_all_data(self) -> Dict[str, int]:
        """
        Delete all locations and user locations data.
        Returns count of deleted items.
        """
        try:
            deleted_counts = {
                'locations': 0,
                'user_locations': 0
            }

            # Delete all locations
            locations_ref = self.db.child('locations')
            all_locations = locations_ref.get()
            
            if all_locations:
                for loc_id, _ in all_locations.items():
                    try:
                        locations_ref.child(loc_id).delete()
                        deleted_counts['locations'] += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete location {loc_id}: {str(e)}")

            # Delete all user locations
            user_locations_ref = self.db.child('userLocations')
            all_user_locations = user_locations_ref.get()
            
            if all_user_locations:
                for user_id, user_locs in all_user_locations.items():
                    try:
                        # Delete all locations for this user
                        user_locations_ref.child(user_id).delete()
                        if isinstance(user_locs, dict):
                            deleted_counts['user_locations'] += len(user_locs)
                    except Exception as e:
                        logger.warning(f"Failed to delete user locations for {user_id}: {str(e)}")

            logger.info(
                f"Deleted {deleted_counts['locations']} locations and "
                f"{deleted_counts['user_locations']} user locations"
            )
            return deleted_counts

        except Exception as e:
            logger.error(f"Failed to delete all data: {str(e)}")
            raise FirebaseServiceError(f"Failed to delete all data: {str(e)}")