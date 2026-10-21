from types import SimpleNamespace
from unittest import TestCase
from planner.station_matching import match_elements


def station(external_id='1', number='123'):
    return SimpleNamespace(external_id=external_id, name=f'LOVES TRAVEL STOP #{number}', city='Des Moines', state='IA')


def element(osm_id=1, lon=-93.6, lat=41.6, **tags):
    return {'id': osm_id, 'type': 'node', 'lon': lon, 'lat': lat, 'tags': {'amenity': 'fuel', 'name': "Love's", 'brand': "Love's", 'ref': '123', **tags}}


class StationMatchingTests(TestCase):
    def test_joins_unique_brand_store_number_in_expected_state(self):
        matches, conflicts = match_elements([station()], {}, [element()])
        self.assertEqual(matches[0]['id'], '1')
        self.assertEqual(matches[0]['method'], 'brand_store_number')
        self.assertEqual(conflicts, [])

    def test_does_not_guess_ambiguous_identity_or_wrong_state(self):
        self.assertEqual(match_elements([station('1'), station('2')], {}, [element()])[0], [])
        self.assertEqual(match_elements([station()], {}, [element(lon=-118, lat=34)])[0], [])

    def test_conflicting_coordinates_require_review(self):
        matches, conflicts = match_elements([station()], {}, [element(), element(osm_id=2, lon=-93.7)])
        self.assertEqual(matches, [])
        self.assertEqual(conflicts, ['1'])
