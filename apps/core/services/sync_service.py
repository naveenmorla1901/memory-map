# apps/core/services/sync_service.py
from django.utils import timezone
from django.conf import settings
import firebase_admin
from firebase_admin import credentials, db
from ..models import Location, UserLocation
import logging
import json
from typing import Dict
import asyncio
from .firebase_service import FirebaseSyncError

logger = logging.getLogger(__name__)

class SyncService:
    def __init__(self):
        if not firebase_admin._apps:
            try:
                if settings.FIREBASE_ADMIN_CREDENTIALS is None:
                    raise ValueError("Firebase Admin credentials not found")
                
                # Initialize with credentials from JSON file
                cred = credentials.Certificate(settings.FIREBASE_ADMIN_SDK_PATH)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': settings.FIREBASE_CONFIG['databaseURL']
                })
                logger.info("Firebase initialized successfully")
            except Exception as e:
                logger.error(f"Firebase initialization error: {str(e)}")
                raise
                
        self.db = db.reference()

    async def sync_with_conflict_resolution(self) -> Dict[str, int]:
        """Sync with conflict resolution"""
        try:
            stats = {
                'synced': 0,
                'conflicts': 0,
                'errors': 0
            }
            
            # Get local changes
            local_changes = await self.get_unsynced_changes()
            
            for change in local_changes:
                try:
                    remote_data = await self.get_remote_data(change.id)
                    
                    if self.has_conflict(change, remote_data):
                        resolved_data = await self.resolve_conflict(change, remote_data)
                        await self.apply_resolution(resolved_data)
                        stats['conflicts'] += 1
                    else:
                        await self.sync_change(change)
                        stats['synced'] += 1
                        
                except Exception as e:
                    logger.error(f"Sync error for {change.id}: {str(e)}")
                    stats['errors'] += 1
                    
            return stats
            
        except Exception as e:
            logger.error(f"Sync failed: {str(e)}")
            raise FirebaseSyncError(str(e))
    async def sync_with_retry(self, retries: int = 3) -> bool:
        """Sync with retry mechanism"""
        for attempt in range(retries):
            try:
                await self.perform_sync()
                return True
            except ConnectionError:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        return False
        
    async def resolve_conflict(
        self,
        local_data: dict,
        remote_data: dict
    ) -> dict:
        """Enhanced conflict resolution"""
        # Compare versions first
        if remote_data['version'] > local_data['version']:
            return remote_data
            
        # If versions are equal, compare timestamps
        local_time = self._parse_date(local_data['updated_at'])
        remote_time = self._parse_date(remote_data['updated_at'])
        
        return remote_data if remote_time > local_time else local_data
    
    def sync_location_to_firebase(self, location):
        """Sync a single location to Firebase"""
        try:
            ref = self.db.child('locations').child(str(location.id))
            
            data = {
                'name': location.name,
                'latitude': float(location.latitude),
                'longitude': float(location.longitude),
                'description': location.description,
                'category': location.category,
                'is_instagram_source': location.is_instagram_source,
                'instagram_url': location.instagram_url,
                'address': location.address,
                'created_at': location.created_at.isoformat(),
                'updated_at': location.updated_at.isoformat()
            }
            
            ref.set(data)
            
            # Update sync status
            location.sync_status = 2  # Synced
            location.last_synced = timezone.now()
            location.firebase_id = str(location.id)
            location.save(update_fields=['sync_status', 'last_synced', 'firebase_id'])
            
            return True
            
        except Exception as e:
            logger.error(f"Error syncing location {location.id}: {str(e)}")
            return False

    def sync_user_location_to_firebase(self, user_location):
        """Sync a single user location to Firebase"""
        try:
            ref = self.db.child('user_locations').child(str(user_location.user.id)).child(str(user_location.id))
            
            data = {
                'location_id': str(user_location.location.id),
                'custom_name': user_location.custom_name,
                'custom_description': user_location.custom_description,
                'custom_category': user_location.custom_category,
                'notes': user_location.notes,
                'is_favorite': user_location.is_favorite,
                'notify_enabled': user_location.notify_enabled,
                'notify_radius': float(user_location.notify_radius),
                'saved_at': user_location.saved_at.isoformat(),
                'updated_at': user_location.updated_at.isoformat()
            }
            
            ref.set(data)
            
            # Update sync status
            user_location.sync_status = 2  # Synced
            user_location.last_synced = timezone.now()
            user_location.firebase_id = str(user_location.id)
            user_location.save(update_fields=['sync_status', 'last_synced', 'firebase_id'])
            
            return True
            
        except Exception as e:
            logger.error(f"Error syncing user location {user_location.id}: {str(e)}")
            return False

    def sync_from_firebase(self, user_id):
        """Sync data from Firebase to local database"""
        try:
            # Sync locations
            locations_ref = self.db.child('locations').get()
            if locations_ref:
                for firebase_id, data in locations_ref.items():
                    Location.objects.update_or_create(
                        id=firebase_id,
                        defaults={
                            'name': data['name'],
                            'latitude': data['latitude'],
                            'longitude': data['longitude'],
                            'description': data.get('description', ''),
                            'category': data['category'],
                            'is_instagram_source': data['is_instagram_source'],
                            'instagram_url': data.get('instagram_url', ''),
                            'address': data.get('address', ''),
                            'sync_status': 2,
                            'last_synced': timezone.now(),
                            'firebase_id': firebase_id
                        }
                    )

            # Sync user locations
            user_locations_ref = self.db.child('user_locations').child(str(user_id)).get()
            if user_locations_ref:
                for firebase_id, data in user_locations_ref.items():
                    UserLocation.objects.update_or_create(
                        id=firebase_id,
                        user_id=user_id,
                        defaults={
                            'location_id': data['location_id'],
                            'custom_name': data.get('custom_name', ''),
                            'custom_description': data.get('custom_description', ''),
                            'custom_category': data.get('custom_category', ''),
                            'notes': data.get('notes', ''),
                            'is_favorite': data['is_favorite'],
                            'notify_enabled': data['notify_enabled'],
                            'notify_radius': data['notify_radius'],
                            'sync_status': 2,
                            'last_synced': timezone.now(),
                            'firebase_id': firebase_id
                        }
                    )
                    
            return True
            
        except Exception as e:
            logger.error(f"Error syncing from Firebase: {str(e)}")
            return False