# apps/core/serializers.py
from rest_framework import serializers
from .models import Location, InstagramReel, UserLocation

class InstagramReelSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramReel
        fields = ['id', 'url', 'description', 'likes', 'comments',
                 'date_posted', 'date_extracted', 'location']
        read_only_fields = ['id', 'date_extracted']

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            'id', 'name', 'latitude', 'longitude', 'description',
            'location_type', 'category', 'address',
            'is_instagram_source', 'instagram_url', 'date_posted',
            'sync_status', 'last_synced', 'firebase_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'sync_status', 'last_synced', 'firebase_id'
        ]

    def validate(self, data):
        if data.get('is_instagram_source'):
            if not data.get('instagram_url'):
                raise serializers.ValidationError({
                    'instagram_url': 'Instagram URL is required for Instagram locations'
                })
        
        if 'latitude' in data and 'longitude' in data:
            if not (-90 <= data['latitude'] <= 90):
                raise serializers.ValidationError({
                    'latitude': 'Latitude must be between -90 and 90'
                })
            if not (-180 <= data['longitude'] <= 180):
                raise serializers.ValidationError({
                    'longitude': 'Longitude must be between -180 and 180'
                })
        
        return data

class UserLocationSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True)
    location_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = UserLocation
        fields = [
            'id', 'user', 'location', 'location_id',
            'custom_name', 'custom_description', 'custom_category',
            'notes', 'is_favorite', 'notify_enabled', 'notify_radius',
            'sync_status', 'last_synced', 'firebase_id',
            'saved_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'sync_status', 'last_synced', 'firebase_id',
            'saved_at', 'updated_at'
        ]

    def validate_notify_radius(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                'Notification radius must be greater than 0'
            )
        return value

class LocationAnalysisSerializer(serializers.Serializer):
    """Serializer for Instagram reel analysis endpoint"""
    url = serializers.URLField(required=True)
    locations = LocationSerializer(many=True, read_only=True)
    likes = serializers.CharField(read_only=True)
    comments = serializers.CharField(read_only=True)
    date_posted = serializers.DateTimeField(read_only=True)