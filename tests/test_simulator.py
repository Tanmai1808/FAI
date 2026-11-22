from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ambulance_dispatch.config import ScenarioConfig, severity_mix
from ambulance_dispatch.demand import DemandTape
from ambulance_dispatch.model import Incident, RateInterval
from ambulance_dispatch.simulator import RunSettings, simulate


def fixed_tape(horizon: float, incidents: tuple[Incident, ...]) -> DemandTape:
    return DemandTape(
        incidents,
        (RateInterval(0.0, horizon, (0.25, 0.25, 0.25, 0.25)),),
    )


class SimulatorTests(unittest.TestCase):
    def test_full_communication_selects_one_responder(self) -> None:
        config = ScenarioConfig(
            width=2,
            height=2,
            edge_minutes=2.0,
            n_ambulances=2,
            horizon_minutes=60.0,
            severity_probabilities=severity_mix("balanced"),
        )
        tape = fixed_tape(60.0, (Incident(0, 0.0, 1, 1),))
        result = simulate(config, RunSettings("BID", "full", seed=7), tape)
        self.assertEqual(result.n_incidents, 1)
        self.assertEqual(result.served, 1)
        self.assertEqual(result.total_responder_commitments, 1)
        self.assertEqual(result.duplicate_incidents, 0)
        self.assertAlmostEqual(result.mean_response_minutes, 2.0)

    def test_no_communication_creates_duplicate_commitments(self) -> None:
        config = ScenarioConfig(
            width=2,
            height=2,
            edge_minutes=2.0,
            n_ambulances=2,
            horizon_minutes=60.0,
            severity_probabilities=severity_mix("balanced"),
        )
        tape = fixed_tape(60.0, (Incident(0, 0.0, 1, 1),))
        result = simulate(config, RunSettings("BID", "none", seed=7), tape)
        self.assertEqual(result.served, 1)
        self.assertEqual(result.total_responder_commitments, 2)
        self.assertEqual(result.duplicate_incidents, 1)
        self.assertEqual(result.messages_sent, 0)

    def test_radius_and_complete_loss_can_create_multiple_local_winners(self) -> None:
        config = ScenarioConfig(
            width=3,
            height=2,
            edge_minutes=2.0,
            n_ambulances=3,
            horizon_minutes=60.0,
            severity_probabilities=severity_mix("balanced"),
        )
        tape = DemandTape(
            (Incident(0, 0.0, 2, 1),),
            (RateInterval(0.0, 60.0, (0.25,) * 6),),
        )
        radius = simulate(
            config,
            RunSettings("BID", "radius-limited", communication_radius_minutes=1.0, seed=13),
            tape,
        )
        lossy = simulate(
            config,
            RunSettings("BID", "lossy", packet_loss_probability=1.0, seed=13),
            tape,
        )
        self.assertEqual(radius.duplicate_incidents, 1)
        self.assertEqual(radius.total_responder_commitments, 3)
        self.assertEqual(lossy.duplicate_incidents, 1)
        self.assertEqual(lossy.total_responder_commitments, 3)
        self.assertGreater(lossy.messages_sent, 0)
        self.assertEqual(lossy.messages_delivered, 0)

    def test_infeasible_call_expires_once(self) -> None:
        config = ScenarioConfig(
            width=2,
            height=2,
            edge_minutes=2.0,
            n_ambulances=1,
            horizon_minutes=10.0,
            deadlines_minutes=(60.0, 45.0, 30.0, 20.0, 1.0),
            severity_probabilities=severity_mix("balanced"),
        )
        tape = fixed_tape(10.0, (Incident(0, 0.0, 0, 5),))
        result = simulate(config, RunSettings("B1", "full", seed=9), tape)
        self.assertEqual(result.served, 0)
        self.assertEqual(result.expired, 1)
        self.assertEqual(result.total_responder_commitments, 0)
        self.assertGreater(result.expiration_cost, 0)

    def test_busy_round_trip_causes_queued_call_wait(self) -> None:
        config = ScenarioConfig(
            width=2,
            height=2,
            edge_minutes=2.0,
            n_ambulances=1,
            horizon_minutes=60.0,
            severity_probabilities=severity_mix("balanced"),
        )
        tape = fixed_tape(
            60.0,
            (Incident(0, 0.0, 0, 1), Incident(1, 1.0, 0, 1)),
        )
        result = simulate(config, RunSettings("B1", "full", seed=11), tape)
        self.assertEqual(result.served, 2)
        self.assertEqual(result.total_responder_commitments, 2)
        self.assertAlmostEqual(result.mean_response_minutes, (2.0 + 25.0) / 2.0)

    def test_seeded_generated_run_is_deterministic(self) -> None:
        config = ScenarioConfig(width=3, height=3, n_ambulances=3, horizon_minutes=180.0, total_rate_per_hour=3.0)
        settings = RunSettings("B2", "full", seed=1234)
        self.assertEqual(simulate(config, settings), simulate(config, settings))

    def test_restricted_unilateral_time_only_deviation_is_reproducible(self) -> None:
        config = ScenarioConfig(width=3, height=3, n_ambulances=3, horizon_minutes=120.0, total_rate_per_hour=4.0)
        baseline = RunSettings("BID", "full", seed=41)
        deviation = RunSettings("BID", "full", seed=41, deviator_id=1, deviation_rule="nearest")
        self.assertEqual(simulate(config, deviation), simulate(config, deviation))
        self.assertEqual(simulate(config, baseline).n_incidents, simulate(config, deviation).n_incidents)


if __name__ == "__main__":
    unittest.main()
