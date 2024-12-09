# apps/core/services/sync_manager.py
from django.utils import timezone
from django.db import transaction
from .firebase_service import FirebaseService
from ..models import Location, UserLocation
import logging

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self):
        self.firebase = FirebaseService()

    def sync_to_firebase(self, user_id):
        """Sync local data to Firebase"""
        try:
            with transaction.atomic():
                # Sync locations
                locations = Location.objects.filter(
                    sync_status__in=[0, 1]  # Not synced or syncing
                ).select_related('created_by')

                for location in locations:
                    location.sync_status = 1  # Syncing
                    location.save(update_fields=['sync_status'])

                    try:
                        self.firebase.sync_location(location)
                        location.sync_status = 2  # Synced
                        location.last_synced = timezone.now()
                        location.save(update_fields=['sync_status', 'last_synced'])
                    except Exception as e:
                        location.sync_status = 0  # Reset status
                        location.save(update_fields=['sync_status'])
                        raise e

                # Sync user locations
                user_locations = UserLocation.objects.filter(
                    user_id=user_id,
                    sync_status__in=[0, 1]
                ).select_related('location')

                for user_location in user_locations:
                    user_location.sync_status = 1
                    user_location.save(update_fields=['sync_status'])

                    try:
                        # Prepare user location data
                        data = {
                            'id': str(user_location.id),
                            'location_id': str(user_location.location.id),
                            'custom_name': user_location.custom_name,
                            'custom_description': user_location.custom_description,
                            'custom_category': user_location.custom_category,
                            'notes': user_location.notes,
                            'is_favorite': user_location.is_favorite,
                            'notify_enabled': user_location.notify_enabled,
                            'notify_radius': float(user_location.notify_radius),
                            'saved_at': user_location.saved_at.isoformat(),
                            'updated_at': user_location.updated_at.isoformat(),
                        }

                        # Save to Firebase
                        ref = self.firebase.db.child('user_locations')\
                            .child(user_id)\
                            .child(str(user_location.id))\
                            .set(data)

                        user_location.sync_status = 2
                        user_location.last_synced = timezone.now()
                        user_location.save(update_fields=['sync_status', 'last_synced'])
                    except Exception as e:
                        user_location.sync_status = 0
                        user_location.save(update_fields=['sync_status'])
                        raise e

            return True
        except Exception as e:
            logger.error(f"Error in sync_to_firebase: {str(e)}")
            raise

    def sync_from_firebase(self, user_id):
        """Sync data from Firebase to local database"""
        try:
            with transaction.atomic():
                # Sync locations
                firebase_locations = self.firebase.db.child('locations').get()
                
                if firebase_locations:
                    for firebase_id, data in firebase_locations.items():
                        try:
                            location = Location.objects.filter(
                                firebase_id=firebase_id
                            ).first()

                            if location:
                                # Update existing location
                                for key, value in data.items():
                                    setattr(location, key, value)
                                location.sync_status = 2
                                location.last_synced = timezone.now()
                                location.save()
                            else:
                                # Create new location
                                Location.objects.create(
                                    firebase_id=firebase_id,
                                    sync_status=2,
                                    last_synced=timezone.now(),
                                    **data
                                )
                        except Exception as e:
                            logger.error(f"Error syncing location {firebase_id}: {str(e)}")

                # Sync user locations
                firebase_user_locations = self.firebase.db.child('user_locations')\
                    .child(user_id)\
                    .get()

                if firebase_user_locations:
                    for firebase_id, data in firebase_user_locations.items():
                        try:
                            user_location = UserLocation.objects.filter(
                                firebase_id=firebase_id
                            ).first()

                            if user_location:
                                # Update existing user location
                                for key, value in data.items():
                                    if key != 'location_id':  # Don't update relationship
                                        setattr(user_location, key, value)
                                user_location.sync_status = 2
                                user_location.last_synced = timezone.now()
                                user_location.save()
                            else:
                                # Create new user location
                                UserLocation.objects.create(
                                    firebase_id=firebase_id,
                                    user_id=user_id,
                                    sync_status=2,
                                    last_synced=timezone.now(),
                                    **data
                                )
                        except Exception as e:
                            logger.error(f"Error syncing user location {firebase_id}: {str(e)}")

            return True
        except Exception as e:
            logger.error(f"Error in sync_from_firebase: {str(e)}")
            raise