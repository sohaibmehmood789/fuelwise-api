import copy
import hashlib
import json
import math
import time
import uuid
from decimal import Decimal
from django.core.cache import cache
from django.db import transaction
from .errors import PlanningError
from .geometry import METERS_PER_MILE, candidates, haversine, station_index
from .locking import lock
from .models import Dataset
from .optimizer import Stop, decimal, money, optimize
from .providers import Providers


def validate(payload):
    if not isinstance(payload, dict):
        raise PlanningError('invalid_request', 'Request body must be a JSON object.', 400)
    allowed = {'start', 'finish', 'initial_fuel_gallons', 'initial_fuel_price_usd', 'corridor_miles'}
    if set(payload) - allowed:
        raise PlanningError('invalid_request', 'Unknown fields: ' + ', '.join(sorted(set(payload)-allowed)), 400)
    result = {}
    for field in ('start', 'finish'):
        value = payload.get(field)
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 200:
            raise PlanningError('invalid_request', f'{field} must be a location string of 2–200 characters.', 400)
        result[field] = value.strip()
    for field, default, minimum, maximum in [('initial_fuel_gallons', 50, 0, 50), ('corridor_miles', 2, .1, 10), ('initial_fuel_price_usd', None, .01, 100)]:
        value = payload.get(field, default)
        if value is None and field == 'initial_fuel_price_usd':
            result[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum or not math.isfinite(value):
            raise PlanningError('invalid_request', f'{field} must be a finite number between {minimum} and {maximum}.', 400)
        result[field] = value
    return result


def plan_trip(options):
    started = time.perf_counter()
    # Read the version and build its spatial snapshot in the same short DB
    # transaction, so a concurrent import cannot mix old metadata/new prices.
    with transaction.atomic():
        dataset = Dataset.objects.first()
        snapshot = station_index(str(dataset.version)) if dataset else None
    if dataset is None:
        raise PlanningError('station_data_missing', 'Import the fuel-price CSV before planning a route.', 503)
    if dataset.report and not dataset.report.get('located_stations'):
        raise PlanningError('station_coordinates_missing', f"Imported {dataset.report.get('unique_usa_stations', 0)} USA stations, but none have coordinates yet. Run offline coordinate enrichment before planning.", 503)
    key = 'plan:' + hashlib.sha256(json.dumps([str(dataset.version), options], sort_keys=True).encode()).hexdigest()
    providers = Providers()
    with lock(key):
        result = cache.get(key)
        hit = result is not None
        if result is None:
            result = compute(options, dataset, providers, snapshot)
            cache.set(key, result, 900)
    result = copy.deepcopy(result)
    result['meta'] = {'plan_cache_hit': hit, 'external_calls': providers.calls, 'elapsed_ms': round((time.perf_counter()-started)*1000, 2)}
    return result


def station_json(station):
    return {'id': station.external_id, 'name': station.name, 'address': station.address, 'city': station.city, 'state': station.state, 'coordinates': [station.longitude, station.latitude], 'coordinate_source': station.coordinate_source, 'price_per_gallon_usd': str(station.price)}


def compute(options, dataset, providers, snapshot):
    start = providers.geocode(options['start'])
    finish = providers.geocode(options['finish'])
    if haversine(start['coordinates'], finish['coordinates']) < .01:
        raise PlanningError('identical_locations', 'Start and finish must be different locations.', 400)
    base = providers.route([start['coordinates'], finish['coordinates']])
    stations, tree = snapshot
    if not stations:
        raise PlanningError('station_data_missing', 'The fuel-price dataset is empty.', 503)
    initial_fuel = decimal(options['initial_fuel_gallons'])
    stops = candidates(base, stations, tree, options['corridor_miles'])
    proposed, _, _ = optimize(stops, decimal(base['distance']) / decimal(METERS_PER_MILE), initial_fuel)
    selected = [p['stop'].station for p in proposed]
    if len(selected) > 40:
        raise PlanningError('too_many_stops', 'This plan needs more than 40 stops; split the journey.')
    route = base
    final_stops = []
    if selected:
        route = providers.route([start['coordinates'], *[[s.longitude, s.latitude] for s in selected], finish['coordinates']])
        position = Decimal(0)
        for station, leg in zip(selected, route['legs']):
            position += decimal(leg['distance']) / decimal(METERS_PER_MILE)
            final_stops.append(Stop(position, station.price, station))
    distance = decimal(route['distance']) / decimal(METERS_PER_MILE)
    try:
        purchases, purchase_cost, remaining = optimize(final_stops, distance, initial_fuel)
    except PlanningError:
        raise PlanningError('verified_route_infeasible', 'Road distances through the chosen stations exceed the available fuel. No feasible verified plan was found within the two-routing-call budget; try a wider station corridor.')
    price = options['initial_fuel_price_usd']
    price_source = {'type': 'request'}
    if price is None:
        nearest = min(stations, key=lambda s: haversine(start['coordinates'], [s.longitude, s.latitude]))
        price = nearest.price
        price_source = {'type': 'nearest_dataset_station_estimate', 'station_id': nearest.external_id, 'straight_line_distance_miles': round(haversine(start['coordinates'], [nearest.longitude, nearest.latitude]), 2)}
    price = decimal(price)
    initial_used = min(initial_fuel, distance / Decimal(10))
    initial_consumed_cost = initial_used * price
    fuel_stops = []
    for purchase in purchases:
        stop = purchase['stop']
        fuel_stops.append({**station_json(stop.station), 'mile_on_route': round(float(stop.miles), 3), 'gallons_to_buy': round(float(purchase['gallons']), 8), 'cost_usd': money(purchase['cost']), 'arrival_fuel_gallons': round(float(purchase['arrival_fuel']), 8), 'departure_fuel_gallons': round(float(purchase['departure_fuel']), 8)})
    # Reconcile cent-rounded display amounts exactly, avoiding sum discrepancies.
    purchase_cost = sum((Decimal(s['cost_usd']) for s in fuel_stops), Decimal(0))
    map_id = uuid.uuid4()
    result = {
        'start': start, 'finish': finish,
        'vehicle': {'range_miles': 500, 'mpg': 10, 'tank_capacity_gallons': 50, 'initial_fuel_gallons': float(initial_fuel)},
        'route': {'distance_miles': round(float(distance), 3), 'duration_seconds': round(route['duration']), 'geometry': route['geometry'], 'waypoints': [station_json(s) for s in selected], 'leg_distances_miles': [round(l['distance']/METERS_PER_MILE, 3) for l in route['legs']]},
        'fuel_stops': fuel_stops,
        'fuel': {'gallons_consumed': round(float(distance/10), 8), 'gallons_purchased': round(sum(s['gallons_to_buy'] for s in fuel_stops), 8), 'arrival_fuel_gallons': round(float(remaining), 8), 'total_money_spent_usd': money(purchase_cost), 'initial_fuel_price_usd': str(price), 'initial_fuel_price_source': price_source, 'initial_fuel_consumed_cost_usd': money(initial_consumed_cost), 'total_trip_fuel_cost_usd': money(purchase_cost + Decimal(money(initial_consumed_cost)))},
        'map_url': f'/api/v1/maps/{map_id}/',
        'dataset': {'source': dataset.source, 'version': str(dataset.version), 'imported_at': dataset.imported_at.isoformat(), 'report': dataset.report, 'coordinate_coverage_complete': not bool(dataset.report.get('unlocated_stations', 0))},
        'assumptions': ['Start with 50 gallons unless initial_fuel_gallons is provided.', 'total_money_spent_usd is fuel purchased during the trip; total_trip_fuel_cost_usd also values starting fuel consumed.', 'Station discovery uses approximate projections within the corridor; road distances and tank feasibility are then verified through selected waypoints.', 'Fuel purchases minimize cost for the final ordered waypoints. Station selection is a heuristic; this is not a global optimum across all roads and stations.', 'Routing may snap station coordinates to a road within 100 meters; station entrance access, fuel availability, and current prices are not guaranteed.', 'Some verified waypoints may require no purchase after road-distance recalculation.', 'Zero arrival reserve; 10 mpg is constant. Fuel prices are USD per US gallon.'],
        'attribution': '© OpenStreetMap contributors (ODbL); routing by OSRM / FOSSGIS; geocoding by Photon / komoot.',
    }
    if dataset.report.get('unlocated_stations', 0):
        result['assumptions'].append(f"Coordinate coverage is partial: {dataset.report.get('located_stations', 0)} of {dataset.report.get('unique_usa_stations', 0)} CSV stations are located. Unlocated station prices cannot participate in route optimization.")
    cache.set('map:' + str(map_id), result, 86400)
    return result
