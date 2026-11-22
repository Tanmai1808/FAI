from __future__ import annotations

import pathlib
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ambulance_dispatch.config import ScenarioConfig, severity_mix
from ambulance_dispatch.demand import DemandTape
from ambulance_dispatch.model import Incident, RateInterval
from ambulance_dispatch.simulator import IncidentState, RunSettings, Simulator, simulate


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

    def test_pending_incidents_reevaluated_on_ambulance_free(self) -> None:
        config = ScenarioConfig(
            width=2,
            height=2,
            edge_minutes=2.0,
            n_ambulances=1,
            horizon_minutes=60.0,
            deadlines_minutes=(60.0, 60.0, 60.0, 60.0, 60.0),
        )
        tape = fixed_tape(
            60.0,
            (Incident(0, 0.0, 0, 1), Incident(1, 5.0, 0, 1)),
        )
        sim = Simulator(config, RunSettings("B1", "full", seed=1), tape)
        sim.run()
        # Incident 1 arrived at t=5.0 while ambulance was busy; ambulance freed at t=24.0
        # (travel 2 + scene 20 + return 2) and immediately re-evaluated pending incidents
        # to dispatch to Incident 1 at t=24.0, reaching the scene at t=26.0.
        self.assertEqual(sim.states[1].response_minute, 26.0)

    def test_b2q_priority_serves_higher_criticality_first(self) -> None:
        config = ScenarioConfig(
            width=2,
            height=2,
            edge_minutes=2.0,
            n_ambulances=1,
            horizon_minutes=60.0,
            deadlines_minutes=(60.0, 60.0, 60.0, 60.0, 60.0),
        )
        tape = fixed_tape(
            60.0,
            (Incident(0, 0.0, 0, 1), Incident(1, 2.0, 0, 1), Incident(2, 4.0, 0, 5)),
        )
        sim_b1 = Simulator(config, RunSettings("B1", "full", seed=10), tape)
        sim_b1.run()
        self.assertIsNotNone(sim_b1.states[1].response_minute)
        self.assertIsNotNone(sim_b1.states[2].response_minute)
        self.assertLess(sim_b1.states[1].response_minute, sim_b1.states[2].response_minute)

        sim_b2q = Simulator(config, RunSettings("B2q", "full", seed=10), tape)
        sim_b2q.run()
        self.assertIsNotNone(sim_b2q.states[1].response_minute)
        self.assertIsNotNone(sim_b2q.states[2].response_minute)
        self.assertLess(sim_b2q.states[2].response_minute, sim_b2q.states[1].response_minute)

    def test_b1_and_b2_remain_identical(self) -> None:
        config = ScenarioConfig(width=3, height=3, n_ambulances=3, horizon_minutes=180.0, total_rate_per_hour=3.0)
        res_b1 = simulate(config, RunSettings("B1", "full", seed=777))
        res_b2 = simulate(config, RunSettings("B2", "full", seed=777))
        self.assertEqual(replace(res_b1, policy=""), replace(res_b2, policy=""))

    def test_cost_decomposition_invariants(self) -> None:
        config = ScenarioConfig(width=3, height=3, n_ambulances=3, horizon_minutes=180.0, total_rate_per_hour=3.0)
        for policy in ("B1", "B2", "B2q", "B3", "BID"):
            result = simulate(config, RunSettings(policy, "full", seed=888))
            self.assertAlmostEqual(
                result.dispatch_cost,
                result.response_cost + result.external_coverage_cost + result.home_demand_cost,
                places=9,
            )
            self.assertAlmostEqual(
                result.total_cost,
                result.dispatch_cost + result.expiration_cost,
                places=9,
            )

    def test_b3_override_components_equal_snapshot_values(self) -> None:
        config = ScenarioConfig(width=2, height=2, n_ambulances=2, horizon_minutes=60.0)
        tape = fixed_tape(
            60.0,
            (Incident(0, 0.0, 1, 1), Incident(1, 0.0, 2, 2)),
        )
        sim = Simulator(config, RunSettings("B3", "full", seed=99), tape)
        result = sim.run()
        self.assertAlmostEqual(
            result.dispatch_cost,
            result.response_cost + result.external_coverage_cost + result.home_demand_cost,
            places=9,
        )

    def test_regression_pre_refactor_costs_numerically_identical(self) -> None:
        config = ScenarioConfig(horizon_minutes=600.0)
        expected = {
            (1000, "B1"): 885.5688738262,
            (1000, "B2"): 885.5688738262,
            (1000, "B3"): 824.8964195960,
            (1000, "BID"): 862.0294124580,
            (1001, "B1"): 762.0563727609,
            (1001, "B2"): 762.0563727609,
            (1001, "B3"): 575.0491543168,
            (1001, "BID"): 683.7554525275,
        }
        for (seed, policy), expected_total in expected.items():
            result = simulate(config, RunSettings(policy=policy, seed=seed))
            self.assertAlmostEqual(
                result.total_cost,
                expected_total,
                places=9,
                msg=f"Regression mismatch for seed={seed} policy={policy}",
            )


if __name__ == "__main__":
    unittest.main()
