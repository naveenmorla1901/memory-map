# apps/core/services/reel_cache.py
import logging
from datetime import datetime
from typing import Optional

from django.utils import timezone as django_timezone

from ..instagram.analyzer import InstagramExtractionError, InstagramReelAnalyzer
from ..models import InstagramReelCache

logger = logging.getLogger(__name__)


def parse_instagram_date(date_str: Optional[str]):
    """Best-effort parse of whatever date format the reel's metadata came in."""
    if not date_str:
        return None
    for fmt in ('%Y%m%d', '%B %d, %Y', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S'):
        try:
            parsed = datetime.strptime(date_str, fmt)
            return django_timezone.make_aware(parsed) if django_timezone.is_naive(parsed) else parsed
        except (ValueError, TypeError):
            continue
    return None


def get_cached_analysis(url: str) -> Optional[InstagramReelCache]:
    """A fresh, successful cache entry for this URL, or None."""
    try:
        entry = InstagramReelCache.objects.get(url=url)
    except InstagramReelCache.DoesNotExist:
        return None
    if entry.status == InstagramReelCache.STATUS_FAILED or entry.is_stale():
        return None
    return entry


def get_cached_failure(url: str) -> Optional[InstagramReelCache]:
    """A recent failed attempt for this URL, so we don't hammer a broken/private reel."""
    try:
        entry = InstagramReelCache.objects.get(url=url, status=InstagramReelCache.STATUS_FAILED)
    except InstagramReelCache.DoesNotExist:
        return None
    if entry.is_stale():
        return None
    return entry


def store_analysis(url: str, **fields) -> InstagramReelCache:
    entry, _ = InstagramReelCache.objects.update_or_create(url=url, defaults=fields)
    return entry


def get_reel_analysis(url: str, google_api_key: str, ytdlp_cookies_file: Optional[str] = None) -> dict:
    """
    Returns {'description', 'locations', 'date_posted'} for a reel URL,
    using InstagramReelCache when available instead of re-running yt-dlp +
    Gemini for a URL we've already analyzed. Raises InstagramExtractionError
    (letting the caller fall back to manual entry) if extraction fails and
    nothing usable is cached.
    """
    cached = get_cached_analysis(url)
    if cached:
        logger.info(f"Using cached analysis for {url}")
        return {'description': cached.description, 'locations': cached.locations, 'date_posted': cached.date_posted}

    recent_failure = get_cached_failure(url)
    if recent_failure:
        raise InstagramExtractionError(recent_failure.failure_reason)

    try:
        analyzer = InstagramReelAnalyzer(google_api_key, ytdlp_cookies_file)
        result = analyzer.analyze_reel(url)
    except InstagramExtractionError as e:
        store_analysis(url, status=InstagramReelCache.STATUS_FAILED, failure_reason=e.reason)
        raise

    locations = result.get('locations') or []
    date_posted = parse_instagram_date(result.get('date_posted'))
    store_analysis(
        url,
        description=result.get('description', ''),
        locations=locations,
        date_posted=date_posted,
        status=InstagramReelCache.STATUS_ANALYZED if locations else InstagramReelCache.STATUS_NO_LOCATIONS,
        failure_reason='',
    )
    return {'description': result.get('description'), 'locations': locations, 'date_posted': date_posted}
