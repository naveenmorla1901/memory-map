# apps/core/instagram/analyzer.py
import json
import logging
from typing import Dict, List, Optional

import yt_dlp
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class InstagramExtractionError(Exception):
    """
    Raised when we couldn't get a reel's caption text at all. This is an
    expected, non-bug outcome (a private/deleted reel, or Instagram
    rate-limiting/blocking the request), so callers should treat it as
    "fall back to manual entry", not a 500.
    """
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class InstagramReelAnalyzer:
    def __init__(self, google_api_key: str, ytdlp_cookies_file: Optional[str] = None):
        """Initialize with a Gemini API key and an optional yt-dlp cookies file."""
        self.description_extractor = InstagramReelDescriptionExtractor(ytdlp_cookies_file)
        self.location_extractor = LocationExtractor(google_api_key)

    def analyze_reel(self, url: str) -> Dict:
        """
        Analyze an Instagram reel: fetch its caption, then extract locations
        from it. Raises InstagramExtractionError if the caption itself
        couldn't be read (nothing to do with the AI model).
        """
        reel_data = self.description_extractor.extract_description(url)
        reel_data['locations'] = self.location_extractor.extract_locations(reel_data['description'])
        return reel_data


class InstagramReelDescriptionExtractor:
    """
    Gets a reel's caption (and, later, its video - see the `download`
    option) via yt-dlp, which is maintained specifically to track
    Instagram's frequently-changing internals. Works anonymously for a
    majority of public reels in practice; for the rest (and for better
    reliability generally), point `ytdlp_cookies_file` at a Netscape-format
    cookies.txt exported from a logged-in Instagram session - see the
    backend README.
    """

    def __init__(self, cookies_file: Optional[str] = None):
        self.cookies_file = cookies_file

    def extract_description(self, url: str, download: bool = False) -> Dict:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': not download,
        }
        if self.cookies_file:
            ydl_opts['cookiefile'] = self.cookies_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as e:
            logger.info(f"yt-dlp could not read {url}: {e}")
            raise InstagramExtractionError(
                "Couldn't read this reel automatically - it may be private, deleted, or "
                "Instagram is blocking the request right now. Add the location manually."
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error reading {url}: {e}", exc_info=True)
            raise InstagramExtractionError(
                "Something went wrong reading this reel. Add the location manually."
            ) from e

        description = (info.get('description') or '').strip()
        if not description:
            raise InstagramExtractionError(
                "This reel doesn't have a caption to read locations from. Add the location manually."
            )

        return {
            'url': url,
            'description': description,
            'date_posted': info.get('upload_date'),  # 'YYYYMMDD' string, or None
            'likes': info.get('like_count'),
            'comments': info.get('comment_count'),
            'uploader': info.get('uploader'),
        }


class LocationExtractor:
    """Extracts structured location data from free text using Gemini."""

    MODEL = 'gemini-2.5-flash'

    PROMPT_TEMPLATE = """
Extract all distinct, specific locations from the following text. Return each unique location as a JSON object with these properties:
- name: The full, unique location name, including any relevant address or context (e.g., "Statue of Hachiko, 2-14-3 Dogenzaka, Shibuya-ku, Tokyo").
- type: The type of location (e.g., "landmark", "city", "road", "region", "park").
- coordinates: If provided in the text, include as {{latitude: float, longitude: float}}. If no coordinates are given, set this as null.
- category: A category based on the text.

Guidelines:
1. **Avoid Redundancy**: Do not repeat locations that are part of a larger location.
2. **Merge Details**: Combine related details (address, neighborhood, city, coordinates) under one entry.
3. **Unique Locations**: Identify only key, distinct locations, excluding general or nested locations.
4. **Explicit Mentions**: Include only explicitly named locations.
5. **Specificity**: Prefer more specific, detailed locations over general areas or cities.
6. **Handle Different Names**: Ensure locations with different names are not duplicated.
7. **Complete Address**: Consider the complete address or context to avoid splitting locations.

Input text:
{text}
"""

    RESPONSE_SCHEMA = {
        'type': 'ARRAY',
        'items': {
            'type': 'OBJECT',
            'properties': {
                'name': {'type': 'STRING'},
                'type': {'type': 'STRING'},
                'category': {'type': 'STRING'},
                'coordinates': {
                    'type': 'OBJECT',
                    'nullable': True,
                    'properties': {
                        'latitude': {'type': 'NUMBER'},
                        'longitude': {'type': 'NUMBER'},
                    },
                },
            },
            'required': ['name', 'type', 'category'],
        },
    }

    def __init__(self, api_key: str):
        # genai.Client raises ValueError on an empty key, and GOOGLE_API_KEY
        # is documented as optional - so a missing key means "always fetch
        # the caption, never extract locations from it", not a crash.
        self.client = genai.Client(api_key=api_key) if api_key else None

    def extract_locations(self, text: str) -> List[Dict]:
        if not self.client:
            logger.info("GOOGLE_API_KEY is not configured - skipping location extraction.")
            return []
        try:
            response = self.client.models.generate_content(
                model=self.MODEL,
                contents=self.PROMPT_TEMPLATE.format(text=text),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type='application/json',
                    response_schema=self.RESPONSE_SCHEMA,
                ),
            )
            return json.loads(response.text) if response.text else []
        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned non-JSON output: {e}")
            return []
        except Exception as e:
            logger.error(f"Gemini location extraction failed: {e}")
            return []
