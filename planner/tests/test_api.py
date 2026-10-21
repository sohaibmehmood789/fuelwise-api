import json
import tempfile
import uuid
from pathlib import Path
from contextlib import nullcontext
from decimal import Decimal
from unittest.mock import Mock, patch
import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from planner.geometry import METERS_PER_MILE, station_index
from planner.models import Dataset, Station


def route_response(legs, coordinates=None):
    return {'code': 'Ok', 'routes': [{'distance': sum(legs)*METERS_PER_MILE, 'duration': 72000, 'geometry': {'type': 'LineString', 'coordinates': coordinates or [[-120, 35], [-96, 35]]}, 'legs': [{'distance': miles*METERS_PER_MILE} for miles in legs]}]}


class APITests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = override_settings(LOCK_DIR=Path(self.temp.name), CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.addCleanup(self.temp.cleanup)
        cache.clear()
        station_index.cache_clear()
        Dataset.objects.create(pk=1, version=uuid.uuid4(), source='test.csv')
        for station_id, lon, price in [('a', -114, 3), ('b', -106, 2)]:
            Station.objects.create(external_id=station_id, name=station_id, address='Test Road', city='Test', state='TX', latitude=35, longitude=lon, price=Decimal(price))
        self.slot = patch('planner.providers.provider_slot', side_effect=lambda _: nullcontext())
        self.slot.start()
        self.addCleanup(self.slot.stop)

    def post(self, payload=None):
        return self.client.post('/api/v1/plan/', json.dumps(payload or {'start': 'Start, CA', 'finish': 'Finish, TX', 'initial_fuel_price_usd': 4}), content_type='application/json')

    def provider(self, url, **kwargs):
        if '/api/' in url or '/structured' in url:
            query = kwargs['params'].get('q', kwargs['params'].get('city', ''))
            coords = [-120, 35] if query.startswith('Start') else [-96, 35]
            data = {'features': [{'properties': {'countrycode': 'US', 'name': 'Test USA'}, 'geometry': {'coordinates': coords}}]}
        else:
            data = route_response([300, 400, 500] if url.count(';') == 3 else [1200])
        return Mock(status_code=200, json=Mock(return_value=data), raise_for_status=Mock())

    @patch('planner.providers.requests.get')
    def test_verified_multiple_stops_costs_and_cache_budget(self, get):
        get.side_effect = self.provider
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['meta']['external_calls'], {'geocoding': 2, 'routing': 2})
        self.assertEqual([s['id'] for s in data['fuel_stops']], ['a', 'b'])
        self.assertEqual(data['fuel']['total_money_spent_usd'], '160.00')
        self.assertEqual(data['fuel']['total_trip_fuel_cost_usd'], '360.00')
        self.assertEqual(data['fuel']['gallons_consumed'], 120)
        self.assertEqual(data['fuel']['gallons_purchased'], 70)
        self.assertEqual(self.client.get(data['map_url']).status_code, 200)
        again = self.post().json()
        self.assertTrue(again['meta']['plan_cache_hit'])
        self.assertEqual(again['meta']['external_calls'], {'geocoding': 0, 'routing': 0})
        self.assertEqual(get.call_count, 4)

    @patch('planner.providers.requests.get')
    def test_short_trip_requires_one_route_call_and_no_stops(self, get):
        def provider(url, **kwargs):
            if '/route/v1/' in url:
                return Mock(status_code=200, json=Mock(return_value=route_response([100])), raise_for_status=Mock())
            return self.provider(url, **kwargs)
        get.side_effect = provider
        data = self.post().json()
        self.assertEqual(data['fuel_stops'], [])
        self.assertEqual(data['meta']['external_calls']['routing'], 1)
        self.assertEqual(data['fuel']['total_money_spent_usd'], '0.00')
        self.assertEqual(data['fuel']['total_trip_fuel_cost_usd'], '40.00')

    @patch('planner.providers.requests.get')
    def test_final_road_distances_must_be_feasible(self, get):
        def provider(url, **kwargs):
            if url.count(';') == 3:
                return Mock(status_code=200, json=Mock(return_value=route_response([510, 400, 500])), raise_for_status=Mock())
            return self.provider(url, **kwargs)
        get.side_effect = provider
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'verified_route_infeasible')
        self.assertEqual(get.call_count, 4)

    @patch('planner.providers.requests.get')
    def test_foreign_locations_are_rejected(self, get):
        get.return_value = Mock(status_code=200, json=Mock(return_value={'features': [{'properties': {'countrycode': 'CA'}}]}), raise_for_status=Mock())
        self.assertEqual(self.post().status_code, 400)

    @patch('planner.providers.requests.get', side_effect=requests.Timeout)
    def test_provider_timeout_is_structured_and_not_retried(self, get):
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'provider_unavailable')
        self.assertEqual(get.call_count, 1)

    @patch('planner.providers.requests.get')
    def test_corrupt_provider_data_is_503(self, get):
        get.return_value = Mock(status_code=200, json=Mock(return_value={}), raise_for_status=Mock())
        self.assertEqual(self.post().status_code, 503)

    def test_invalid_requests(self):
        for payload in [{}, [], {'start': 'x', 'finish': 'Texas'}, {'start': 'California', 'finish': 'Texas', 'initial_fuel_gallons': 51}, {'start': 'California', 'finish': 'Texas', 'corridor_miles': True}, {'start': 'California', 'finish': 'Texas', 'surprise': 1}]:
            with self.subTest(payload=payload):
                response = self.client.post('/api/v1/plan/', json.dumps(payload), content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/api/v1/plan/', '{"start":NaN}', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/api/v1/plan/', 'bad', content_type='text/plain').status_code, 415)
        self.assertEqual(self.client.get('/api/v1/plan/').status_code, 405)
        self.assertEqual(self.post({'start': 'California', 'finish': 'Texas', 'initial_fuel_gallons': 10**500}).status_code, 400)
        self.assertEqual(self.post({'start': 'x'*17000, 'finish': 'Texas'}).status_code, 413)

    @patch('planner.providers.requests.get')
    def test_city_queries_are_structured_and_expand_state(self, get):
        get.side_effect = self.provider
        self.assertEqual(self.post().status_code, 200)
        geocode_call = get.call_args_list[0]
        self.assertIn('/structured', geocode_call.args[0])
        self.assertEqual(geocode_call.kwargs['params']['state'], 'California')
        self.assertEqual(geocode_call.kwargs['params']['countrycode'], 'US')

    @patch('planner.providers.requests.get')
    def test_no_road_segment_is_422(self, get):
        def provider(url, **kwargs):
            if '/route/v1/' in url:
                return Mock(status_code=400, json=Mock(return_value={'code': 'NoSegment'}))
            return self.provider(url, **kwargs)
        get.side_effect = provider
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'no_drivable_route')

    def test_map_assets_are_local_and_versioned(self):
        for name, content_type in [('js', 'text/javascript'), ('css', 'text/css')]:
            response = self.client.get(f'/assets/leaflet-1.9.4.{name}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], content_type)
            response.close()

    def test_no_dataset(self):
        Dataset.objects.all().delete()
        self.assertEqual(self.post().status_code, 503)

    @patch('planner.providers.requests.get')
    def test_unlocated_dataset_is_reported_without_external_calls(self, get):
        Dataset.objects.update(report={'unique_usa_stations': 6626, 'located_stations': 0})
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'station_coordinates_missing')
        get.assert_not_called()

    def test_expired_map(self):
        self.assertEqual(self.client.get(f'/api/v1/maps/{uuid.uuid4()}/').status_code, 404)

    @patch('planner.providers.requests.get')
    def test_import_version_invalidates_cached_plans(self, get):
        get.side_effect = self.provider
        self.assertEqual(self.post().status_code, 200)
        Dataset.objects.update(version=uuid.uuid4())
        result = self.post().json()
        self.assertFalse(result['meta']['plan_cache_hit'])
        self.assertEqual(result['meta']['external_calls'], {'geocoding': 0, 'routing': 0})

    @patch('planner.providers.requests.get')
    def test_map_does_not_interpret_station_html(self, get):
        Station.objects.filter(external_id='a').update(name='</script><script>alert(1)</script>')
        get.side_effect = self.provider
        data = self.post().json()
        html = self.client.get(data['map_url']).content.decode()
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('\\u003C/script\\u003E', html)
