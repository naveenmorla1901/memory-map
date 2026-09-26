from datetime import timedelta
from unittest.mock import MagicMock, patch

import yt_dlp
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.instagram.analyzer import InstagramExtractionError, PlaceExtractor, ReelCaptionFetcher
from apps.core.models import InstagramReelCache, SavedLocation
from apps.core.services.reels import canonicalize_reel_url, get_reel_places

User = get_user_model()
URL = 'https://www.instagram.com/reel/ABC123/'


def ytdlp_returning(mock_cls, info=None, error=None):
    ydl = mock_cls.return_value.__enter__.return_value
    if error:
        ydl.extract_info.side_effect = error
    else:
        ydl.extract_info.return_value = info
    return ydl


class CanonicalizeTests(TestCase):
    def test_variants_map_to_one_url(self):
        for variant in (
            'https://www.instagram.com/reel/ABC123/',
            'https://instagram.com/reel/ABC123',
            'https://www.instagram.com/reels/ABC123/?igsh=xyz&utm_source=ig',
            'https://www.instagram.com/some.creator/reel/ABC123/',
        ):
            self.assertEqual(canonicalize_reel_url(variant), URL, variant)

    def test_posts_keep_their_kind(self):
        self.assertEqual(canonicalize_reel_url('https://instagram.com/p/XyZ/?img_index=1'),
                         'https://www.instagram.com/p/XyZ/')


class ReelCaptionFetcherTests(TestCase):
    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_returns_caption_and_metadata(self, mock_cls):
        ytdlp_returning(mock_cls, {'description': 'Tacos at El Huequito #cdmx', 'upload_date': '20250101', 'uploader': 'foodie'})
        result = ReelCaptionFetcher().fetch(URL)
        self.assertEqual(result['caption'], 'Tacos at El Huequito #cdmx')
        self.assertEqual(result['uploader'], 'foodie')
        options = mock_cls.call_args[0][0]
        self.assertTrue(options['skip_download'])
        self.assertNotIn('cookiefile', options)

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_passes_cookies(self, mock_cls):
        ytdlp_returning(mock_cls, {'description': 'x'})
        ReelCaptionFetcher('/secrets/cookies.txt').fetch(URL)
        self.assertEqual(mock_cls.call_args[0][0]['cookiefile'], '/secrets/cookies.txt')

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_download_error_becomes_extraction_error(self, mock_cls):
        ytdlp_returning(mock_cls, error=yt_dlp.utils.DownloadError('empty media response'))
        with self.assertRaises(InstagramExtractionError):
            ReelCaptionFetcher().fetch(URL)

    @patch('apps.core.instagram.analyzer.yt_dlp.YoutubeDL')
    def test_empty_caption_is_an_extraction_error(self, mock_cls):
        ytdlp_returning(mock_cls, {'description': '   '})
        with self.assertRaises(InstagramExtractionError):
            ReelCaptionFetcher().fetch(URL)


class PlaceExtractorTests(TestCase):
    def test_prompt_contains_caption_categories_and_uploader(self):
        prompt = PlaceExtractor.build_prompt('Sunset at {weird} braces', 'someone')
        self.assertIn('Sunset at {weird} braces', prompt)
        self.assertIn('viewpoint:', prompt)
        self.assertIn('Posted by: someone', prompt)

    @patch('apps.core.instagram.analyzer.genai.Client')
    def test_parses_filters_and_normalizes(self, mock_client_cls):
        mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text='''[
            {"name": "El Huequito", "category": "food", "city": "Mexico City", "country": "Mexico", "confidence": 0.95},
            {"name": "el huequito", "category": "food", "confidence": 0.9},
            {"name": "Somewhere vague", "category": "other", "confidence": 0.1},
            {"name": "Museo Frida", "category": "not-a-category", "confidence": 1.7}
        ]''')
        places = PlaceExtractor('key', 'gemini-2.5-flash').extract('caption')
        self.assertEqual([p['name'] for p in places], ['El Huequito', 'Museo Frida'])
        self.assertEqual(places[1]['category'], 'other')
        self.assertEqual(places[1]['confidence'], 1.0)
        _, kwargs = mock_client_cls.return_value.models.generate_content.call_args
        self.assertEqual(kwargs['model'], 'gemini-2.5-flash')

    @patch('apps.core.instagram.analyzer.genai.Client')
    def test_bad_json_and_api_errors_return_nothing(self, mock_client_cls):
        generate = mock_client_cls.return_value.models.generate_content
        generate.return_value = MagicMock(text='not json')
        self.assertEqual(PlaceExtractor('key', 'm').extract('caption'), [])
        generate.side_effect = Exception('quota exceeded')
        self.assertEqual(PlaceExtractor('key', 'm').extract('caption'), [])

    @patch('apps.core.instagram.analyzer.genai.Client')
    def test_missing_api_key_skips_extraction_without_crashing(self, mock_client_cls):
        self.assertEqual(PlaceExtractor('', 'm').extract('caption'), [])
        mock_client_cls.assert_not_called()


FETCHED = {'url': URL, 'caption': 'Tacos at El Huequito', 'date_posted': '20250101', 'uploader': 'foodie'}
EXTRACTED = [{'name': 'El Huequito', 'category': 'food', 'address': '', 'city': 'Mexico City', 'country': 'Mexico', 'confidence': 0.95}]
GEOCODED = [{'id': 'N1', 'name': 'El Huequito', 'address': 'Ayuntamiento 21, Mexico City, Mexico',
             'latitude': 19.43, 'longitude': -99.14, 'category': 'food'}]


@patch('apps.core.services.reels.geocoding.search', return_value=GEOCODED)
@patch('apps.core.services.reels.PlaceExtractor')
@patch('apps.core.services.reels.ReelCaptionFetcher')
class ReelPipelineTests(TestCase):
    def setUp(self):
        cache.clear()

    def wire(self, fetcher_cls, extractor_cls, fetched=FETCHED, extracted=EXTRACTED):
        fetcher_cls.return_value.fetch.return_value = fetched
        extractor_cls.return_value.extract.return_value = extracted

    def test_geocodes_and_caches(self, fetcher_cls, extractor_cls, search):
        self.wire(fetcher_cls, extractor_cls)
        result = get_reel_places('https://instagram.com/reels/ABC123/?igsh=1')
        self.assertEqual(result['places'][0]['latitude'], 19.43)
        search.assert_called_once_with('El Huequito, Mexico City, Mexico', limit=1)

        entry = InstagramReelCache.objects.get()
        self.assertEqual(entry.url, URL)
        self.assertEqual(entry.status, InstagramReelCache.STATUS_ANALYZED)
        self.assertEqual(entry.date_posted.year, 2025)

        get_reel_places(URL)
        fetcher_cls.return_value.fetch.assert_called_once()

    def test_unfound_place_keeps_null_coordinates(self, fetcher_cls, extractor_cls, search):
        self.wire(fetcher_cls, extractor_cls)
        search.return_value = []
        place = get_reel_places(URL)['places'][0]
        self.assertIsNone(place['latitude'])
        self.assertEqual(place['address'], 'Mexico City, Mexico')

    def test_failures_are_cached_briefly(self, fetcher_cls, extractor_cls, search):
        fetcher_cls.return_value.fetch.side_effect = InstagramExtractionError('private')
        with self.assertRaises(InstagramExtractionError):
            get_reel_places(URL)
        with self.assertRaises(InstagramExtractionError):
            get_reel_places(URL)
        fetcher_cls.return_value.fetch.assert_called_once()

        InstagramReelCache.objects.update(analyzed_at=timezone.now() - timedelta(days=2))
        fetcher_cls.return_value.fetch.side_effect = None
        self.wire(fetcher_cls, extractor_cls)
        self.assertEqual(len(get_reel_places(URL)['places']), 1)

    def test_stale_success_is_refreshed(self, fetcher_cls, extractor_cls, search):
        self.wire(fetcher_cls, extractor_cls)
        get_reel_places(URL)
        InstagramReelCache.objects.update(analyzed_at=timezone.now() - timedelta(days=31))
        get_reel_places(URL)
        self.assertEqual(fetcher_cls.return_value.fetch.call_count, 2)


@patch('apps.core.services.reels.geocoding.search', return_value=GEOCODED)
@patch('apps.core.services.reels.PlaceExtractor')
@patch('apps.core.services.reels.ReelCaptionFetcher')
class AnalyzeReelAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='a@x.com', email='a@x.com', password='Correct-Horse-9')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def post(self, url=URL):
        return self.client.post('/api/v1/reels/analyze/', {'url': url}, format='json')

    def test_found(self, fetcher_cls, extractor_cls, search):
        fetcher_cls.return_value.fetch.return_value = FETCHED
        extractor_cls.return_value.extract.return_value = EXTRACTED
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'found')
        self.assertEqual(response.data['places'][0]['name'], 'El Huequito')
        self.assertFalse(response.data['places'][0]['already_saved'])

    def test_marks_places_already_saved_from_this_reel(self, fetcher_cls, extractor_cls, search):
        fetcher_cls.return_value.fetch.return_value = FETCHED
        extractor_cls.return_value.extract.return_value = EXTRACTED
        SavedLocation.objects.create(user=self.user, name='el huequito', latitude=1, longitude=1, instagram_url=URL)
        self.assertTrue(self.post().data['places'][0]['already_saved'])

    def test_unreadable_reel_is_manual_required_not_error(self, fetcher_cls, extractor_cls, search):
        fetcher_cls.return_value.fetch.side_effect = InstagramExtractionError('private')
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'status': 'manual_required', 'url': URL, 'reason': 'private'})

    def test_no_places_is_manual_required(self, fetcher_cls, extractor_cls, search):
        fetcher_cls.return_value.fetch.return_value = FETCHED
        extractor_cls.return_value.extract.return_value = []
        self.assertEqual(self.post().data['status'], 'manual_required')

    @override_settings(REEL_ANALYSIS_ENABLED=False)
    def test_feature_flag_off(self, fetcher_cls, extractor_cls, search):
        self.assertEqual(self.post().data['status'], 'manual_required')
        fetcher_cls.return_value.fetch.assert_not_called()

    def test_rejects_non_instagram_urls(self, fetcher_cls, extractor_cls, search):
        response = self.post('https://evil.example.com/reel/ABC/')
        self.assertEqual(response.status_code, 400)
        fetcher_cls.return_value.fetch.assert_not_called()
