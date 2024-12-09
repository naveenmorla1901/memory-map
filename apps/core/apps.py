# apps/core/apps.py
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        """
        Initialize any app-specific settings here.
        This is called when Django starts.
        """
        try:
            # Import and initialize Firebase Admin SDK
            import firebase_admin
            from firebase_admin import credentials
            from django.conf import settings
            from .services.firebase_service import FirebaseService
            FirebaseService()
            if not firebase_admin._apps:
                cred = credentials.Certificate(settings.FIREBASE_ADMIN_SDK_PATH)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': settings.FIREBASE_CONFIG['databaseURL']
                })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            print(f"Warning: Could not initialize Firebase: {e}")