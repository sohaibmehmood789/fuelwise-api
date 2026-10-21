"""Exact minimum fuel purchase cost on a fixed ordered route, O(n).

The next cheaper station is computed with a monotonic stack. At each station,
buy enough to reach the first cheaper station within range; otherwise fill to
capacity or to the destination. A cheaper later purchase dominates buying now.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from .errors import PlanningError

MPG = Decimal('10')
CAPACITY = Decimal('50')
EPSILON = Decimal('0.00000001')


def decimal(value):
    return Decimal(str(value))


def money(value):
    return str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Stop:
    miles: Decimal
    price: Decimal
    station: object


def optimize(stops, distance, initial_fuel=CAPACITY):
    distance, fuel = decimal(distance), decimal(initial_fuel)
    if distance < 0 or not 0 <= fuel <= CAPACITY:
        raise ValueError('Invalid distance or initial fuel')
    if any(s.miles < 0 or s.miles > distance or s.price <= 0 for s in stops):
        raise ValueError('Invalid station')
    if any(a.miles > b.miles for a, b in zip(stops, stops[1:])):
        raise ValueError('Stations must be ordered')
    next_cheaper = [None] * len(stops)
    stack = []
    for i in range(len(stops)-1, -1, -1):
        while stack and stops[stack[-1]].price >= stops[i].price:
            stack.pop()
        next_cheaper[i] = stack[-1] if stack else None
        stack.append(i)
    purchases, previous, total = [], Decimal(0), Decimal(0)
    for i, stop in enumerate(stops):
        fuel -= (stop.miles - previous) / MPG
        if fuel < -EPSILON:
            raise PlanningError('insufficient_station_coverage', f'Cannot reach a fuel station near mile {stop.miles:.1f} with the available fuel.')
        fuel = max(fuel, Decimal(0))
        target = min(CAPACITY, (distance - stop.miles) / MPG)
        j = next_cheaper[i]
        if j is not None and stops[j].miles - stop.miles <= CAPACITY * MPG:
            target = min(target, (stops[j].miles - stop.miles) / MPG)
        gallons = max(Decimal(0), target - fuel)
        if gallons > EPSILON:
            cost = gallons * stop.price
            purchases.append({'stop': stop, 'gallons': gallons, 'cost': cost, 'arrival_fuel': fuel, 'departure_fuel': fuel + gallons})
            total += cost
            fuel += gallons
        previous = stop.miles
    fuel -= (distance - previous) / MPG
    if fuel < -EPSILON:
        raise PlanningError('insufficient_station_coverage', 'The final leg exceeds the available fuel. Add more stations or widen the corridor.')
    return purchases, total, max(fuel, Decimal(0))
