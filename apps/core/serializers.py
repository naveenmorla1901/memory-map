from rest_framework import serializers

from .categories import CATEGORY_KEYS, normalize_category
from .models import SavedLocation
from .services.reels import canonicalize_reel_url


class SavedLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedLocation
        fields = [
            'id', 'name', 'description', 'notes', 'category',
            'latitude', 'longitude', 'address',
            'source', 'instagram_url',
            'is_favorite', 'visited', 'notify_enabled', 'notify_radius_km',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'name': {'trim_whitespace': True},
            'category': {'required': False},
        }

    def to_internal_value(self, data):
        # Be forgiving about category spelling ("Food", "cafe ") rather than
        # rejecting a whole save over it; unknown values become "other".
        if hasattr(data, 'copy') and 'category' in data:
            data = data.copy()
            data['category'] = normalize_category(data.get('category'))
        return super().to_internal_value(data)

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Name cannot be blank.')
        return value.strip()

    def validate_instagram_url(self, value):
        # Store one canonical form so "already saved from this reel" checks
        # match regardless of the share-tracking params in the link.
        return canonicalize_reel_url(value) if value else value

    def validate(self, attrs):
        source = attrs.get('source', getattr(self.instance, 'source', SavedLocation.SOURCE_MANUAL))
        instagram_url = attrs.get('instagram_url', getattr(self.instance, 'instagram_url', ''))
        if source == SavedLocation.SOURCE_INSTAGRAM and not instagram_url:
            raise serializers.ValidationError({'instagram_url': 'Required for places saved from Instagram.'})
        if instagram_url and 'source' not in attrs and self.instance is None:
            attrs['source'] = SavedLocation.SOURCE_INSTAGRAM
        return attrs


class BulkSavedLocationSerializer(serializers.Serializer):
    locations = SavedLocationSerializer(many=True)

    def validate_locations(self, value):
        if not value:
            raise serializers.ValidationError('Provide at least one location.')
        if len(value) > 20:
            raise serializers.ValidationError('At most 20 locations at a time.')
        return value


class CategorySerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=CATEGORY_KEYS)
    label = serializers.CharField()
    description = serializers.CharField()


class LocationStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    favorites = serializers.IntegerField()
    visited = serializers.IntegerField()
    from_instagram = serializers.IntegerField()
    by_category = serializers.DictField(child=serializers.IntegerField())


class ReelAnalysisRequestSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=500)

    def validate_url(self, value):
        from urllib.parse import urlparse
        host = (urlparse(value).hostname or '').lower()
        if host not in ('instagram.com', 'www.instagram.com', 'm.instagram.com', 'instagr.am'):
            raise serializers.ValidationError('Only Instagram links are supported.')
        return value


class ExtractedPlaceSerializer(serializers.Serializer):
    name = serializers.CharField()
    category = serializers.CharField()
    address = serializers.CharField(allow_blank=True)
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    confidence = serializers.FloatField()
    already_saved = serializers.BooleanField()


class ReelAnalysisResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['found', 'manual_required'])
    url = serializers.URLField()
    reason = serializers.CharField(required=False)
    caption = serializers.CharField(required=False, allow_blank=True)
    places = ExtractedPlaceSerializer(many=True, required=False)


class GeocodeResultSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField(allow_blank=True)
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    category = serializers.CharField()
