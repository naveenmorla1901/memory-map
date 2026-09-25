# apps/core/instagram/analyzer.py
import html
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class InstagramExtractionError(Exception):
    """
    Raised when we couldn't get a reel's caption text at all. This is an
    expected, non-bug outcome (Instagram blocks unauthenticated scraping),
    so callers should treat it as "fall back to manual entry", not a 500.
    """
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class InstagramReelAnalyzer:
    def __init__(self, google_api_key: str, oembed_access_token: Optional[str] = None):
        """Initialize with a Gemini API key and an optional Meta oEmbed access token."""
        self.description_extractor = InstagramReelDescriptionExtractor(oembed_access_token)
        self.location_extractor = LocationExtractor(google_api_key)

    def analyze_reel(self, url: str) -> Optional[Dict]:
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
    Gets the caption text off an Instagram reel URL. Instagram serves a
    login wall to unauthenticated/non-browser requests, so a raw HTML
    scrape mostly doesn't work anymore - it's kept as a zero-config,
    best-effort attempt. The reliable path is Meta's oEmbed API, which
    needs a Meta developer app that has been through App Review for the
    "oEmbed Read" permission (see README). Without that token configured,
    this will usually raise InstagramExtractionError, which is expected -
    the app is meant to fall back to letting the user pick the location
    manually.
    """

    OEMBED_URL = 'https://graph.facebook.com/v21.0/instagram_oembed'

    def __init__(self, oembed_access_token: Optional[str] = None):
        self.oembed_access_token = oembed_access_token
        self.session = requests.Session()
        self.session.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'X-IG-App-ID': '936619743392459',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://www.instagram.com',
            'Connection': 'keep-alive',
            'Referer': 'https://www.instagram.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }

    def extract_description(self, url: str) -> Dict:
        if self.oembed_access_token:
            reel_data = self._extract_via_oembed(url)
            if reel_data:
                return reel_data

        reel_data = self._extract_via_scrape(url)
        if reel_data:
            return reel_data

        raise InstagramExtractionError(
            "Couldn't read this reel's caption automatically - Instagram blocks "
            "unauthenticated requests. Add the location manually, or configure "
            "INSTAGRAM_OEMBED_ACCESS_TOKEN for reliable extraction."
        )

    def _extract_via_oembed(self, url: str) -> Optional[Dict]:
        """
        Best-effort: Meta's oEmbed API returns an embed <blockquote> whose
        fallback HTML includes the caption text. This path needs real Meta
        App Review credentials to work at all, so it can't be exercised in
        development without them - it's written defensively (any unexpected
        response shape just falls through to the scrape/manual-entry path
        rather than raising).
        """
        try:
            response = self.session.get(
                self.OEMBED_URL,
                params={'url': url, 'access_token': self.oembed_access_token},
                timeout=10,
            )
            if response.status_code != 200:
                logger.info(f"oEmbed request failed with status {response.status_code}: {response.text[:200]}")
                return None

            embed_html = response.json().get('html', '')
            caption = re.sub(r'<[^>]+>', ' ', embed_html)
            caption = html.unescape(caption)
            caption = re.sub(r'\s+', ' ', caption).strip()
            if not caption:
                return None

            cleaned_text, metadata = self._clean_caption(caption)
            return {
                'url': url,
                'likes': metadata['likes'],
                'comments': metadata['comments'],
                'date_posted': metadata['date'],
                'date_extracted': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'description': cleaned_text or caption,
            }
        except Exception as e:
            logger.warning(f"oEmbed extraction failed: {e}")
            return None

    def _extract_via_scrape(self, url: str) -> Optional[Dict]:
        try:
            response = self.session.get(url, timeout=10)
        except Exception as e:
            logger.warning(f"Instagram scrape request failed: {e}")
            return None

        if response.status_code != 200:
            return None

        meta_desc = re.search(r'<meta property="og:description" content="([^"]+)"', response.text)
        if not meta_desc:
            # This is the common case now: Instagram served its generic
            # login-wall page instead of the post, which has no og:description.
            return None

        cleaned_text, metadata = self._clean_caption(meta_desc.group(1))
        return {
            'url': url,
            'likes': metadata['likes'],
            'comments': metadata['comments'],
            'date_posted': metadata['date'],
            'date_extracted': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': cleaned_text,
        }

    def _clean_caption(self, text: str) -> Tuple[str, Dict]:
        """Strip the "N likes, M comments - username on <date>: " prefix Instagram's
        og:description used to include, and normalize the remaining caption text."""
        metadata = {'likes': None, 'comments': None, 'date': None}

        stats_match = re.match(r'(\d+[KM]?)\s*likes?,\s*(\d+[KM]?)\s*comments?', text)
        if stats_match:
            metadata['likes'] = stats_match.group(1)
            metadata['comments'] = stats_match.group(2)

        date_match = re.search(r'on ([A-Z][a-z]+ \d+, \d{4}):', text)
        if date_match:
            metadata['date'] = date_match.group(1)

        if ' - ' in text:
            text = text.split(' - ', 1)[1]
        if ': ' in text:
            text = text.split(': ', 1)[1]

        def clean_text(segment: str) -> str:
            segment = re.sub(r'\\u[0-9a-fA-F]{4}', '', segment)
            segment = re.sub(r'\ud83d[\ude00-\udfff]', '', segment)
            segment = re.sub(r'\ud83e[\udd00-\udfff]', '', segment)
            segment = segment.encode('ascii', 'ignore').decode('ascii')
            segment = html.unescape(segment)
            segment = segment.replace('&quot;', '"').replace('&amp;', '&')
            segment = re.sub(r'http\S+', '', segment)
            segment = re.sub(r'@\w+', '', segment)
            segment = re.sub(r'#\w+', '', segment)
            segment = re.sub(r'\s+', ' ', segment)
            segment = re.sub(r'\s*([,.])\s*', r'\1 ', segment)
            segment = re.sub(r'[^\w\s.,!?()-]', '', segment)
            return segment.strip()

        cleaned_sentences = []
        for sentence in text.split('.'):
            cleaned = clean_text(sentence)
            if cleaned and len(cleaned) > 5:
                cleaned = re.sub(r'^\s*[•\-*]\s*', '', cleaned)
                cleaned = re.sub(r'^\d+\.\s*', '', cleaned)
                cleaned_sentences.append(cleaned.strip())

        final_text = '. '.join(s for s in cleaned_sentences if s)
        if final_text and not final_text.endswith('.'):
            final_text += '.'

        return final_text, metadata


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
        self.client = genai.Client(api_key=api_key)

    def extract_locations(self, text: str) -> List[Dict]:
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
