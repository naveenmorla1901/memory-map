import os
import json
import firebase_admin
from firebase_admin import credentials
import logging
from apps.core.services.firebase_service import FirebaseService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_service_account():
    """Verify service account file exists and is valid"""
    try:
        # Get the path to the service account key
        current_dir = os.path.dirname(os.path.abspath(__file__))
        service_account_path = os.path.join(current_dir, '..', 'secrets', 'serviceAccountKey.json')
        
        # Check if file exists
        if not os.path.exists(service_account_path):
            logger.error(f"❌ Service account key not found at: {service_account_path}")
            return False
            
        # Try to read and parse JSON
        with open(service_account_path, 'r') as f:
            creds = json.load(f)
            
        required_fields = [
            'type',
            'project_id',
            'private_key_id',
            'private_key',
            'client_email',
            'client_id',
        ]
        
        # Check required fields
        for field in required_fields:
            if field not in creds:
                logger.error(f"❌ Missing required field in service account key: {field}")
                return False
                
        logger.info("✅ Service account key is valid")
        return True
        
    except json.JSONDecodeError:
        logger.error("❌ Service account key is not valid JSON")
        return False
    except Exception as e:
        logger.error(f"❌ Error verifying service account: {str(e)}")
        return False

def verify_firebase_connection():
    """Verify Firebase connection works"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        service_account_path = os.path.join(current_dir, '..', 'secrets', 'serviceAccountKey.json')
        
        # Initialize Firebase
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        
        logger.info("✅ Successfully connected to Firebase")
        return True
        
    except Exception as e:
        logger.error(f"❌ Firebase connection error: {str(e)}")
        return False

def main():
    logger.info("\nVerifying Firebase setup...")
    
    # Verify service account
    if not verify_service_account():
        return
        
    # Verify Firebase connection
    if not verify_firebase_connection():
        return
        
    logger.info("\n🎉 Firebase setup verification complete!")

if __name__ == '__main__':
    main()