from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.categories import category_for_osm_tag, normalize_category
from apps.core.services import geocoding

User = get_user_model()

PHOTON_RESPONSE = {'features': [{
    'properties': {'osm_type': 'N', 'osm_id': 42, 'osm_key': 'amenity', 'osm_value': 'cafe',
                   'name': 'Blue Bottle Coffee', 'housenumber': '66', 'street': 'Mint Street',
                   'city': 'San Francisco', 'state': 'California', 'country': 'United States'},
    'geometry': {'coordinates': [-122.40, 37.78]},
}]}


def photon_ok(payload=PHOTON_RESPONSE):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class CategoryMappingTests(TestCase):
    def test_osm_tags(self):
        self.assertEqual(category_for_osm_tag('amenity', 'cafe'), 'cafe')
        self.assertEqual(category_for_osm_tag('natural', 'beach'), 'beach')
        self.assertEqual(category_for_osm_tag('natural', 'peak'), 'nature')
        self.assertEqual(category_for_osm_tag('shop', 'books'), 'shopping')
        self.assertEqual(category_for_osm_tag('highway', 'residential'), 'other')
        self.assertEqual(category_for_osm_tag('place', 'square'), 'landmark')
        self.assertEqual(category_for_osm_tag('highway', 'motorway', 'Golden Gate Bridge'), 'landmark')

    def test_normalize(self):
        self.assertEqual(normalize_category('Bars & Nightlife'), 'bar')
        self.assertEqual(normalize_category(' CAFE '), 'cafe')
        self.assertEqual(normalize_category(None), 'other')


class GeocodingServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('apps.core.services.geocoding.requests.get', return_value=photon_ok())
    def test_search_shapes_results_and_caches(self, get):
        results = geocoding.search('blue bottle', near=(37.7749, -122.4194))
        self.assertEqual(results, [{
            'id': 'N42', 'name': 'Blue Bottle Coffee',
            'address': '66 Mint Street, San Francisco, California, United States',
            'latitude': 37.78, 'longitude': -122.40, 'category': 'cafe',
        }])
        params = get.call_args.kwargs['params']
        self.assertEqual((params['lat'], params['lon']), (37.77, -122.42))
        self.assertIn('User-Agent', get.call_args.kwargs['headers'])

        geocoding.search('  Blue   Bottle ', near=(37.7741, -122.4190))
        get.assert_called_once()

    @patch('apps.core.services.geocoding.requests.get')
    def test_split_features_of_one_place_are_merged(self, get):
        segment = PHOTON_RESPONSE['features'][0]
        nearby = {**segment, 'geometry': {'coordinates': [-122.401, 37.781]}}
        same_address = {**segment, 'geometry': {'coordinates': [-122.45, 37.80]}}
        other_branch = {**segment, 'geometry': {'coordinates': [-122.45, 37.80]},
                        'properties': {**segment['properties'], 'street': 'Market Street'}}
        get.return_value = photon_ok({'features': [segment, nearby, same_address, other_branch]})
        results = geocoding.search('blue bottle')
        self.assertEqual([r['address'].split(',')[0] for r in results], ['66 Mint Street', '66 Market Street'])

    def test_short_queries_skip_the_network(self):
        with patch('apps.core.services.geocoding.requests.get') as get:
            self.assertEqual(geocoding.search('a'), [])
            get.assert_not_called()

    @patch('apps.core.services.geocoding.requests.get', side_effect=requests.ConnectionError())
    def test_network_errors_raise_geocoding_error(self, get):
        with self.assertRaises(geocoding.GeocodingError):
            geocoding.search('anything')

    @patch('apps.core.services.geocoding.requests.get', return_value=photon_ok())
    def test_reverse_keeps_the_exact_tapped_point(self, get):
        result = geocoding.reverse(37.781234567, -122.401234567)
        self.assertEqual(result['name'], 'Blue Bottle Coffee')
        self.assertEqual((result['latitude'], result['longitude']), (37.781234567, -122.401234567))


class GeocodeAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(username='u', email='u@x.com', password='x'))

    @patch('apps.core.services.geocoding.requests.get', return_value=photon_ok())
    def test_search_endpoint(self, get):
        response = self.client.get('/api/v1/geocode/search/?q=blue+bottle&lat=37.7&lon=-122.4')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['name'], 'Blue Bottle Coffee')

    @patch('apps.core.services.geocoding.requests.get', return_value=photon_ok({'features': []}))
    def test_reverse_in_the_middle_of_nowhere_still_returns_a_pin(self, get):
        response = self.client.get('/api/v1/geocode/reverse/?lat=0&lon=-30')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Dropped pin')

    def test_reverse_validates_coordinates(self):
        self.assertEqual(self.client.get('/api/v1/geocode/reverse/?lat=200&lon=0').status_code, 400)

    @patch('apps.core.services.geocoding.requests.get', side_effect=requests.Timeout())
    def test_provider_down_is_503(self, get):
        self.assertEqual(self.client.get('/api/v1/geocode/search/?q=coffee').status_code, 503)

    def test_requires_auth(self):
        self.assertEqual(APIClient().get('/api/v1/geocode/search/?q=coffee').status_code, 401)
