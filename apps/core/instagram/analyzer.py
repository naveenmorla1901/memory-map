import json
import logging
from typing import Dict, List, Optional

import yt_dlp
from google import genai
from google.genai import types

from ..categories import CATEGORIES, CATEGORY_KEYS, normalize_category

logger = logging.getLogger(__name__)


class InstagramExtractionError(Exception):
    """
    The reel's caption couldn't be read at all (private/deleted reel, or
    Instagram rate-limiting the request). Expected, not a bug: callers
    should fall back to letting the user pick the place manually.
    """
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ReelCaptionFetcher:
    """
    Fetches a reel's caption and metadata via yt-dlp, which is maintained
    specifically to track Instagram's frequently-changing internals. Works
    anonymously for most public reels; `cookies_file` (a Netscape
    cookies.txt from a logged-in session) makes it far more reliable.

    `download=True` also fetches the video itself - the hook for extracting
    places from a reel's audio/visuals later, not used yet.
    """

    def __init__(self, cookies_file: Optional[str] = None):
        self.cookies_file = cookies_file

    def fetch(self, url: str, download: bool = False) -> Dict:
        options = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': not download,
            'socket_timeout': 15,
        }
        if self.cookies_file:
            options['cookiefile'] = self.cookies_file

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as e:
            logger.info('yt-dlp could not read %s: %s', url, e)
            raise InstagramExtractionError(
                "Couldn't read this reel - it may be private or deleted, or Instagram "
                "is limiting requests right now."
            ) from e
        except Exception as e:
            logger.exception('Unexpected error reading %s', url)
            raise InstagramExtractionError("Something went wrong reading this reel.") from e

        caption = (info.get('description') or '').strip()
        if not caption:
            raise InstagramExtractionError("This reel has no caption to find places in.")

        return {
            'url': url,
            'caption': caption,
            'date_posted': info.get('upload_date'),  # 'YYYYMMDD' or None
            'uploader': info.get('uploader') or info.get('channel') or '',
        }


class PlaceExtractor:
    """Pulls the specific, visitable places a caption mentions, via Gemini."""

    SYSTEM_INSTRUCTION = (
        "You extract real-world places from Instagram reel captions for a travel app that "
        "lets people save places they want to visit. Precision matters more than recall: "
        "a wrong place on someone's map is worse than a missing one."
    )

    PROMPT_TEMPLATE = """Find every specific, physically visitable place this caption names.

Rules:
- Include a place only if the caption names it explicitly, in the text or a hashtag (e.g. #bluebottlecoffee). Never guess a place from a vague description.
- Skip general regions or cities when a more specific place in them is named (for "the best tacos in Mexico City at El Huequito", return El Huequito, not Mexico City). Only return a city/region on its own if it is the only place named.
- Skip businesses that are not places (brands, apps, airlines, the creator's own account).
- Merge repeated mentions of one place into one entry.
- For each place give the city and country when the caption or the place's well-known identity makes them clear - they are used to find the place on a map. Leave them empty rather than guessing.
- confidence: 0.9+ when the caption plainly names a specific place, 0.5-0.8 when the name is partial or ambiguous, below 0.5 when unsure. Leave out anything below 0.3.
- category: the best fit from this list:
{categories}

Posted by: {uploader}

Caption:
\"\"\"
{caption}
\"\"\"
"""

    RESPONSE_SCHEMA = {
        'type': 'ARRAY',
        'items': {
            'type': 'OBJECT',
            'properties': {
                'name': {'type': 'STRING', 'description': 'The place name as people would search for it'},
                'category': {'type': 'STRING', 'enum': CATEGORY_KEYS},
                'address': {'type': 'STRING', 'description': 'Street address if given, else empty'},
                'city': {'type': 'STRING'},
                'country': {'type': 'STRING'},
                'confidence': {'type': 'NUMBER'},
            },
            'required': ['name', 'category', 'confidence'],
            'propertyOrdering': ['name', 'category', 'address', 'city', 'country', 'confidence'],
        },
    }

    def __init__(self, api_key: str, model: str):
        # genai.Client raises on an empty key; the key is optional, so a
        # missing one means "never extract", not a crash.
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model = model

    @classmethod
    def build_prompt(cls, caption: str, uploader: str = '') -> str:
        categories = '\n'.join(f'  - {key}: {description}' for key, _, description in CATEGORIES)
        # Captions are untrusted user content; cap the size we send.
        return cls.PROMPT_TEMPLATE.format(
            categories=categories, uploader=uploader or 'unknown', caption=caption[:5000]
        )

    def extract(self, caption: str, uploader: str = '') -> List[Dict]:
        if not self.client:
            logger.info('GOOGLE_API_KEY is not configured - skipping place extraction.')
            return []
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=self.build_prompt(caption, uploader),
                config=types.GenerateContentConfig(
                    system_instruction=self.SYSTEM_INSTRUCTION,
                    temperature=0.0,
                    response_mime_type='application/json',
                    response_schema=self.RESPONSE_SCHEMA,
                ),
            )
            raw = json.loads(response.text) if response.text else []
        except json.JSONDecodeError as e:
            logger.error('Gemini returned non-JSON output: %s', e)
            return []
        except Exception as e:
            logger.error('Gemini place extraction failed: %s', e)
            return []
        return self._clean(raw)

    @staticmethod
    def _clean(raw) -> List[Dict]:
        places, seen = [], set()
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get('name') or '').strip()
            try:
                confidence = max(0.0, min(1.0, float(item.get('confidence', 0))))
            except (TypeError, ValueError):
                confidence = 0.0
            if not name or confidence < 0.3 or name.lower() in seen:
                continue
            seen.add(name.lower())
            places.append({
                'name': name[:255],
                'category': normalize_category(item.get('category')),
                'address': str(item.get('address') or '').strip(),
                'city': str(item.get('city') or '').strip(),
                'country': str(item.get('country') or '').strip(),
                'confidence': round(confidence, 2),
            })
        return places
