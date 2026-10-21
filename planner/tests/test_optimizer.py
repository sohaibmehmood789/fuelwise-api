import random
from decimal import Decimal
from unittest import TestCase
from planner.errors import PlanningError
from planner.optimizer import Stop, decimal, optimize


class OptimizerTests(TestCase):
    def test_waits_for_cheaper_fuel_and_buys_only_what_is_needed(self):
        stops = [Stop(decimal(300), decimal(4), 'a'), Stop(decimal(700), decimal(2), 'b')]
        purchases, cost, remaining = optimize(stops, 1200)
        self.assertEqual([p['gallons'] for p in purchases], [Decimal(20), Decimal(50)])
        self.assertEqual(cost, Decimal(180))
        self.assertEqual(remaining, 0)

    def test_short_trip_consumes_starting_fuel_without_purchases(self):
        purchases, cost, remaining = optimize([], 100)
        self.assertEqual((purchases, cost, remaining), ([], 0, 40))

    def test_exact_range_and_unreachable_gap(self):
        self.assertEqual(optimize([], 500)[2], 0)
        with self.assertRaises(PlanningError):
            optimize([], 500.01)
        with self.assertRaises(PlanningError):
            optimize([Stop(decimal(501), decimal(1), 'a')], 600)

    def test_empty_start_at_station(self):
        purchases, cost, remaining = optimize([Stop(decimal(0), decimal('3.50'), 'origin')], 250, 0)
        self.assertEqual(purchases[0]['gallons'], 25)
        self.assertEqual((cost, remaining), (Decimal('87.50'), 0))

    def test_matches_independent_exhaustive_dynamic_program(self):
        # Integer demand and prices have an integer optimum. Exhaust every
        # feasible tank state/purchase, independently of the greedy strategy.
        randomizer = random.Random(20261021)
        for case in range(120):
            demands = [randomizer.randint(1, 55) for _ in range(randomizer.randint(2, 8))]
            prices = [randomizer.randint(1, 8) for _ in demands[:-1]]
            initial = randomizer.randint(0, 50)
            states = {initial: 0}
            position, stops = 0, []
            for i, demand in enumerate(demands):
                states = {fuel-demand: cost for fuel, cost in states.items() if fuel >= demand}
                position += demand * 10
                if i < len(prices):
                    stops.append(Stop(decimal(position), decimal(prices[i]), i))
                    next_states = {}
                    for fuel, cost in states.items():
                        for target in range(fuel, 51):
                            candidate = cost + (target-fuel)*prices[i]
                            next_states[target] = min(next_states.get(target, float('inf')), candidate)
                    states = next_states
            with self.subTest(case=case):
                if not states:
                    with self.assertRaises(PlanningError):
                        optimize(stops, position, initial)
                else:
                    purchases, cost, remaining = optimize(stops, position, initial)
                    self.assertEqual(cost, min(states.values()))
                    self.assertEqual(decimal(initial) + sum(p['gallons'] for p in purchases) - decimal(position)/10, remaining)
                    self.assertTrue(all(0 <= p['arrival_fuel'] <= p['departure_fuel'] <= 50 for p in purchases))
