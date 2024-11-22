# apps/core/models.py
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

class Location(models.Model):
    LOCATION_TYPES = [
        ('manual', 'Manually Added'),
        ('instagram', 'From Instagram')
    ]
    
    SYNC_STATUS = [
        (0, 'Not Synced'),
        (1, 'Syncing'),
        (2, 'Synced')
    ]
    # Add new fields
    version = models.IntegerField(default=1)
    is_deleted = models.BooleanField(default=False)
    last_modified = models.DateTimeField(auto_now=True)  # Soft delete
    # Primary Fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    description = models.TextField(blank=True)
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPES, default='manual')
    category = models.CharField(max_length=100)
    address = models.TextField(blank=True)
    
    # Instagram-specific fields
    is_instagram_source = models.BooleanField(default=False)
    instagram_url = models.URLField(blank=True)
    date_posted = models.DateTimeField(null=True, blank=True)
    
    # Sync fields
    sync_status = models.IntegerField(choices=SYNC_STATUS, default=0)
    last_synced = models.DateTimeField(null=True, blank=True)
    firebase_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    # Add validation method
    def clean(self):
        super().clean()
        if self.latitude and (not -90 <= self.latitude <= 90):
            raise ValidationError({'latitude': 'Must be between -90 and 90'})
        if self.longitude and (not -180 <= self.longitude <= 180):
            raise ValidationError({'longitude': 'Must be between -180 and 180'})

    # Add method for soft delete
    def soft_delete(self):
        self.is_deleted = True
        self.save(update_fields=['is_deleted', 'updated_at'])
    class Meta:
        indexes = [
            # Spatial indexes
            models.Index(fields=['latitude', 'longitude']),
            
            # Category and type indexes
            models.Index(fields=['category']),
            models.Index(fields=['location_type']),
            
            # Instagram-related index
            models.Index(fields=['is_instagram_source', 'instagram_url']),
            
            # Sync-related indexes
            models.Index(fields=['sync_status']),
            models.Index(fields=['firebase_id']),
            
            # Timestamp index
            models.Index(fields=['-created_at']),
            models.Index(fields=['version']),
            models.Index(fields=['is_deleted', 'sync_status'])  # For ordering
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.latitude}, {self.longitude})"

class UserLocation(models.Model):
    SYNC_STATUS = [
        (0, 'Not Synced'),
        (1, 'Syncing'),
        (2, 'Synced')
    ]
    
    # Primary Fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, related_name='saved_locations', on_delete=models.CASCADE)
    location = models.ForeignKey(Location, related_name='saved_by', on_delete=models.CASCADE)
    
    # User customization
    custom_name = models.CharField(max_length=255, blank=True)
    custom_description = models.TextField(blank=True)
    custom_category = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    
    # Preferences
    is_favorite = models.BooleanField(default=False)
    notify_enabled = models.BooleanField(default=False)
    notify_radius = models.FloatField(default=1.0)  # in kilometers
    
    # Sync fields
    sync_status = models.IntegerField(choices=SYNC_STATUS, default=0)
    last_synced = models.DateTimeField(null=True, blank=True)
    firebase_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Timestamps
    saved_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'location']
        indexes = [
            # User-related indexes
            models.Index(fields=['user', 'sync_status']),
            models.Index(fields=['user', 'saved_at']),  # Changed from created_at to saved_at
            
            # Location-related indexes
            models.Index(fields=['location', 'is_favorite']),
            
            # Feature-specific indexes
            models.Index(fields=['notify_enabled']),
            models.Index(fields=['sync_status']),
            
            # Timestamp index
            models.Index(fields=['-saved_at']),
            # models.Index(fields=['version']),
            # models.Index(fields=['is_deleted', 'sync_status'])  # For ordering
        ]
        ordering = ['-saved_at']

    def __str__(self):
        return f"{self.user.username}'s save of {self.location.name}"
    
class InstagramReel(models.Model):
    url = models.URLField(unique=True)
    location = models.ForeignKey(Location, related_name='reels', on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    date_posted = models.DateTimeField(null=True, blank=True)
    date_extracted = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        indexes = [
            models.Index(fields=['url']),
            models.Index(fields=['created_by']),
            models.Index(fields=['date_posted']),
        ]
        ordering = ['-date_posted']

    def __str__(self):
        return f"Reel by {self.created_by.username} at {self.location.name}"