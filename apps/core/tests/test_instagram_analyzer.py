from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.instagram.analyzer import (
    InstagramExtractionError,
    InstagramReelDescriptionExtractor,
    LocationExtractor,
)


class DescriptionExtractorTests(TestCase):
    """
    Instagram now serves a generic login-wall page (no og:description meta
    tag) to unauthenticated requests - confirmed against a real, live public
    reel URL during development. These tests pin that failure mode so a
    regression (or Instagram changing behavior again) is caught.
    """

    def setUp(self):
        self.extractor = InstagramReelDescriptionExtractor()

    @patch('apps.core.instagram.analyzer.requests.Session.get')
    def test_scrape_returns_none_on_login_wall_page(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text='<html><head><title>Instagram</title></head><body>Log in</body></html>')
        self.assertIsNone(self.extractor._extract_via_scrape('https://www.instagram.com/reel/abc123/'))

    @patch('apps.core.instagram.analyzer.requests.Session.get')
    def test_scrape_extracts_caption_when_meta_tag_present(self, mock_get):
        html_body = (
            '<html><head>'
            '<meta property="og:description" content="120 likes, 4 comments - travelbot on January 1, 2025: '
            'Amazing sunset at Golden Gate Bridge!">'
            '</head></html>'
        )
        mock_get.return_value = MagicMock(status_code=200, text=html_body)
        result = self.extractor._extract_via_scrape('https://www.instagram.com/reel/abc123/')
        self.assertIsNotNone(result)
        self.assertIn('Golden Gate Bridge', result['description'])
        self.assertEqual(result['likes'], '120')

    @patch('apps.core.instagram.analyzer.requests.Session.get')
    def test_extract_description_raises_when_every_path_fails(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, text='<html><title>Instagram</title></html>')
        with self.assertRaises(InstagramExtractionError):
            self.extractor.extract_description('https://www.instagram.com/reel/abc123/')

    @patch('apps.core.instagram.analyzer.requests.Session.get')
    def test_oembed_used_when_token_configured_and_scrape_not_attempted_first(self, mock_get):
        extractor = InstagramReelDescriptionExtractor(oembed_access_token='app-id|client-token')
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {'html': '<blockquote><p>A trip to the Eiffel Tower.</p></blockquote>'},
        )
        result = extractor.extract_description('https://www.instagram.com/reel/abc123/')
        self.assertIn('Eiffel Tower', result['description'])
        # oEmbed succeeded, so the scrape fallback should never have been called.
        mock_get.assert_called_once()


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


class AnalyzeReelViewTests(TestCase):
    """Verifies the API contract the mobile app's share-to-save flow depends on:
    a reel whose caption can't be read comes back as a normal 200 'manual_required'
    response, not an error the client has to special-case."""

    def setUp(self):
        self.user = User.objects.create_user(username='vtester', password='TestPass123!', email='v@example.com')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('apps.core.views.InstagramReelAnalyzer')
    def test_extraction_failure_returns_manual_required(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.side_effect = InstagramExtractionError('blocked')
        response = self.client.post('/api/v1/analyze-reel/', {'url': 'https://www.instagram.com/reel/abc123/'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'manual_required')
        self.assertEqual(response.data['url'], 'https://www.instagram.com/reel/abc123/')

    @patch('apps.core.views.InstagramReelAnalyzer')
    def test_no_locations_found_returns_manual_required(self, mock_analyzer_cls):
        mock_analyzer_cls.return_value.analyze_reel.return_value = {'description': 'just a sunset', 'locations': []}
        response = self.client.post('/api/v1/analyze-reel/', {'url': 'https://www.instagram.com/reel/abc123/'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'manual_required')

    @patch('apps.core.views.InstagramReelAnalyzer')
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
