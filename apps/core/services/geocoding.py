"""
Server-side geocoding via a Photon API (https://github.com/komoot/photon).

The app never calls a public geocoder directly: routing through here lets us
cache results, rate-limit per user, send one identifying User-Agent, and
swap providers (GEOCODER_BASE_URL) without an app release.
"""
import hashlib
import logging
from typing import List, Optional

import requests
from django.conf import settings
from django.core.cache import cache

from ..categories import category_for_osm_tag

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 8


class GeocodingError(Exception):
    pass


def _cache_key(prefix: str, *parts) -> str:
    raw = '|'.join(str(p) for p in parts)
    return f'geocode:{prefix}:{hashlib.sha256(raw.encode()).hexdigest()}'


def _format_address(props: dict) -> str:
    street = ' '.join(filter(None, [props.get('housenumber'), props.get('street')]))
    parts = [street, props.get('district') or props.get('locality'), props.get('city'),
             props.get('state'), props.get('country')]
    seen, cleaned = set(), []
    for part in parts:
        if part and part not in seen and part != props.get('name'):
            seen.add(part)
            cleaned.append(part)
    return ', '.join(cleaned)


def _feature_to_result(feature: dict) -> Optional[dict]:
    props = feature.get('properties') or {}
    coordinates = (feature.get('geometry') or {}).get('coordinates') or []
    if len(coordinates) != 2:
        return None
    longitude, latitude = coordinates
    address = _format_address(props)
    # Unnamed results (a plain street address) use the address's first part.
    name = props.get('name') or (address.split(',')[0].strip() if address else '')
    if not name:
        return None
    return {
        'id': f"{props.get('osm_type', '')}{props.get('osm_id', '')}" or f'{latitude},{longitude}',
        'name': name,
        'address': address,
        'latitude': latitude,
        'longitude': longitude,
        'category': category_for_osm_tag(props.get('osm_key'), props.get('osm_value'), name),
    }


def _get(path: str, params: dict) -> List[dict]:
    try:
        response = requests.get(
            f'{settings.GEOCODER_BASE_URL}{path}',
            params=params,
            headers={'User-Agent': settings.GEOCODER_USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        features = response.json().get('features', [])
    except (requests.RequestException, ValueError) as e:
        logger.warning('Geocoder request to %s failed: %s', path, e)
        raise GeocodingError('The place search service is unavailable right now.') from e
    return _dedupe([result for result in map(_feature_to_result, features) if result])


def _dedupe(results: List[dict]) -> List[dict]:
    """
    OSM often splits one place into several features (each road segment of
    a bridge, say). Drop a result with the same name as an earlier one if it
    has the same address or is within ~500m. Branches of a chain have their
    own street addresses, so they're kept.
    """
    def same_place(a, b):
        if a['name'].lower() != b['name'].lower():
            return False
        return a['address'] == b['address'] or (
            abs(a['latitude'] - b['latitude']) < 0.005 and abs(a['longitude'] - b['longitude']) < 0.005
        )

    kept = []
    for result in results:
        if not any(same_place(result, other) for other in kept):
            kept.append(result)
    return kept


def search(query: str, *, near: Optional[tuple] = None, limit: int = 6) -> List[dict]:
    """Forward search. `near` (lat, lon) biases results toward the user."""
    query = ' '.join(query.split())[:200]
    if len(query) < 2:
        return []
    params = {'q': query, 'limit': limit, 'lang': 'en'}
    if near:
        # Round the bias point so nearby users share cache entries.
        params['lat'], params['lon'] = round(near[0], 2), round(near[1], 2)

    key = _cache_key('search', query.lower(), limit, params.get('lat'), params.get('lon'))
    cached = cache.get(key)
    if cached is not None:
        return cached
    results = _get('/api/', params)
    cache.set(key, results, settings.GEOCODER_CACHE_SECONDS)
    return results


def reverse(latitude: float, longitude: float) -> Optional[dict]:
    """The nearest named place/address to a point, or None."""
    lat, lon = round(latitude, 5), round(longitude, 5)
    key = _cache_key('reverse', lat, lon)
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    results = _get('/reverse', {'lat': lat, 'lon': lon, 'limit': 1, 'lang': 'en'})
    result = results[0] if results else None
    if result:
        # Keep the exact tapped point - the nearest address can be meters away.
        result = {**result, 'latitude': latitude, 'longitude': longitude}
    cache.set(key, result or {}, settings.GEOCODER_CACHE_SECONDS)
    return result
