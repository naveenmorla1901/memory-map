import os
import json
import requests
import firebase_admin
import time
from firebase_admin import auth, credentials
import logging
from datetime import datetime
import pytest
from apps.core.services.firebase_service import FirebaseService
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)





@pytest.fixture
def firebase_service():
    return FirebaseService()

@pytest.mark.asyncio
async def test_create_user_profile(firebase_service):
    user_data = {
        'email': 'test@example.com',
        'display_name': 'Test User'
    }
    profile = await firebase_service.create_user_profile('test_user_id', user_data)
    assert profile['email'] == user_data['email']
    assert profile['displayName'] == user_data['display_name']

@pytest.mark.asyncio
async def test_save_location(firebase_service):
    location_data = {
        'name': 'Test Location',
        'latitude': 40.7128,
        'longitude': -74.0060,
        'user_id': 'test_user_id'
    }
    location_id = await firebase_service.save_location(location_data)
    assert location_id is not None
# Firebase configuration
FIREBASE_CONFIG = {
    'apiKey': "AIzaSyBOKAdTRz8J-9QSu8P7DEyLd6NAqqN0STI",
    'authDomain': "memory-map-78ad6.firebaseapp.com",
    'databaseURL': "https://memory-map-78ad6-default-rtdb.firebaseio.com",
    'projectId': "memory-map-78ad6",
    'storageBucket': "memory-map-78ad6.firebasestorage.app",
    'messagingSenderId': "293613109189",
    'appId': "1:293613109189:web:d2decb21864327465255ac",
    'measurementId': "G-DSD59LSN6W"
}

class FirebaseAuthTester:
    def __init__(self):
        self.BASE_URL = 'http://localhost:8002/api/v1'
        self.firebase_app = None
        self.test_user_email = f'test_{datetime.now().strftime("%Y%m%d%H%M%S")}@example.com'
        
    def initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            service_account_path = os.path.join(current_dir, '..', 'secrets', 'serviceAccountKey.json')
            
            if not os.path.exists(service_account_path):
                raise FileNotFoundError(f"Service account key not found at: {service_account_path}")

            if not firebase_admin._apps:
                cred = credentials.Certificate(service_account_path)
                self.firebase_app = firebase_admin.initialize_app(cred, {
                    'databaseURL': FIREBASE_CONFIG['databaseURL']
                })
                logger.info("✅ Firebase initialized successfully")
            else:
                self.firebase_app = firebase_admin.get_app()
                logger.info("✅ Using existing Firebase app")
                
        except Exception as e:
            logger.error(f"❌ Firebase initialization error: {str(e)}")
            raise

    def create_test_user(self):
        """Create a test user in Firebase"""
        try:
            # Create new user
            user = auth.create_user(
                email=self.test_user_email,
                password='TestPassword123!',
                display_name='Test User'
            )
            logger.info(f"✅ Created test user: {user.uid} ({self.test_user_email})")
            return user
        except Exception as e:
            logger.error(f"❌ Error creating user: {str(e)}")
            return None

    def get_id_token(self, custom_token):
        """Exchange custom token for ID token"""
        try:
            # URL for token exchange
            url = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyCustomToken"
            params = {
                'key': FIREBASE_CONFIG['apiKey']
            }
            data = {
                'token': custom_token.decode('utf-8'),
                'returnSecureToken': True
            }
            
            response = requests.post(url, params=params, json=data)
            if response.status_code == 200:
                id_token = response.json()['idToken']
                logger.info("✅ Exchanged custom token for ID token")
                return id_token
            else:
                logger.error(f"❌ Token exchange failed: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting ID token: {str(e)}")
            return None

    def test_endpoints(self, id_token):
        """Test various API endpoints"""
        headers = {
            'Authorization': f'Bearer {id_token}',
            'Content-Type': 'application/json'
        }

        endpoints = [
            {'url': '/test-firebase/', 'name': 'Firebase Connection Test'},
            {'url': '/test-auth/', 'name': 'Authentication Test'},
            {'url': '/locations/', 'name': 'Locations API Test'}
        ]

        success = True
        for endpoint in endpoints:
            logger.info(f"\nTesting {endpoint['name']}...")
            try:
                response = requests.get(
                    f'{self.BASE_URL}{endpoint["url"]}',
                    headers=headers,
                    timeout=5
                )
                
                logger.info(f"Status code: {response.status_code}")
                if response.status_code == 200:
                    logger.info(f"Response: {json.dumps(response.json(), indent=2)}")
                    logger.info(f"✅ {endpoint['name']} successful!")
                else:
                    logger.error(f"❌ {endpoint['name']} failed!")
                    logger.error(f"Response: {response.text}")
                    success = False
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ {endpoint['name']} error: {str(e)}")
                success = False

        return success

    # Add these test scenarios to your existing test script


    def test_location_crud(self, id_token):
        """Test Location CRUD operations"""
        headers = {
            'Authorization': f'Bearer {id_token}',
            'Content-Type': 'application/json'
        }

        logger.info("\nTesting Location CRUD Operations...")

        # 1. Create a location
        create_data = {
            'name': 'Test Location',
            'latitude': 40.7128,
            'longitude': -74.0060,
            'description': 'Test location for CRUD operations',
            'category': 'test',
            'address': '123 Test St'
        }

        try:
            # Create
            logger.info("\nCreating location...")
            response = requests.post(
                f'{self.BASE_URL}/locations/',
                headers=headers,
                json=create_data
            )
            
            if response.status_code == 201:
                location_id = response.json()['id']
                logger.info(f"✅ Location created successfully: {location_id}")
            else:
                logger.error(f"❌ Failed to create location: {response.text}")
                return False

            # Read
            logger.info("\nReading location...")
            response = requests.get(
                f'{self.BASE_URL}/locations/{location_id}/',
                headers=headers
            )
            
            if response.status_code == 200:
                logger.info("✅ Location retrieved successfully")
            else:
                logger.error(f"❌ Failed to retrieve location: {response.text}")
                return False

            # Update
            update_data = {
                'name': 'Updated Test Location',
                'description': 'Updated test description'
            }
            
            logger.info("\nUpdating location...")
            response = requests.patch(
                f'{self.BASE_URL}/locations/{location_id}/',
                headers=headers,
                json=update_data
            )
            
            if response.status_code == 200:
                logger.info("✅ Location updated successfully")
            else:
                logger.error(f"❌ Failed to update location: {response.text}")
                return False

            # Delete
            logger.info("\nDeleting location...")
            response = requests.delete(
                f'{self.BASE_URL}/locations/{location_id}/',
                headers=headers
            )
            
            if response.status_code == 204:
                logger.info("✅ Location deleted successfully")
            else:
                logger.error(f"❌ Failed to delete location: {response.text}")
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Error during Location CRUD test: {str(e)}")
            return False

    def test_instagram_integration(self, id_token):
        """Test Instagram integration with better error handling"""
        headers = {
            'Authorization': f'Bearer {id_token}',
            'Content-Type': 'application/json'
        }

        logger.info("\nTesting Instagram Integration...")

        test_cases = [
            {
                'test_name': 'Invalid URL',
                'url': 'https://www.instagram.com/reel/example-reel/',
                'expected_status': 400
            },
            {
                'test_name': 'Empty URL',
                'url': '',
                'expected_status': 400
            },
            {
                'test_name': 'Malformed URL',
                'url': 'not-a-url',
                'expected_status': 400
            }
        ]

        success = True
        for test_case in test_cases:
            try:
                logger.info(f"\nTesting {test_case['test_name']}...")
                response = requests.post(
                    f'{self.BASE_URL}/analyze-reel/',
                    headers=headers,
                    json={'url': test_case['url']}
                )

                logger.info(f"Status code: {response.status_code}")
                logger.info(f"Response: {json.dumps(response.json(), indent=2)}")

                if response.status_code == test_case['expected_status']:
                    logger.info(f"✅ {test_case['test_name']} test passed")
                else:
                    logger.error(f"❌ {test_case['test_name']} test failed")
                    success = False

            except Exception as e:
                logger.error(f"❌ Error during {test_case['test_name']} test: {str(e)}")
                success = False

        return success

    def test_data_validation(self, id_token):
        """Test data validation for locations"""
        headers = {
            'Authorization': f'Bearer {id_token}',
            'Content-Type': 'application/json'
        }

        logger.info("\nTesting Data Validation...")

        test_cases = [
            {
                'test_name': 'Invalid Latitude',
                'data': {
                    'name': 'Test Location',
                    'latitude': 91,  # Invalid: > 90
                    'longitude': 0,
                },
                'expected_status': 400
            },
            {
                'test_name': 'Invalid Longitude',
                'data': {
                    'name': 'Test Location',
                    'latitude': 0,
                    'longitude': 181,  # Invalid: > 180
                },
                'expected_status': 400
            },
            {
                'test_name': 'Missing Required Fields',
                'data': {
                    'name': 'Test Location'
                    # Missing lat/long
                },
                'expected_status': 400
            }
        ]

        success = True
        for test_case in test_cases:
            try:
                logger.info(f"\nTesting {test_case['test_name']}...")
                response = requests.post(
                    f'{self.BASE_URL}/locations/',
                    headers=headers,
                    json=test_case['data']
                )

                logger.info(f"Status code: {response.status_code}")
                logger.info(f"Response: {json.dumps(response.json(), indent=2)}")

                if response.status_code == test_case['expected_status']:
                    logger.info(f"✅ {test_case['test_name']} test passed")
                else:
                    logger.error(f"❌ {test_case['test_name']} test failed")
                    success = False

            except Exception as e:
                logger.error(f"❌ Error during {test_case['test_name']} test: {str(e)}")
                success = False

        return success

    def test_sync_operations(self, id_token):
        """Test Firebase sync operations"""
        headers = {
            'Authorization': f'Bearer {id_token}',
            'Content-Type': 'application/json'
        }

        logger.info("\nTesting Sync Operations...")

        try:
            # Test sync to Firebase
            logger.info("\nTesting sync to Firebase...")
            response = requests.post(
                f'{self.BASE_URL}/sync/to-firebase/',
                headers=headers
            )
            
            if response.status_code == 200:
                logger.info("✅ Sync to Firebase successful")
            else:
                logger.error(f"❌ Sync to Firebase failed: {response.text}")
                return False

            # Test sync from Firebase
            logger.info("\nTesting sync from Firebase...")
            response = requests.post(
                f'{self.BASE_URL}/sync/from-firebase/',
                headers=headers
            )
            
            if response.status_code == 200:
                logger.info("✅ Sync from Firebase successful")
            else:
                logger.error(f"❌ Sync from Firebase failed: {response.text}")
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Error during sync operations test: {str(e)}")
            return False

    
    def test_performance(self, id_token):
        """Test API performance"""
        headers = {
            'Authorization': f'Bearer {id_token}',
            'Content-Type': 'application/json'
        }

        logger.info("\nTesting API Performance...")

        endpoints = [
        {'url': '/locations/', 'method': 'GET', 'threshold': 3000},  # 3s
        {'url': '/test-firebase/', 'method': 'GET', 'threshold': 3000},  # 3s
        {'url': '/test-auth/', 'method': 'GET', 'threshold': 3000}  # 3s
    ]

        success = True
        for endpoint in endpoints:
            try:
                logger.info(f"\nTesting {endpoint['url']} performance...")
                start_time = time.time()
                
                if endpoint['method'] == 'GET':
                    response = requests.get(
                        f'{self.BASE_URL}{endpoint["url"]}',
                        headers=headers
                    )
                
                elapsed_time = (time.time() - start_time) * 1000  # Convert to ms
                
                logger.info(f"Response time: {elapsed_time:.2f}ms")
                
                if elapsed_time <= endpoint['threshold']:
                    logger.info(f"✅ Performance test passed")
                else:
                    logger.error(f"❌ Performance test failed - exceeded {endpoint['threshold']}ms threshold")
                    success = False

            except Exception as e:
                logger.error(f"❌ Error during performance test: {str(e)}")
                success = False

        return success
    def run_tests(self):
        """Run complete test suite"""
        logger.info("\nStarting Firebase Authentication Tests...")
        
        try:
            # Step 1: Create test user
            logger.info("\nStep 1: Creating test user...")
            user = self.create_test_user()
            if not user:
                return False

            # Step 2: Get custom token
            logger.info("\nStep 2: Getting custom token...")
            custom_token = auth.create_custom_token(user.uid)
            if not custom_token:
                return False
            logger.info("✅ Created custom token")

            # Step 3: Exchange for ID token
            logger.info("\nStep 3: Getting ID token...")
            id_token = self.get_id_token(custom_token)
            if not id_token:
                return False

            # Step 4: Run all tests
            logger.info("\nStep 4: Running all tests...")
            
            # Basic endpoint tests
            if not self.test_endpoints(id_token):
                return False
                
            # CRUD operations test
            if not self.test_location_crud(id_token):
                return False
                
            # Instagram integration test
            if not self.test_instagram_integration(id_token):
                return False
                
            # Data validation test
            if not self.test_data_validation(id_token):
                return False
                
            # Sync operations test
            if not self.test_sync_operations(id_token):
                return False
                
            # Performance test
            if not self.test_performance(id_token):
                return False

            return True

        except Exception as e:
            logger.error(f"\n❌ Test execution error: {str(e)}")
            return False

    def cleanup(self):
        """Clean up test user"""
        try:
            user = auth.get_user_by_email(self.test_user_email)
            auth.delete_user(user.uid)
            logger.info(f"✅ Deleted test user: {user.uid}")
        except Exception as e:
            logger.error(f"❌ Error cleaning up: {str(e)}")

def main():
    tester = FirebaseAuthTester()
    success = False
    
    try:
        tester.initialize_firebase()
        success = tester.run_tests()
        
        if success:
            logger.info("\n🎉 All tests passed!")
        else:
            logger.error("\n❌ Some tests failed!")
            
    except Exception as e:
        logger.error(f"\n❌ Test execution failed: {str(e)}")
    finally:
        if success:
            tester.cleanup()

if __name__ == '__main__':
    main()