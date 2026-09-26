"""
Turns a shared Instagram reel link into a list of places, with caching.

Pipeline: canonicalize URL -> cache lookup -> fetch caption (yt-dlp) ->
extract places (Gemini) -> geocode each (Photon) -> cache. A reel shared by
many people is only ever processed once per cache window.
"""
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from ..instagram.analyzer import InstagramExtractionError, PlaceExtractor, ReelCaptionFetcher
from ..models import InstagramReelCache, SavedLocation
from . import geocoding

logger = logging.getLogger(__name__)

_SHORTCODE_PATTERN = re.compile(r'^/(?:[\w.]+/)?(reel|reels|p|tv)/([A-Za-z0-9_-]+)')


def canonicalize_reel_url(url: str) -> str:
    """
    https://www.instagram.com/reel/ABC/?igsh=xyz and instagram.com/reels/ABC
    are the same reel - map them to one cache key. Unrecognized paths are
    returned unchanged (minus the query string).
    """
    parsed = urlparse(url.strip())
    match = _SHORTCODE_PATTERN.match(parsed.path)
    if not match:
        return f'https://www.instagram.com{parsed.path}'
    kind, shortcode = match.groups()
    kind = 'reel' if kind == 'reels' else kind
    return f'https://www.instagram.com/{kind}/{shortcode}/'


def _parse_upload_date(value: Optional[str]):
    if not value:
        return None
    try:
        return timezone.make_aware(datetime.strptime(value, '%Y%m%d'))
    except (TypeError, ValueError):
        return None


def _geocode_place(place: dict) -> dict:
    query = ', '.join(filter(None, [place['name'], place.get('city'), place.get('country')]))
    try:
        results = geocoding.search(query, limit=1)
    except geocoding.GeocodingError:
        results = []
    match = results[0] if results else None
    return {
        'name': place['name'],
        'category': place['category'],
        'address': (match or {}).get('address') or ', '.join(
            filter(None, [place.get('address'), place.get('city'), place.get('country')])
        ),
        'latitude': match['latitude'] if match else None,
        'longitude': match['longitude'] if match else None,
        'confidence': place['confidence'],
    }


def _run_pipeline(url: str) -> dict:
    fetched = ReelCaptionFetcher(settings.INSTAGRAM_YTDLP_COOKIES_FILE or None).fetch(url)
    extracted = PlaceExtractor(settings.GOOGLE_API_KEY, settings.GEMINI_MODEL).extract(
        fetched['caption'], fetched['uploader']
    )
    return {
        'caption': fetched['caption'],
        'date_posted': _parse_upload_date(fetched['date_posted']),
        'places': [_geocode_place(place) for place in extracted],
    }


def get_reel_places(url: str) -> dict:
    """
    {'caption', 'places'} for a reel, from cache when fresh. Raises
    InstagramExtractionError if the caption can't be read (also cached,
    briefly, so a broken link isn't retried on every share).
    """
    canonical = canonicalize_reel_url(url)
    entry = InstagramReelCache.objects.filter(url=canonical).first()

    if entry and not entry.is_stale():
        if entry.status == InstagramReelCache.STATUS_FAILED:
            raise InstagramExtractionError(entry.failure_reason)
        return {'caption': entry.description, 'places': entry.locations}

    try:
        result = _run_pipeline(canonical)
    except InstagramExtractionError as e:
        InstagramReelCache.objects.update_or_create(
            url=canonical,
            defaults={'status': InstagramReelCache.STATUS_FAILED, 'failure_reason': e.reason,
                      'description': '', 'locations': []},
        )
        raise

    InstagramReelCache.objects.update_or_create(
        url=canonical,
        defaults={
            'status': InstagramReelCache.STATUS_ANALYZED if result['places'] else InstagramReelCache.STATUS_NO_LOCATIONS,
            'description': result['caption'],
            'locations': result['places'],
            'date_posted': result['date_posted'],
            'failure_reason': '',
        },
    )
    return {'caption': result['caption'], 'places': result['places']}


def analyze_reel_for_user(url: str, user) -> dict:
    """The API response for one user: places plus whether they've already saved each."""
    canonical = canonicalize_reel_url(url)

    if not settings.REEL_ANALYSIS_ENABLED:
        return {'status': 'manual_required', 'url': canonical,
                'reason': 'Automatic place detection is turned off. Search for the place instead.'}

    try:
        result = get_reel_places(canonical)
    except InstagramExtractionError as e:
        return {'status': 'manual_required', 'url': canonical, 'reason': e.reason}

    if not result['places']:
        return {'status': 'manual_required', 'url': canonical, 'caption': result['caption'],
                'reason': "We read the caption but couldn't spot a specific place in it."}

    places = [{**place, 'already_saved': is_saved} for place, is_saved in zip(result['places'], _already_saved(user, canonical, result['places']))]
    return {'status': 'found', 'url': canonical, 'caption': result['caption'], 'places': places}


# About 300m: the same name this close is the same place, whichever reel it came from.
SAME_PLACE_DEGREES = 0.003


def _already_saved(user, reel_url: str, places: list) -> list:
    """
    Whether the user already has each place: saved from this reel, or saved
    any other way under the same name at (nearly) the same spot - so sharing
    a second reel about a place doesn't create a duplicate.
    """
    names = Q()
    for place in places:
        names |= Q(name__iexact=place['name'])
    saved = list(
        SavedLocation.objects.filter(names, user=user).values_list('name', 'latitude', 'longitude', 'instagram_url')
    ) if places else []

    def matches(place):
        for name, latitude, longitude, url in saved:
            if name.lower() != place['name'].lower():
                continue
            if url == reel_url:
                return True
            if place['latitude'] is not None and (
                abs(latitude - place['latitude']) < SAME_PLACE_DEGREES
                and abs(longitude - place['longitude']) < SAME_PLACE_DEGREES
            ):
                return True
        return False

    return [matches(place) for place in places]
