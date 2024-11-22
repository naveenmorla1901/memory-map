# apps/core/tests/test_firebase_service.py

import pytest
import asyncio 
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional,List,Dict
import firebase_admin
from firebase_admin import credentials, db
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.conf import settings
from apps.core.services.firebase_service import (
    FirebaseService,
    FirebaseServiceError,
    FirebaseAuthenticationError,
    FirebaseDataError
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) 
pytestmark = pytest.mark.asyncio
# Test configuration
TEST_USER_ID = "test_user_123"
# Test settings
TEST_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}
# Test configuration
TEST_USER_ID = "test_user_123"
TEST_LOCATION_DATA = {
    "name": "Test Location",
    "latitude": 40.7128,
    "longitude": -74.0060,
    "user_id": TEST_USER_ID,
    "description": "Test location for unit tests",
    "category": "test"
}
@pytest.fixture(autouse=True)
async def setup_test_environment(firebase_service):
    """Setup and cleanup test environment with verification"""
    try:
        # Initial cleanup with retries
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            await firebase_service.cleanup_test_data()
            if await firebase_service.verify_cleanup():
                break
            retry_count += 1
            logger.warning(f"Cleanup retry {retry_count}/{max_retries}")
            await asyncio.sleep(1)  # Add small delay between retries
        
        # Create test user
        await firebase_service.create_test_user()
        
        yield
        
    finally:
        # Cleanup after test with retries
        retry_count = 0
        while retry_count < max_retries:
            await firebase_service.cleanup_test_data()
            if await firebase_service.verify_cleanup():
                break
            retry_count += 1
            logger.warning(f"Post-test cleanup retry {retry_count}/{max_retries}")
            await asyncio.sleep(1)
@pytest.fixture(scope='function')
async def clean_firebase(firebase_service):
    """Ensure clean Firebase state for each test"""
    await firebase_service.cleanup_test_data()
    assert await firebase_service.verify_cleanup(), "Firebase cleanup failed"
    yield
    await firebase_service.cleanup_test_data()
    assert await firebase_service.verify_cleanup(), "Firebase cleanup failed"
@pytest.fixture(scope='function')
def test_user_id():
    """Provide test user ID"""
    return FirebaseService.DEFAULT_TEST_USER_ID
def safe_cache_operation(operation):
    """Wrapper for safe cache operations"""
    try:
        return operation()
    except Exception as e:
        print(f"Cache operation failed: {str(e)}")
        return None
@pytest.fixture(autouse=True)
def use_test_cache():
    """Use local memory cache for testing"""
    with override_settings(CACHES=TEST_CACHE):
        yield

@pytest.fixture(scope='session', autouse=True)
def setup_firebase():
    """Initialize Firebase for testing"""
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.FIREBASE_ADMIN_CREDENTIALS)
            firebase_admin.initialize_app(cred, {
                'databaseURL': settings.FIREBASE_DATABASE_URL
            })
    except Exception as e:
        pytest.fail(f"Failed to initialize Firebase: {e}")


@pytest.fixture(scope='function')
def firebase_service():
    """Provide FirebaseService instance"""
    return FirebaseService()

@pytest.fixture(autouse=True)
def clear_test_data(firebase_service):
    """Clean up test data before and after each test"""
    def cleanup():
        try:
            # Clear test locations using value-based query
            locations_ref = firebase_service.db.child('locations')
            locations_ref.get(shallow=True)  # Verify connection
            
            # Get all locations and filter locally
            all_locations = locations_ref.get()
            if all_locations:
                for loc_id, loc_data in all_locations.items():
                    if isinstance(loc_data, dict) and loc_data.get('createdBy') == TEST_USER_ID:
                        locations_ref.child(loc_id).delete()

            # Clear test user locations
            firebase_service.db.child('userLocations').child(TEST_USER_ID).delete()
            
        except Exception as e:
            print(f"Error in cleanup: {str(e)}")

    cleanup()
    yield
    cleanup()

@pytest.fixture(autouse=True)
def clear_test_data(firebase_service):
    """Remove existing fixture and replace with this one"""
    pass  # Let setup_test_environment handle cleanup

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after each test"""
    try:
        cache.clear()
    except Exception:
        pass  # Ignore cache errors in tests
    yield
    try:
        cache.clear()
    except Exception:
        pass

@pytest.fixture(scope='function')
def test_location_data(test_user_id):
    """Test location data fixture with consistent test user ID"""
    return {
        "name": "Test Location",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "user_id": test_user_id,
        "description": "Test location for unit tests",
        "category": "test",
        "instagram_data": {
            "url": "https://instagram.com/test",
            "post_id": "test123",
            "likes": 100,
            "comments": 10
        }
    }
@pytest.fixture(autouse=True)
async def cleanup_before_test(firebase_service):
    """Clean up before each test"""
    await firebase_service.cleanup_test_data()
    yield
    await firebase_service.cleanup_test_data()

class TestFirebaseService:
    """Test cases for FirebaseService"""
    
    async def test_initialization(self, firebase_service):
        """Test service initialization"""
        assert firebase_service is not None
        assert firebase_service.db is not None
        
        # Test database connection
        try:
            result = firebase_service.db.get()
            assert result is not None or result == {}
        except Exception as e:
            pytest.fail(f"Database connection failed: {str(e)}")
    
    async def test_save_location_success(self, firebase_service):
        """Test successful location save"""
        try:
            location_id, location_data = await firebase_service.save_location(TEST_LOCATION_DATA)
            
            assert location_id is not None
            assert location_data['name'] == TEST_LOCATION_DATA['name']
            assert location_data['latitude'] == TEST_LOCATION_DATA['latitude']
            assert location_data['longitude'] == TEST_LOCATION_DATA['longitude']

            # Verify in Firebase
            saved_data = firebase_service.db.child('locations').child(location_id).get()
            assert saved_data is not None
            assert saved_data['name'] == TEST_LOCATION_DATA['name']
            
            # Verify cache (if available)
            cached_data = safe_cache_operation(
                lambda: cache.get(f'location_{location_id}')
            )
            if cached_data:
                assert cached_data['name'] == TEST_LOCATION_DATA['name']
            
        except Exception as e:
            pytest.fail(f"Test failed: {str(e)}")
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.firebase_service = FirebaseService()
        cls.test_user_id = "test_user_123"
        cls.test_location_data = {
            "name": "Test Location",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "user_id": cls.test_user_id,
            "description": "Test location for unit tests",
            "category": "test"
        }

    def setUp(self):
        """Setup for each test"""
        self.clear_test_data()
        cache.clear()  # Clear cache before each test

    def tearDown(self):
        """Cleanup after each test"""
        self.clear_test_data()
        cache.clear()  # Clear cache after each test

    def clear_test_data(self):
        """Clear test data from Firebase"""
        try:
            # Clear test locations
            test_locations = self.firebase_service.db.child('locations')\
                .order_by_child('createdBy')\
                .equal_to(self.test_user_id)\
                .get()
                
            if test_locations:
                for location_id in test_locations.keys():
                    self.firebase_service.db.child('locations')\
                        .child(location_id)\
                        .delete()

            # Clear test user locations
            self.firebase_service.db.child('userLocations')\
                .child(self.test_user_id)\
                .delete()
                
        except Exception as e:
            logger.error(f"Error clearing test data: {str(e)}")


    async def test_search_with_filters(self, firebase_service):
        """Test location search with different filters"""
        location_ids = []
        try:
            # First clean up any existing data
            await firebase_service.delete_all_data()

            # Create test data
            test_locations = [
                {
                    "name": "Coffee Shop",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "category": "cafe",
                    "user_id": "test_user_123",
                    "description": "Test cafe"
                },
                {
                    "name": "Restaurant",
                    "latitude": 40.7129,  # Very close to first location
                    "longitude": -74.0061,
                    "category": "food",
                    "user_id": "test_user_123",
                    "description": "Test restaurant"
                },
                {
                    "name": "Far Place",
                    "latitude": 41.7128,  # Much further away
                    "longitude": -75.0060,
                    "category": "other",
                    "user_id": "test_user_123",
                    "description": "Far location"
                }
            ]
            
            # Save test locations
            for loc in test_locations:
                loc_id, _ = await firebase_service.save_location(loc)
                location_ids.append(loc_id)

            # Test category filter
            cafe_results = await firebase_service.search_locations(category="cafe")
            assert len(cafe_results) == 1, f"Expected 1 cafe, got {len(cafe_results)}"
            assert cafe_results[0]['name'] == "Coffee Shop"

            # Test proximity search
            nearby_results = await firebase_service.search_locations(
                center_lat=40.7128,
                center_lng=-74.0060,
                radius_km=0.5
            )
            assert len(nearby_results) == 2, \
                f"Expected 2 nearby locations, got {len(nearby_results)}"
            names = {r['name'] for r in nearby_results}
            assert 'Coffee Shop' in names
            assert 'Restaurant' in names
            assert 'Far Place' not in names

        except Exception as e:
            pytest.fail(f"Test failed: {str(e)}")
            
        finally:
            # Clean up
            for loc_id in location_ids:
                try:
                    await firebase_service.delete_location(loc_id, "test_user_123")
                except Exception as e:
                    logger.warning(f"Cleanup failed for location {loc_id}: {e}")

    @pytest.mark.asyncio
    async def test_user_specific_operations(self, firebase_service):
        """Test user permission handling"""
        location_id = None
        try:
            # Create location as user1
            location_data = {
                "name": "User Test Location",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "user_id": "user1",
                "category": "test"
            }
            
            # Save as user1
            location_id, saved_data = await firebase_service.save_location(location_data)
            
            # Try to update as user2 (should fail)
            update_data = {
                "name": "Unauthorized Update",
                "version": saved_data['version']
            }
            
            with pytest.raises(FirebaseServiceError) as exc_info:
                await firebase_service.update_location(
                    location_id,
                    "user2",  # Different user
                    update_data
                )
            assert "Unauthorized" in str(exc_info.value)
            
            # Try to delete as user2 (should fail)
            with pytest.raises(FirebaseServiceError) as exc_info:
                await firebase_service.delete_location(location_id, "user2")
            assert "Unauthorized" in str(exc_info.value)

        finally:
            # Cleanup with original user
            if location_id:
                try:
                    await firebase_service.delete_location(location_id, "user1")
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")
    async def test_bulk_operations(self, firebase_service):
        """Test bulk operations with proper cleanup"""
        location_ids = []
        try:
            # Create multiple locations
            for i in range(5):
                location_data = {
                    "name": f"Test Location {i}",
                    "latitude": 40.7128 + (i * 0.001),
                    "longitude": -74.0060 + (i * 0.001),
                    "user_id": "test_user_123",
                    "category": "test"
                }
                
                loc_id, _ = await firebase_service.save_location(location_data)
                location_ids.append(loc_id)

            assert len(location_ids) == 5

        except Exception as e:
            pytest.fail(f"Test failed: {str(e)}")

        finally:
            # Clean up
            for loc_id in location_ids:
                try:
                    await firebase_service.delete_location(loc_id, "test_user_123")
                except Exception as e:
                    logger.warning(f"Cleanup failed for location {loc_id}: {e}")
    async def test_save_location_validation(self, firebase_service):
        """Test location validation"""
        test_cases = [
            {
                "case": "Missing latitude",
                "data": {
                    "name": "Test Location",
                    "longitude": -74.0060,
                    "user_id": TEST_USER_ID
                },
                "expected_error": "Missing required fields: latitude"
            },
            {
                "case": "Invalid latitude type",
                "data": {
                    "name": "Test Location",
                    "latitude": "not-a-number",
                    "longitude": -74.0060,
                    "user_id": TEST_USER_ID
                },
                "expected_error": "Validation failed: latitude must be a valid number"
            },
            {
                "case": "Invalid latitude range",
                "data": {
                    "name": "Test Location",
                    "latitude": 91.0,
                    "longitude": -74.0060,
                    "user_id": TEST_USER_ID
                },
                "expected_error": "Validation failed: latitude must be between -90 and 90"
            }
        ]

        for test_case in test_cases:
            with pytest.raises(FirebaseServiceError) as exc_info:
                await firebase_service.save_location(test_case["data"])
            assert test_case["expected_error"] in str(exc_info.value), \
                f"Test case '{test_case['case']}' failed"
    
    async def test_get_user_locations(self, firebase_service, test_location_data):
        """Test retrieving user locations"""
        location_ids = []
        try:
            # First clean up any existing test data
            await firebase_service.cleanup_test_data()
            
            # Create test locations using service method
            location_ids = await firebase_service.create_test_data(3)
            
            # Verify all locations were created
            assert len(location_ids) == 3, "Failed to create all test locations"
            
            # Small delay to ensure Firebase consistency
            await asyncio.sleep(1)
            
            # Get user locations
            user_locations = await firebase_service.get_user_locations(firebase_service.test_user_id)
            
            # Verify location count and data
            assert len(user_locations) == 3, \
                f"Expected 3 locations, got {len(user_locations)}"

            # Verify all created locations are present
            retrieved_ids = {loc.get('id') for loc in user_locations}
            assert all(loc_id in retrieved_ids for loc_id in location_ids), \
                "Not all created locations were retrieved"

        except Exception as e:
            logger.error(f"Test failed: {str(e)}", exc_info=True)
            pytest.fail(f"Test failed: {e}")
            
        finally:
            # Cleanup
            try:
                await firebase_service.cleanup_test_data()
            except Exception as e:
                logger.warning(f"Final cleanup failed: {e}")

    async def test_update_location(self, firebase_service):
        """Test location update"""
        # Create initial location
        location_id, original_data = await firebase_service.save_location(TEST_LOCATION_DATA)
        
        # Update the location
        update_data = {
            "name": "Updated Location Name",
            "description": "Updated description"
        }
        
        updated_data = await firebase_service.update_location(
            location_id,
            TEST_USER_ID,
            update_data
        )
        
        assert updated_data['name'] == update_data['name']
        assert updated_data['description'] == update_data['description']
        assert updated_data['version'] == original_data['version'] + 1

    async def reset_test_data(self, firebase_service, user_id: str) -> None:
        """Complete reset of test data"""
        try:
            # Delete all locations for the test user
            locations_ref = firebase_service.db.child('locations')
            user_locations_ref = firebase_service.db.child('userLocations').child(user_id)
            
            try:
                # Get all locations first
                all_locations = locations_ref.get()
                if all_locations:
                    delete_tasks = []
                    for loc_id, loc_data in all_locations.items():
                        if isinstance(loc_data, dict) and loc_data.get('createdBy') == user_id:
                            logger.info(f"Deleting location {loc_id}")
                            # Delete location
                            locations_ref.child(loc_id).delete()
                            # Delete user location reference
                            user_locations_ref.child(loc_id).delete()
                
                # Verify deletion
                remaining = locations_ref.order_by_child('createdBy').equal_to(user_id).get()
                if remaining:
                    logger.warning(f"Found {len(remaining)} remaining locations after cleanup")
                    
            except Exception as e:
                logger.error(f"Error during location cleanup: {e}")
                raise

        except Exception as e:
            logger.error(f"Reset failed: {e}")
            raise

    async def create_test_locations(
        self,
        firebase_service,
        base_data: Dict,
        count: int = 3
    ) -> List[Dict]:
        """Create a set of test locations"""
        locations = []
        base_lat = 40.7128
        base_lng = -74.0060
        
        categories = ['cafe', 'food', 'outdoor']
        names = ['Downtown Coffee Shop', 'Italian Restaurant', 'Central Park']
        
        for i in range(count):
            location_data = {
                **base_data,
                "name": names[i],
                "category": categories[i],
                "description": f"Test location {i+1}",
                "latitude": base_lat + (i * 0.0001),  # Small increments for nearby locations
                "longitude": base_lng + (i * 0.0001),
                "createdAt": (datetime.now(timezone.utc) - timedelta(days=i)).isoformat()
            }
            
            try:
                location_id, data = await firebase_service.save_location(location_data)
                locations.append((location_id, data))
                logger.info(f"Created test location: {location_id} - {data['name']}")
            except Exception as e:
                logger.error(f"Failed to create test location: {e}")
                raise
                
        return locations        

    async def test_delete_location(self, firebase_service):
        """Test location deletion"""
        # Create a location
        location_id, _ = await firebase_service.save_location(TEST_LOCATION_DATA)
        
        # Delete the location
        result = await firebase_service.delete_location(location_id, TEST_USER_ID)
        assert result is True
        
        # Verify deletion
        deleted_location = firebase_service.db.child('locations')\
            .child(location_id)\
            .get()
        assert deleted_location is None
        
        deleted_user_location = firebase_service.db.child('userLocations')\
            .child(TEST_USER_ID)\
            .child(location_id)\
            .get()
        assert deleted_user_location is None

    @pytest.mark.asyncio
    async def test_location_with_instagram_data(self, firebase_service, test_location_data):
        """Test saving location with Instagram data"""
        try:
            location_data = {
                **test_location_data,
                "is_instagram_source": True,
                "instagram_data": {
                    "url": "https://instagram.com/test",
                    "post_id": "test123",
                    "likes": 100
                }
            }
            
            location_id, saved_data = await firebase_service.save_location(location_data)
            assert saved_data['isInstagramSource'] is True
            assert 'instagramData' in saved_data
            
        except Exception as e:
            pytest.fail(f"Test failed: {e}")

    async def test_batch_location_operations(self, firebase_service, test_location_data):
        """Test batch operations"""
        try:
            # Create multiple locations
            batch_size = 3
            locations = []
            for i in range(batch_size):
                loc_data = {
                    **test_location_data,
                    "name": f"Test Location {i}"
                }
                location_id, data = await firebase_service.save_location(loc_data)
                locations.append((location_id, data))

            assert len(locations) == batch_size
            
        except Exception as e:
            pytest.fail(f"Test failed: {e}")

    @pytest.mark.asyncio
    async def test_error_handling(self, firebase_service):
        """Test error handling scenarios"""
        try:
            # Test invalid latitude type
            invalid_data = {
                "name": "Invalid Location",
                "latitude": "not-a-number",  # Invalid type
                "longitude": -74.0060,
                "user_id": TEST_USER_ID
            }
            
            with pytest.raises(FirebaseServiceError) as exc_info:
                await firebase_service.save_location(invalid_data)
            assert "latitude must be a valid number" in str(exc_info.value)

            # Test missing required field
            missing_data = {
                "latitude": 40.7128,
                "longitude": -74.0060,
                "user_id": TEST_USER_ID
                # Missing name
            }
            
            with pytest.raises(FirebaseServiceError) as exc_info:
                await firebase_service.save_location(missing_data)
            assert "Missing required fields" in str(exc_info.value)

            # Test invalid coordinate range
            out_of_range_data = {
                "name": "Out of Range",
                "latitude": 91.0,  # Invalid latitude
                "longitude": -74.0060,
                "user_id": TEST_USER_ID
            }
            
            with pytest.raises(FirebaseServiceError) as exc_info:
                await firebase_service.save_location(out_of_range_data)
            assert "latitude must be between -90 and 90" in str(exc_info.value)

        except Exception as e:
            pytest.fail(f"Test failed: {str(e)}")


    @pytest.mark.asyncio
    async def test_cache_operations(self, firebase_service):
        """Test cache operations"""
        location_id = None
        try:
            # Clear cache first
            cache.clear()
            
            # Create test location
            location_data = {
                "name": "Cache Test Location",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "user_id": "test_user_123",
                "category": "test"
            }
            
            # Save location
            location_id, saved_data = await firebase_service.save_location(location_data)
            
            # Verify initial cache
            cache_key = f'location_{location_id}'
            cached_data = cache.get(cache_key)
            assert cached_data is not None, "Cache was not set after save"
            assert cached_data['name'] == location_data['name']
            
            # Update location
            update_data = {
                "name": "Updated Cache Location",
                "version": saved_data['version']
            }
            
            updated_data = await firebase_service.update_location(
                location_id,
                "test_user_123",
                update_data
            )
            
            # Verify cache was updated
            updated_cache = cache.get(cache_key)
            assert updated_cache is not None, "Cache was not updated"
            assert updated_cache['name'] == "Updated Cache Location"
            
        except Exception as e:
            pytest.fail(f"Test failed: {str(e)}")
            
        finally:
            if location_id:
                try:
                    await firebase_service.delete_location(location_id, "test_user_123")
                    cache.delete(f'location_{location_id}')
                except Exception as e:
                    logger.warning(f"Cleanup failed: {str(e)}")

    async def test_location_search(self, firebase_service, test_location_data):
        """Test location search functionality"""
        try:
            # Create test locations
            test_locations = [
                {
                    **test_location_data,
                    "name": "Coffee Shop",
                    "category": "cafe",
                    "latitude": 40.7128,
                    "longitude": -74.0060
                },
                {
                    **test_location_data,
                    "name": "Restaurant",
                    "category": "food",
                    "latitude": 40.7129,
                    "longitude": -74.0061
                }
            ]

            # Save test locations
            saved_locations = []
            for loc_data in test_locations:
                try:
                    location_id, data = await firebase_service.save_location(loc_data)
                    saved_locations.append((location_id, data))
                    logger.info(f"Saved location {location_id}: {data}")
                except Exception as save_error:
                    logger.error(f"Failed to save location: {str(save_error)}")
                    continue

            # Ensure we have saved locations before testing search
            assert len(saved_locations) > 0, "Failed to save test locations"

            # Test category search
            try:
                cafe_locations = await firebase_service.search_locations(category="cafe")
                assert len(cafe_locations) > 0, "No cafe locations found"
                assert any(loc["name"] == "Coffee Shop" for loc in cafe_locations), \
                    "Coffee Shop not found in results"
            except Exception as search_error:
                logger.error(f"Category search failed: {str(search_error)}")
                raise

            # Test proximity search with explicit error handling
            try:
                nearby_locations = await firebase_service.search_locations(
                    center_lat=40.7128,
                    center_lng=-74.0060,
                    radius_km=0.5
                )
                assert len(nearby_locations) > 0, "No nearby locations found"
                
                # Verify distance calculation
                for loc in nearby_locations:
                    distance = firebase_service._calculate_distance(
                        40.7128, -74.0060,
                        float(loc['latitude']), float(loc['longitude'])
                    )
                    assert distance <= 0.5, f"Location {loc['name']} is outside search radius"
                    
            except Exception as search_error:
                logger.error(f"Proximity search failed: {str(search_error)}")
                raise

        except Exception as e:
            logger.error(f"Test failed with error: {str(e)}")
            pytest.fail(f"Test failed: {str(e)}")

        finally:
            # Clean up test data
            for location_id, _ in saved_locations:
                try:
                    await firebase_service.delete_location(
                        location_id,
                        test_location_data['user_id']
                    )
                except Exception as del_error:
                    logger.warning(f"Cleanup failed for location {location_id}: {str(del_error)}")

    async def test_performance(self, firebase_service, test_location_data):
        """Test performance with multiple operations"""
        try:
            # Prepare test data
            num_locations = 5
            locations = []
            
            # Test save performance
            start_time = datetime.now()
            for i in range(num_locations):
                location_data = {
                    **test_location_data,
                    "name": f"Test Location {i}",
                    "latitude": 40.7128 + (i * 0.001),
                    "longitude": -74.0060 + (i * 0.001)
                }
                location_id, data = await firebase_service.save_location(location_data)
                locations.append((location_id, data))
            
            save_duration = (datetime.now() - start_time).total_seconds()
            assert save_duration < 5.0, f"Save operations took too long: {save_duration}s"

            # Test retrieval performance
            start_time = datetime.now()
            retrieved_locations = await firebase_service.get_user_locations(test_location_data['user_id'])
            retrieve_duration = (datetime.now() - start_time).total_seconds()
            assert retrieve_duration < 2.0, f"Retrieval took too long: {retrieve_duration}s"

        except Exception as e:
            pytest.fail(f"Performance test failed: {str(e)}")

     # Add a helper method for search functionality
    async def search_locations(
        self,
        category: Optional[str] = None,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        radius_km: Optional[float] = None
    ) -> List[Dict]:
        """Helper method for location search"""
        db = self.db.child('locations')
        
        # Get base query
        if category:
            results = db.order_by_child('category').equal_to(category).get()
        else:
            results = db.get()

        if not results:
            return []

        locations = []
        for loc_id, loc_data in results.items():
            if self._location_matches_criteria(
                loc_data,
                center_lat,
                center_lng,
                radius_km
            ):
                locations.append({
                    'id': loc_id,
                    **loc_data
                })

        return locations
    
    async def cleanup_all_test_locations(self, firebase_service, user_id):
        """Clean up all test locations for a user"""
        try:
            # Get all locations
            locations_ref = firebase_service.db.child('locations')
            all_locations = locations_ref.get()
            
            if all_locations:
                # Delete locations created by test user
                for loc_id, loc_data in all_locations.items():
                    if isinstance(loc_data, dict) and loc_data.get('createdBy') == user_id:
                        try:
                            # Delete from locations
                            locations_ref.child(loc_id).delete()
                            # Delete from user locations
                            firebase_service.db.child('userLocations')\
                                .child(user_id)\
                                .child(loc_id)\
                                .delete()
                            logger.info(f"Cleaned up location: {loc_id}")
                        except Exception as e:
                            logger.warning(f"Failed to delete location {loc_id}: {e}")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        
    def _location_matches_criteria(
        self,
        location: Dict,
        center_lat: Optional[float],
        center_lng: Optional[float],
        radius_km: Optional[float]
    ) -> bool:
        """Check if location matches search criteria"""
        if not (center_lat and center_lng and radius_km):
            return True

        loc_lat = location.get('latitude')
        loc_lng = location.get('longitude')
        if not (loc_lat and loc_lng):
            return False

        distance = self._calculate_distance(
            center_lat, center_lng,
            loc_lat, loc_lng
        )
        return distance <= radius_km

    def _calculate_distance(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
    ) -> float:
        """Calculate distance between two points in kilometers"""
        from math import sin, cos, sqrt, atan2, radians

        R = 6371  # Earth's radius in kilometers

        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    @staticmethod
    async def _cleanup_test_data(firebase_service):
        """Clean up all test data"""
        try:
            # Get all locations
            all_locations = firebase_service.db.child('locations').get()
            if all_locations:
                for loc_id, loc_data in all_locations.items():
                    if isinstance(loc_data, dict) and loc_data.get('createdBy') == TEST_USER_ID:
                        try:
                            # Delete from locations
                            firebase_service.db.child('locations').child(loc_id).delete()
                            # Delete from user locations
                            firebase_service.db.child('userLocations')\
                                .child(TEST_USER_ID)\
                                .child(loc_id)\
                                .delete()
                        except Exception as e:
                            logger.warning(f"Failed to delete test location {loc_id}: {e}")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    

if __name__ == '__main__':
    pytest.main(['-v', 'test_firebase_service.py'])