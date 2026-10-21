import math
from functools import lru_cache
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from .models import Station
from .optimizer import Stop, decimal

METERS_PER_MILE = 1609.344


def haversine(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(h)))


@lru_cache(maxsize=4)
def station_index(version):
    # Spatial index is rebuilt once per dataset per worker, never per request.
    stations = list(Station.objects.filter(latitude__isnull=False, longitude__isnull=False).order_by('id'))
    return stations, STRtree([Point(s.longitude, s.latitude) for s in stations])


def candidates(route, stations, tree, corridor):
    coordinates = route['geometry']['coordinates']
    latitude = sum(c[1] for c in coordinates) / len(coordinates)
    xscale = 69.172 * max(.05, math.cos(math.radians(latitude)))
    yscale = 69.0
    line = LineString([(c[0] * xscale, c[1] * yscale) for c in coordinates]).simplify(.01)
    if line.length == 0:
        return []
    # Broad bounding box index filter, then precise local projection. This is
    # candidate discovery only; final feasibility uses routed road distances.
    geographic = LineString(coordinates).simplify(.0001)
    bounds = geographic.buffer(corridor / min(xscale, yscale))
    result = {}
    distance = route['distance'] / METERS_PER_MILE
    for index in tree.query(bounds, predicate='intersects'):
        station = stations[int(index)]
        point = Point(station.longitude*xscale, station.latitude*yscale)
        if line.distance(point) > corridor:
            continue
        mile = decimal(line.project(point) / line.length * distance)
        if mile >= decimal(distance):
            continue
        stop = Stop(mile, station.price, station)
        # Co-located stations: retain the cheapest, with deterministic ID ties.
        key = round(float(mile), 6)
        if key not in result or (stop.price, station.external_id) < (result[key].price, result[key].station.external_id):
            result[key] = stop
    return sorted(result.values(), key=lambda s: (s.miles, s.price, s.station.external_id))
