from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import SavedLocation

User = get_user_model()


def make_user(email='alice@example.com'):
    return User.objects.create_user(username=email, email=email, password='Correct-Horse-9', first_name='Alice')


PLACE = {'name': 'Blue Bottle', 'latitude': 37.78, 'longitude': -122.40, 'category': 'cafe'}


class SavedLocationAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_and_list(self):
        response = self.client.post('/api/v1/locations/', PLACE, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['category'], 'cafe')
        self.assertEqual(response.data['source'], 'manual')

        listed = self.client.get('/api/v1/locations/').data
        self.assertEqual([item['name'] for item in listed], ['Blue Bottle'])

    def test_unknown_category_is_normalized_not_rejected(self):
        response = self.client.post('/api/v1/locations/', {**PLACE, 'category': 'Restaurant-ish'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['category'], 'other')
        response = self.client.post('/api/v1/locations/', {**PLACE, 'category': 'Food'}, format='json')
        self.assertEqual(response.data['category'], 'food')

    def test_rejects_out_of_range_coordinates_and_blank_name(self):
        response = self.client.post('/api/v1/locations/', {**PLACE, 'latitude': 91}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)
        response = self.client.post('/api/v1/locations/', {**PLACE, 'name': '   '}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_instagram_url_sets_source_and_is_canonicalized(self):
        response = self.client.post('/api/v1/locations/', {
            **PLACE, 'instagram_url': 'https://instagram.com/reels/ABC123/?igsh=tracking',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['source'], 'instagram')
        self.assertEqual(response.data['instagram_url'], 'https://www.instagram.com/reel/ABC123/')

    def test_other_users_cannot_see_or_edit_my_places(self):
        mine = SavedLocation.objects.create(user=self.user, **PLACE)
        intruder = APIClient()
        intruder.force_authenticate(make_user('mallory@example.com'))

        self.assertEqual(intruder.get('/api/v1/locations/').data, [])
        self.assertEqual(intruder.get(f'/api/v1/locations/{mine.id}/').status_code, 404)
        self.assertEqual(intruder.patch(f'/api/v1/locations/{mine.id}/', {'name': 'x'}, format='json').status_code, 404)
        self.assertEqual(intruder.delete(f'/api/v1/locations/{mine.id}/').status_code, 404)
        mine.refresh_from_db()
        self.assertEqual(mine.name, 'Blue Bottle')

    def test_cannot_reassign_owner(self):
        other = make_user('bob@example.com')
        mine = SavedLocation.objects.create(user=self.user, **PLACE)
        self.client.patch(f'/api/v1/locations/{mine.id}/', {'user': other.id}, format='json')
        mine.refresh_from_db()
        self.assertEqual(mine.user, self.user)

    def test_update_and_delete(self):
        mine = SavedLocation.objects.create(user=self.user, **PLACE)
        response = self.client.patch(f'/api/v1/locations/{mine.id}/', {'is_favorite': True, 'visited': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_favorite'])
        self.assertTrue(response.data['visited'])
        self.assertEqual(self.client.delete(f'/api/v1/locations/{mine.id}/').status_code, 204)
        self.assertFalse(SavedLocation.objects.filter(pk=mine.pk).exists())

    def test_filters_search_and_ordering(self):
        SavedLocation.objects.create(user=self.user, **PLACE)
        SavedLocation.objects.create(user=self.user, name='Alcatraz', latitude=37.82, longitude=-122.42,
                                     category='landmark', is_favorite=True, notes='book ferry early')
        names = lambda q: [i['name'] for i in self.client.get(f'/api/v1/locations/?{q}').data]
        self.assertEqual(names('category=landmark'), ['Alcatraz'])
        self.assertEqual(names('favorite=true'), ['Alcatraz'])
        self.assertEqual(names('favorite=false'), ['Blue Bottle'])
        self.assertEqual(names('search=ferry'), ['Alcatraz'])
        self.assertEqual(names('ordering=name'), ['Alcatraz', 'Blue Bottle'])

    def test_bulk_create_is_atomic(self):
        good = {**PLACE, 'instagram_url': 'https://www.instagram.com/reel/ABC/'}
        response = self.client.post('/api/v1/locations/bulk/', {'locations': [good, {**good, 'name': 'Two'}]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data), 2)

        bad = {'locations': [good, {**good, 'latitude': 500}]}
        self.assertEqual(self.client.post('/api/v1/locations/bulk/', bad, format='json').status_code, 400)
        self.assertEqual(SavedLocation.objects.count(), 2)

    def test_stats(self):
        SavedLocation.objects.create(user=self.user, **PLACE, is_favorite=True)
        SavedLocation.objects.create(user=self.user, name='B', latitude=1, longitude=1, category='cafe', visited=True)
        stats = self.client.get('/api/v1/locations/stats/').data
        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['favorites'], 1)
        self.assertEqual(stats['visited'], 1)
        self.assertEqual(stats['by_category'], {'cafe': 2})

    def test_requires_auth(self):
        self.assertEqual(APIClient().get('/api/v1/locations/').status_code, 401)


class CategoriesAPITests(TestCase):
    def test_categories_are_public_and_complete(self):
        response = APIClient().get('/api/v1/categories/')
        self.assertEqual(response.status_code, 200)
        keys = [c['key'] for c in response.data]
        self.assertIn('food', keys)
        self.assertEqual(keys[-1], 'other')


class HealthAndWebPagesTests(TestCase):
    def test_healthz(self):
        self.assertEqual(self.client.get('/healthz/').json(), {'status': 'ok'})

    def test_public_pages_render(self):
        for path in ('/', '/privacy/', '/terms/', '/delete-account/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, 'Memory Map')


class ErrorPageTests(TestCase):
    def test_unknown_api_urls_return_json(self):
        response = self.client.get('/api/v1/does-not-exist/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'detail': 'Not found.'})

    def test_unknown_web_urls_return_the_branded_page(self):
        response = self.client.get('/does-not-exist/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Page not found', status_code=404)

    def test_server_errors(self):
        from django.test import RequestFactory
        from apps.core.web_views import server_error
        api = server_error(RequestFactory().get('/api/v1/locations/'))
        self.assertEqual(api.status_code, 500)
        self.assertIn(b'Something went wrong', api.content)
        web = server_error(RequestFactory().get('/privacy/'))
        self.assertEqual(web.status_code, 500)
        self.assertIn(b'<html', web.content)
