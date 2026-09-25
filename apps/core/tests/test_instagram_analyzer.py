from unittest.mock import MagicMock, patch

import yt_dlp
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.instagram.analyzer import (
    InstagramExtractionError,
    InstagramReelDescriptionExtractor,
    LocationExtractor,
)


def mock_youtube_dl(mock_ydl_cls, info=None, side_effect=None):
    """`with yt_dlp.YoutubeDL(opts) as ydl: ydl.extract_info(...)` - wire the mock context manager."""
    mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
    if side_effect is not None:
        mock_ydl.extract_info.side_effect = side_effect
    else:
        mock_ydl.extract_info.return_value = info
    return mock_ydl


class DescriptionExtractorTests(TestCase):
    """
    Verified live against real public reel URLs during development: yt-dlp
    reads the caption for most public reels anonymously, and fails cleanly
    (DownloadError) for the rest (private/deleted/rate-limited) rather than
    silently returning garbage - these tests pin both outcomes.
    """

    def setUp(self):
        self.extractor = InstagramReelDescriptionExtractor()

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_extract_description_returns_caption_and_metadata(self, mock_ydl_cls):
        mock_youtube_dl(mock_ydl_cls, info={
            'description': 'Amazing sunset at Golden Gate Bridge!',
            'upload_date': '20250101',
            'like_count': 120,
            'comment_count': 4,
            'uploader': 'travelbot',
        })

        result = self.extractor.extract_description('https://www.instagram.com/reel/abc123/')

        self.assertEqual(result['description'], 'Amazing sunset at Golden Gate Bridge!')
        self.assertEqual(result['date_posted'], '20250101')
        self.assertEqual(result['likes'], 120)
        self.assertEqual(result['comments'], 4)

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_raises_when_caption_is_empty(self, mock_ydl_cls):
        mock_youtube_dl(mock_ydl_cls, info={'description': ''})
        with self.assertRaises(InstagramExtractionError):
            self.extractor.extract_description('https://www.instagram.com/reel/abc123/')

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_raises_on_download_error(self, mock_ydl_cls):
        mock_youtube_dl(
            mock_ydl_cls,
            side_effect=yt_dlp.utils.DownloadError('Instagram sent an empty media response'),
        )
        with self.assertRaises(InstagramExtractionError):
            self.extractor.extract_description('https://www.instagram.com/reel/abc123/')

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_passes_cookies_file_through_to_ytdlp(self, mock_ydl_cls):
        mock_youtube_dl(mock_ydl_cls, info={'description': 'text'})
        extractor = InstagramReelDescriptionExtractor(cookies_file='/tmp/cookies.txt')

        extractor.extract_description('https://www.instagram.com/reel/abc123/')

        opts = mock_ydl_cls.call_args[0][0]
        self.assertEqual(opts['cookiefile'], '/tmp/cookies.txt')

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_does_not_download_video_by_default(self, mock_ydl_cls):
        mock_youtube_dl(mock_ydl_cls, info={'description': 'text'})
        self.extractor.extract_description('https://www.instagram.com/reel/abc123/')
        opts = mock_ydl_cls.call_args[0][0]
        self.assertTrue(opts['skip_download'])


class LocationExtractorTests(TestCase):
    @patch('apps.core.instagram.analyzer.genai.Client')
    def test_extract_locations_parses_json_response(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = MagicMock(
            text='[{"name": "Eiffel Tower", "type": "landmark", "category": "monument", "coordinates": null}]'
        )
        extractor = LocationExtractor(api_key='fake-key')
        locations = extractor.extract_locations('A trip to the Eiffel Tower.')

        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0]['name'], 'Eiffel Tower')
        # Confirms we're on the current model, not the retired gemini-1.5-pro.
        _, kwargs = mock_client.models.generate_content.call_args
        self.assertEqual(kwargs['model'], 'gemini-2.5-flash')

    @patch('apps.core.instagram.analyzer.genai.Client')
    def test_extract_locations_returns_empty_list_on_bad_json(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = MagicMock(text='not json')
        extractor = LocationExtractor(api_key='fake-key')
        self.assertEqual(extractor.extract_locations('some text'), [])

    @patch('apps.core.instagram.analyzer.genai.Client')
    def test_extract_locations_returns_empty_list_on_api_error(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = Exception('quota exceeded')
        extractor = LocationExtractor(api_key='fake-key')
        self.assertEqual(extractor.extract_locations('some text'), [])

    @patch('apps.core.instagram.analyzer.genai.Client')
    def test_empty_api_key_does_not_crash_client_construction(self, mock_client_cls):
        # genai.Client(api_key='') raises ValueError in the real SDK - GOOGLE_API_KEY
        # is documented as optional, so this must degrade gracefully, not 500.
        extractor = LocationExtractor(api_key='')
        self.assertEqual(extractor.extract_locations('A trip to the Eiffel Tower.'), [])
        mock_client_cls.assert_not_called()


class AnalyzeReelViewTests(TestCase):
    """Verifies the API contract the mobile app's share-to-save flow depends on:
    a reel whose caption can't be read comes back as a normal 200 'manual_required'
    response, not an error the client has to special-case."""

    def setUp(self):
        self.user = User.objects.create_user(username='vtester', password='TestPass123!', email='v@example.com')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_extraction_failure_returns_manual_required(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.side_effect = InstagramExtractionError('blocked')
        response = self.client.post('/api/v1/analyze-reel/', {'url': 'https://www.instagram.com/reel/abc123/'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'manual_required')
        self.assertEqual(response.data['url'], 'https://www.instagram.com/reel/abc123/')

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_no_locations_found_returns_manual_required(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {'description': 'just a sunset', 'locations': []}
        response = self.client.post('/api/v1/analyze-reel/', {'url': 'https://www.instagram.com/reel/abc123/'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'manual_required')

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_successful_extraction_returns_locations(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {
            'description': 'A trip to the Eiffel Tower.',
            'date_posted': None,
            'locations': [{'name': 'Eiffel Tower', 'type': 'landmark', 'category': 'monument', 'coordinates': None}],
        }
        response = self.client.post('/api/v1/analyze-reel/', {'url': 'https://www.instagram.com/reel/abc123/'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'new')
        self.assertEqual(len(response.data['locations']), 1)

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_second_request_for_same_url_uses_the_cache(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {
            'description': 'A trip to the Eiffel Tower.',
            'date_posted': None,
            'locations': [{'name': 'Eiffel Tower', 'type': 'landmark', 'category': 'monument', 'coordinates': None}],
        }
        url = 'https://www.instagram.com/reel/abc123/'

        first = self.client.post('/api/v1/analyze-reel/', {'url': url}, format='json')
        second = self.client.post('/api/v1/analyze-reel/', {'url': url}, format='json')

        self.assertEqual(first.data['status'], 'new')
        self.assertEqual(second.data['status'], 'new')
        self.assertEqual(second.data['locations'], first.data['locations'])
        # The whole point of the cache: yt-dlp + Gemini only ran once.
        mock_analyzer_cls.return_value.analyze_reel.assert_called_once()
