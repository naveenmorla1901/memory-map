from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.instagram.analyzer import InstagramExtractionError
from apps.core.models import InstagramReelCache
from apps.core.services.reel_cache import get_reel_analysis

URL = 'https://www.instagram.com/reel/abc123/'


def age_entry(entry: InstagramReelCache, days: float):
    """auto_now overwrites analyzed_at on save(), so back-date it with a direct update()."""
    InstagramReelCache.objects.filter(pk=entry.pk).update(analyzed_at=timezone.now() - timedelta(days=days))


class InstagramReelCacheModelTests(TestCase):
    def test_fresh_success_is_not_stale(self):
        entry = InstagramReelCache.objects.create(url=URL, status=InstagramReelCache.STATUS_ANALYZED)
        self.assertFalse(entry.is_stale())

    def test_success_older_than_30_days_is_stale(self):
        entry = InstagramReelCache.objects.create(url=URL, status=InstagramReelCache.STATUS_ANALYZED)
        age_entry(entry, InstagramReelCache.SUCCESS_MAX_AGE_DAYS + 1)
        entry.refresh_from_db()
        self.assertTrue(entry.is_stale())

    def test_failure_is_stale_much_sooner_than_a_success(self):
        entry = InstagramReelCache.objects.create(url=URL, status=InstagramReelCache.STATUS_FAILED)
        age_entry(entry, InstagramReelCache.FAILURE_MAX_AGE_DAYS + 0.1)
        entry.refresh_from_db()
        self.assertTrue(entry.is_stale())


class GetReelAnalysisTests(TestCase):
    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_first_call_runs_the_analyzer_and_caches_the_result(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {
            'description': 'A trip to the Eiffel Tower.',
            'date_posted': '20250101',
            'locations': [{'name': 'Eiffel Tower', 'type': 'landmark', 'category': 'monument', 'coordinates': None}],
        }

        result = get_reel_analysis(URL, google_api_key='key')

        self.assertEqual(result['description'], 'A trip to the Eiffel Tower.')
        self.assertEqual(len(result['locations']), 1)
        mock_analyzer_cls.return_value.analyze_reel.assert_called_once_with(URL)

        entry = InstagramReelCache.objects.get(url=URL)
        self.assertEqual(entry.status, InstagramReelCache.STATUS_ANALYZED)
        self.assertEqual(entry.locations, result['locations'])

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_second_call_uses_the_cache_instead_of_the_analyzer(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {
            'description': 'A trip to the Eiffel Tower.',
            'date_posted': None,
            'locations': [{'name': 'Eiffel Tower', 'type': 'landmark', 'category': 'monument', 'coordinates': None}],
        }

        get_reel_analysis(URL, google_api_key='key')
        second = get_reel_analysis(URL, google_api_key='key')

        mock_analyzer_cls.return_value.analyze_reel.assert_called_once()
        self.assertEqual(second['description'], 'A trip to the Eiffel Tower.')

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_stale_cache_entry_triggers_a_fresh_analysis(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {
            'description': 'fresh', 'date_posted': None, 'locations': [],
        }
        entry = InstagramReelCache.objects.create(
            url=URL, status=InstagramReelCache.STATUS_ANALYZED, description='stale'
        )
        age_entry(entry, InstagramReelCache.SUCCESS_MAX_AGE_DAYS + 1)

        get_reel_analysis(URL, google_api_key='key')

        mock_analyzer_cls.return_value.analyze_reel.assert_called_once()

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_no_locations_found_is_cached_as_no_locations_not_failed(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {
            'description': 'just a sunset', 'date_posted': None, 'locations': [],
        }

        get_reel_analysis(URL, google_api_key='key')

        entry = InstagramReelCache.objects.get(url=URL)
        self.assertEqual(entry.status, InstagramReelCache.STATUS_NO_LOCATIONS)

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_failure_is_cached_and_reraised_without_calling_the_analyzer_again(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.side_effect = InstagramExtractionError('reel is private')

        with self.assertRaises(InstagramExtractionError):
            get_reel_analysis(URL, google_api_key='key')

        entry = InstagramReelCache.objects.get(url=URL)
        self.assertEqual(entry.status, InstagramReelCache.STATUS_FAILED)
        self.assertEqual(entry.failure_reason, 'reel is private')

        # A second call within the (short) failure TTL shouldn't hit yt-dlp/Gemini again.
        with self.assertRaises(InstagramExtractionError) as second_call:
            get_reel_analysis(URL, google_api_key='key')
        self.assertEqual(second_call.exception.reason, 'reel is private')
        mock_analyzer_cls.return_value.analyze_reel.assert_called_once()

    @patch('apps.core.services.reel_cache.InstagramReelAnalyzer')
    def test_stale_failure_is_retried(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {
            'description': 'now it works', 'date_posted': None, 'locations': [],
        }
        entry = InstagramReelCache.objects.create(
            url=URL, status=InstagramReelCache.STATUS_FAILED, failure_reason='was rate limited'
        )
        age_entry(entry, InstagramReelCache.FAILURE_MAX_AGE_DAYS + 0.1)

        result = get_reel_analysis(URL, google_api_key='key')

        mock_analyzer_cls.return_value.analyze_reel.assert_called_once()
        self.assertEqual(result['description'], 'now it works')
