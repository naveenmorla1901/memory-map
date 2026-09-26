import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .categories import CATEGORY_CHOICES, DEFAULT_CATEGORY


class SavedLocation(models.Model):
    """
    A place one user saved. Deliberately owned by exactly one user: an
    earlier design shared a `Location` row between users' saves, which meant
    one user editing their save silently changed someone else's.
    """
    SOURCE_MANUAL = 'manual'
    SOURCE_INSTAGRAM = 'instagram'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Added manually'),
        (SOURCE_INSTAGRAM, 'From an Instagram reel'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_locations')

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=DEFAULT_CATEGORY)

    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    address = models.CharField(max_length=500, blank=True)

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    instagram_url = models.URLField(max_length=500, blank=True)

    is_favorite = models.BooleanField(default=False)
    visited = models.BooleanField(default=False)
    notify_enabled = models.BooleanField(default=False)
    notify_radius_km = models.FloatField(
        default=1.0, validators=[MinValueValidator(0.1), MaxValueValidator(50)]
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['user', 'is_favorite']),
            models.Index(fields=['user', 'instagram_url']),
        ]

    def __str__(self):
        return f'{self.name} ({self.user})'


class InstagramReelCache(models.Model):
    """
    Caches the result of analyzing an Instagram reel URL - its caption and
    the places extracted from it - keyed by URL. Extraction (a yt-dlp fetch,
    a Gemini call, and geocoding) is slow and not free, so re-shares of the
    same reel reuse this instead of re-running the pipeline.
    """
    STATUS_ANALYZED = 'analyzed'
    STATUS_NO_LOCATIONS = 'no_locations'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_ANALYZED, 'Analyzed'),
        (STATUS_NO_LOCATIONS, 'No Locations Found'),
        (STATUS_FAILED, 'Failed'),
    ]

    # Failures expire much sooner: they're more often transient (rate
    # limiting, a momentary outage) than a permanently unreadable reel.
    SUCCESS_MAX_AGE_DAYS = 30
    FAILURE_MAX_AGE_DAYS = 1

    url = models.URLField(max_length=500, unique=True)
    description = models.TextField(blank=True)
    locations = models.JSONField(default=list, blank=True)
    date_posted = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    failure_reason = models.TextField(blank=True)
    analyzed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-analyzed_at']

    def __str__(self):
        return f'{self.url} ({self.status})'

    def is_stale(self) -> bool:
        max_age = self.FAILURE_MAX_AGE_DAYS if self.status == self.STATUS_FAILED else self.SUCCESS_MAX_AGE_DAYS
        return (timezone.now() - self.analyzed_at) > timedelta(days=max_age)
