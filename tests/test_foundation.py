from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ambulance_dispatch.config import ScenarioConfig, severity_mix
from ambulance_dispatch.demand import build_rate_schedule, generate_incident_tape
from ambulance_dispatch.graph import City


class CityTests(unittest.TestCase):
    def test_grid_shortest_paths_and_coverage(self) -> None:
        city = City.grid(3, 3, 2.0)
        self.assertEqual(city.travel(0, 8), 8.0)
        self.assertEqual(city.travel(8, 0), 8.0)
        self.assertTrue(city.covered([4], 0, 4.0))
        self.assertFalse(city.covered([0], 8, 4.0))

    def test_weighted_coverage(self) -> None:
        city = City.grid(2, 2, 1.0)
        self.assertAlmostEqual(city.coverage_fraction([0], [1.0, 1.0, 1.0, 1.0], 1.0), 0.75)


class DemandTests(unittest.TestCase):
    def test_rates_preserve_total_and_shift_at_midpoint(self) -> None:
        uniform = build_rate_schedule(9, 120.0, 4.5, "uniform")
        fixed = build_rate_schedule(9, 120.0, 4.5, "hotspots")
        shifting = build_rate_schedule(9, 120.0, 4.5, "shifting")
        self.assertAlmostEqual(sum(uniform[0].rates_per_hour), 4.5)
        self.assertAlmostEqual(sum(fixed[0].rates_per_hour), 4.5)
        self.assertAlmostEqual(sum(shifting[0].rates_per_hour), 4.5)
        self.assertAlmostEqual(sum(shifting[1].rates_per_hour), 4.5)
        self.assertEqual(shifting[0].end_minute, 60.0)
        self.assertNotEqual(shifting[0].rates_per_hour, shifting[1].rates_per_hour)

    def test_incident_tape_is_seed_reproducible_and_bounded(self) -> None:
        schedule = build_rate_schedule(4, 600.0, 8.0, "shifting")
        probabilities = severity_mix("balanced")
        first = generate_incident_tape(schedule, probabilities, 42)
        second = generate_incident_tape(schedule, probabilities, 42)
        self.assertEqual(first, second)
        self.assertTrue(all(0 < incident.arrival_minute < 600 for incident in first))
        self.assertTrue(all(0 <= incident.zone < 4 for incident in first))
        self.assertTrue(all(1 <= incident.criticality <= 5 for incident in first))

    def test_invalid_config_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ScenarioConfig(severity_probabilities=(0.2, 0.2, 0.2, 0.2, 0.3))


if __name__ == "__main__":
    unittest.main()
