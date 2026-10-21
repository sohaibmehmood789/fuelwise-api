import hashlib
import json
import math
import requests
from django.conf import settings
from django.core.cache import cache
from .errors import PlanningError
from .locking import lock, provider_slot
from .locations import geocode_query


class Providers:
    def __init__(self):
        self.calls = {'geocoding': 0, 'routing': 0}

    def fetch(self, provider, url, params, ttl):
        key = 'provider:' + hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        with lock(key):
            saved = cache.get(key)
            if saved is not None:
                return saved
            try:
                with provider_slot(provider):
                    self.calls[provider] += 1
                    response = requests.get(url, params=params, headers={'User-Agent': settings.PROVIDER_USER_AGENT}, timeout=(3.05, 15), allow_redirects=False)
                if provider == 'routing' and response.status_code == 400:
                    problem = response.json()
                    if isinstance(problem, dict) and problem.get('code') in ('NoRoute', 'NoSegment'):
                        raise PlanningError('no_drivable_route', 'No drivable route or nearby road segment for a selected location.')
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected provider status')
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError('Provider response must be an object')
            except (requests.RequestException, ValueError):
                raise PlanningError('provider_unavailable', f'{provider.capitalize()} provider unavailable; please retry.', 503)
            cache.set(key, data, ttl)
            return data

    def geocode(self, query):
        endpoint, params = geocode_query(query)
        data = self.fetch('geocoding', settings.PHOTON_URL.rstrip('/') + endpoint, params, 30 * 86400)
        try:
            for feature in data['features']:
                props = feature['properties']
                if props.get('countrycode', '').upper() == 'US':
                    lon, lat = feature['geometry']['coordinates']
                    if not all(math.isfinite(v) for v in (lon, lat)) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                        raise ValueError()
                    return {'query': query, 'label': ', '.join(str(props[k]) for k in ('name', 'city', 'state', 'country') if props.get(k)), 'coordinates': [lon, lat]}
        except (KeyError, TypeError, ValueError, AttributeError):
            raise PlanningError('invalid_provider_response', 'Geocoder returned malformed data.', 503)
        raise PlanningError('location_not_in_usa', f'No USA location found for {query!r}. Include city and state.', 400)

    def route(self, coordinates):
        coords = ';'.join(f'{lon:.6f},{lat:.6f}' for lon, lat in coordinates)
        radiuses = ';'.join('2000' if i in (0, len(coordinates)-1) else '100' for i in range(len(coordinates)))
        data = self.fetch('routing', settings.OSRM_URL.rstrip('/') + '/route/v1/driving/' + coords, {'overview': 'full', 'geometries': 'geojson', 'steps': 'false', 'alternatives': 'false', 'radiuses': radiuses}, 86400)
        try:
            if data.get('code') in ('NoRoute', 'NoSegment'):
                raise PlanningError('no_drivable_route', 'No drivable route through these locations.')
            route = data['routes'][0]
            if data['code'] != 'Ok' or len(route['legs']) != len(coordinates)-1:
                raise ValueError()
            if route['geometry']['type'] != 'LineString' or len(route['geometry']['coordinates']) < 2:
                raise ValueError()
            for coordinate in route['geometry']['coordinates']:
                lon, lat = coordinate
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coordinate) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError()
            numbers = [route['distance'], route['duration']] + [leg['distance'] for leg in route['legs']]
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in numbers):
                raise ValueError()
            if abs(sum(leg['distance'] for leg in route['legs']) - route['distance']) > 5:
                raise ValueError()
            return route
        except (KeyError, IndexError, TypeError, ValueError):
            raise PlanningError('invalid_provider_response', 'Router returned malformed data.', 503)
