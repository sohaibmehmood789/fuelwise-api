"""Conservative offline joins between price records and OSM fuel POIs.

Never use town centroids as station coordinates. Ambiguous identities and
conflicting locations remain unresolved for explicit review.
"""
import json
import math
import re
from collections import defaultdict
from django.conf import settings
from shapely.geometry import Point, shape
from .geometry import haversine
from .locations import STATES


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def brand(value):
    value = normalized(value)
    for pattern, name in [('flyingj', 'pilotflyingj'), ('pilot', 'pilotflyingj'), ('loves', 'loves'), ('roadranger', 'roadranger'), ('sappbro', 'sapp'), ('kwiktrip', 'kwiktrip'), ('kwikstar', 'kwikstar'), ('circlek', 'circlek'), ('quiktrip', 'quiktrip'), ('speedway', 'speedway'), ('7eleven', '7eleven'), ('travelcentersofamerica', 'ta'), ('petrostopping', 'petro')]:
        if pattern in value:
            return name
    if value.startswith('ta') and ('travel' in value or 'truck' in value):
        return 'ta'
    return None


def store_number(name):
    match = re.search(r'#\s*(\d+)', name)
    return str(int(match.group(1))) if match else None


def match_elements(stations, aliases, elements):
    by_store, by_city_name = defaultdict(set), defaultdict(set)
    by_id = {s.external_id: s for s in stations}
    for station in stations:
        for name in {station.name, *aliases.get(station.external_id, [])}:
            by_city_name[(normalized(station.city), station.state, normalized(name))].add(station.external_id)
            chain, number = brand(name), store_number(name)
            if chain and number:
                by_store[(chain, number, station.state)].add(station.external_id)
    state_shapes = {feature['properties']['name']: shape(feature['geometry']) for feature in json.loads((settings.BASE_DIR / 'data' / 'us_states.geojson').read_text())['features']}
    proposals = defaultdict(list)
    for element in elements:
        tags = element.get('tags', {})
        if tags.get('amenity') != 'fuel':
            continue
        location = element.get('center', element)
        lat, lon = location.get('lat'), location.get('lon')
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lon)):
            continue
        point = Point(lon, lat)
        states = [code for code, name in STATES.items() if state_shapes.get(name) is not None and state_shapes[name].distance(point) <= .01]
        # Shared national borders can produce two state candidates; ambiguity
        # is resolved only by a unique source identity, never proximity alone.
        candidates = set()
        method = 'brand_store_number'
        chain = brand(' '.join(str(tags.get(k, '')) for k in ('name', 'brand', 'operator')))
        number = store_number(tags.get('name', ''))
        reference = tags.get('ref', '').strip()
        if number is None and re.fullmatch(r'\d+', reference):
            number = str(int(reference))
        if chain and number:
            for state in states:
                candidates.update(by_store.get((chain, number, state), set()))
        if not candidates and tags.get('addr:city'):
            method = 'exact_name_city_state'
            for state in states:
                candidates.update(by_city_name.get((normalized(tags['addr:city']), state, normalized(tags.get('name', ''))), set()))
        if len(candidates) == 1:
            station_id = next(iter(candidates))
            proposals[station_id].append({'id': station_id, 'latitude': lat, 'longitude': lon, 'source': f"osm:{element['type']}/{element['id']};{method}", 'osm_name': tags.get('name', ''), 'source_name': by_id[station_id].name, 'method': method})
    accepted, ambiguous = [], []
    for station_id, proposals_for_station in proposals.items():
        first = proposals_for_station[0]
        if any(haversine([first['longitude'], first['latitude']], [other['longitude'], other['latitude']]) > .25 for other in proposals_for_station):
            ambiguous.append(station_id)
        else:
            accepted.append(first)
    return sorted(accepted, key=lambda row: row['id']), sorted(ambiguous)
