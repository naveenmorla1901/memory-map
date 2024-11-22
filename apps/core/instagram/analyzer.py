# apps/core/instagram/analyzer.py
import requests
import re
import html
import json
import time
from datetime import datetime
from typing import Optional, Dict, Tuple, List

class InstagramReelAnalyzer:
    def __init__(self, google_api_key: str):
        """Initialize with Google AI API key"""
        self.description_extractor = InstagramReelDescriptionExtractor()
        self.location_extractor = LocationExtractor(google_api_key)

    def analyze_reel(self, url: str) -> Optional[Dict]:
        """Analyze Instagram reel to extract description and locations"""
        # First extract the description
        reel_data = self.description_extractor.extract_description(url)

        if reel_data:
            # Extract locations from the description
            locations = self.location_extractor.extract_locations(reel_data['description'])

            # Add locations to the output
            reel_data['locations'] = locations

            return reel_data
        return None

class InstagramReelDescriptionExtractor:
    def __init__(self):
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

    def _extract_metadata_and_clean(self, text: str) -> Tuple[str, Dict]:
        """Extract metadata and clean text in one pass"""
        metadata = {
            'likes': None,
            'comments': None,
            'date': None
        }

        # Extract metadata
        stats_match = re.match(r'(\d+[KM]?)\s*likes?,\s*(\d+[KM]?)\s*comments?', text)
        if stats_match:
            metadata['likes'] = stats_match.group(1)
            metadata['comments'] = stats_match.group(2)

        date_match = re.search(r'on ([A-Z][a-z]+ \d+, \d{4}):', text)
        if date_match:
            metadata['date'] = date_match.group(1)

        # Remove metadata section and clean text
        if ' - ' in text:
            text = text.split(' - ', 1)[1]
        if ': ' in text:
            text = text.split(': ', 1)[1]

        # Clean text function
        def clean_text(text: str) -> str:
            # Handle Unicode and emojis
            text = text.encode('utf-8').decode('utf-8')
            # Remove Unicode escape sequences
            text = re.sub(r'\\u[0-9a-fA-F]{4}', '', text)
            text = re.sub(r'\ud83d[\ude00-\udfff]', '', text)
            text = re.sub(r'\ud83e[\udd00-\udfff]', '', text)
            text = text.encode('ascii', 'ignore').decode('ascii')

            # Clean HTML entities
            text = html.unescape(text)
            text = text.replace('&quot;', '"').replace('&amp;', '&')

            # Remove URLs and social media elements
            text = re.sub(r'http\S+', '', text)
            text = re.sub(r'@\w+', '', text)
            text = re.sub(r'#\w+', '', text)

            # Clean formatting
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\s*([,.])\s*', r'\1 ', text)
            text = re.sub(r'[^\w\s.,!?()-]', '', text)

            return text.strip()

        # Process text sentence by sentence
        sentences = text.split('.')
        cleaned_sentences = []

        for sentence in sentences:
            cleaned = clean_text(sentence)
            if cleaned and len(cleaned) > 5:  # Filter out very short segments
                # Remove bullets and numbering
                cleaned = re.sub(r'^\s*[\u2022\-*]\s*', '', cleaned)
                cleaned = re.sub(r'^\d+\.\s*', '', cleaned)
                cleaned_sentences.append(cleaned.strip())

        # Create final text
        final_text = '. '.join(s for s in cleaned_sentences if s)
        if final_text and not final_text.endswith('.'):
            final_text += '.'

        return final_text, metadata

    def extract_description(self, url: str) -> Optional[Dict]:
        """Extract and process Instagram reel description"""
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                meta_desc = re.search(r'<meta property="og:description" content="([^"]+)"', response.text)
                if meta_desc:
                    raw_description = meta_desc.group(1)
                    cleaned_text, metadata = self._extract_metadata_and_clean(raw_description)

                    return {
                        'url': url,
                        'likes': metadata['likes'],
                        'comments': metadata['comments'],
                        'date_posted': metadata['date'],
                        'date_extracted': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'description': cleaned_text
                    }
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

class LocationExtractor:
    def __init__(self, api_key: str):
        """Initialize with Google AI API key"""
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"

        self.prompt_template = """
Extract all distinct, specific locations from the following text. Return each unique location as a JSON object with these properties:
- name: The full, unique location name, including any relevant address or context (e.g., "Statue of Hachiko, 2-14-3 Dogenzaka, Shibuya-ku, Tokyo").
- type: The type of location (e.g., "landmark", "city", "road", "region", "park").
- coordinates: If provided in the text, include as {latitude: float, longitude: float}. If no coordinates are given, set this as null.
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

    def extract_locations(self, text: str) -> List[Dict]:
        """Extract locations using Google AI API"""
        url = f"{self.base_url}?key={self.api_key}"

        payload = {
            "contents": [{
                "parts": [{
                    "text": f"{self.prompt_template}\n\nText to analyze: {text}"
                }]
            }],
            "generationConfig": {
                "temperature": 0.0,
                "topP": 1,
                "topK": 1,
                "maxOutputTokens": 1024
            }
        }

        response = requests.post(url, json=payload)

        if response.status_code == 200:
            response_data = response.json()
            if 'candidates' in response_data and response_data['candidates']:
                generated_text = response_data['candidates'][0]['content']['parts'][0]['text']
                try:
                    start_idx = generated_text.find('[')
                    end_idx = generated_text.rfind(']') + 1
                    if start_idx != -1 and end_idx != -1:
                        json_str = generated_text[start_idx:end_idx]
                        return json.loads(json_str)
                except json.JSONDecodeError:
                    return []
        return []