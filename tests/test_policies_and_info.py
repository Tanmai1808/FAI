from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ambulance_dispatch.communication import CommunicationChannel
from ambulance_dispatch.config import ScenarioConfig, Weights
from ambulance_dispatch.graph import City
from ambulance_dispatch.learning import DiscountedRateLearner, assign_zone_observers
from ambulance_dispatch.model import Ambulance, AmbulanceStatus, Incident
from ambulance_dispatch.policies.baselines import select_b1, select_b2
from ambulance_dispatch.policies.bidding import Bid, compute_bid, local_minimum_winners
from ambulance_dispatch.policies.centralized import assign_b3, hungarian_min_cost
from ambulance_dispatch.policies.costs import marginal_coverage_cost


class CommunicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.city = City.grid(3, 1, 1.0)
        self.positions = {0: 0, 1: 1, 2: 2}

    def test_full_delivers_and_none_sends_nothing(self) -> None:
        full = CommunicationChannel(self.city, "full", seed=1)
        none = CommunicationChannel(self.city, "none", seed=1)
        self.assertEqual(len(full.broadcast(0, self.positions, (0, 1, 2), "bid", {}, 0)), 2)
        self.assertEqual(none.broadcast(0, self.positions, (0, 1, 2), "bid", {}, 0), ())
        self.assertEqual(none.messages_sent, 0)

    def test_radius_and_loss_are_directed_packet_rules(self) -> None:
        radius = CommunicationChannel(self.city, "radius-limited", radius_minutes=1.0, seed=3)
        got = radius.broadcast(0, self.positions, (0, 1, 2), "status", {}, 0)
        self.assertEqual(tuple(m.receiver for m in got), (1,))
        lossy = CommunicationChannel(self.city, "lossy", loss_probability=1.0, seed=3)
        self.assertEqual(lossy.broadcast(0, self.positions, (1, 2), "bid", {}, 0), ())
        self.assertEqual(lossy.messages_sent, 2)
        self.assertEqual(lossy.messages_delivered, 0)


class LearningTests(unittest.TestCase):
    def test_owner_partition_and_discounted_update(self) -> None:
        city = City.grid(3, 1, 1.0)
        owners = assign_zone_observers(city, {0: 0, 1: 2})
        self.assertEqual(owners[0], 0)
        self.assertEqual(owners[2], 1)
        learner = DiscountedRateLearner(0, 2, (0,), prior_per_hour=1.0, eta=0.5, bin_minutes=60.0)
        learner.observe_arrival(1, 5.0)  # outside this agent's private partition
        learner.observe_arrival(0, 6.0)
        updates = learner.close_bin(0)
        self.assertEqual(updates, ((0, 1.0),))
        self.assertEqual(learner.rates, [1.0, 1.0])

    def test_remote_rate_is_installed_once_and_rmse_is_defined(self) -> None:
        learner = DiscountedRateLearner(0, 2, (), prior_per_hour=1.0, eta=0.5, bin_minutes=60.0)
        self.assertTrue(learner.receive_rate(1, 1, 2, 4.0))
        self.assertFalse(learner.receive_rate(1, 1, 2, 4.0))
        self.assertFalse(learner.receive_rate(1, 1, 1, 3.0))
        self.assertAlmostEqual(learner.rmse([1.0, 2.0]), (2.0**2 / 2) ** 0.5)


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.city = City.grid(3, 3, 2.0)
        self.incident = Incident(0, 10.0, 4, 3)
        self.ambulances = [Ambulance(0, 0, 0), Ambulance(1, 8, 8)]

    def test_baseline_order_and_bid_feasibility(self) -> None:
        self.assertEqual(select_b1(self.city, self.incident, self.ambulances).ambulance_id, 0)
        self.assertEqual(select_b2(self.city, self.incident, self.ambulances, alpha=0.1).ambulance_id, 0)
        bid = compute_bid(
            self.city,
            self.ambulances[0],
            self.incident,
            10.0,
            30.0,
            20.0,
            Weights(),
            {0: 0, 1: 8},
            [0.5] * 9,
            2.0,
        )
        self.assertIsNotNone(bid)
        self.assertIsNone(compute_bid(
            self.city, self.ambulances[0], self.incident, 10.0, 1.0, 20.0,
            Weights(), {0: 0}, [0.5] * 9, 2.0,
        ))

    def test_local_minimum_has_one_full_winner_but_multiple_no_message_winners(self) -> None:
        bids = {0: Bid(0, 1.0, 0), 1: Bid(1, 2.0, 1), 2: Bid(2, 3.0, 2)}
        full = {i: tuple(b for j, b in bids.items() if j != i) for i in bids}
        none = {i: () for i in bids}
        self.assertEqual(local_minimum_winners(bids, full), (0,))
        self.assertEqual(local_minimum_winners(bids, none), (0, 1, 2))
        split = {0: (bids[1],), 1: (bids[0],), 2: ()}
        self.assertEqual(local_minimum_winners(bids, split), (0, 2))

    def test_hungarian_and_b3_assignment(self) -> None:
        assignment = hungarian_min_cost([[4, 1], [2, 3]])
        self.assertEqual(assignment, ((0, 1), (1, 0)))
        self.assertEqual(assign_b3([[1.0, 8.0], [7.0, 2.0]], 10.0), ((0, 0), (1, 1)))
        self.assertEqual(assign_b3([[50.0]], 10.0), ())

    def test_home_demand_term_is_unconditional_and_disjoint_from_coverage_loss(self) -> None:
        city = City.grid(2, 1, 1.0)
        marginal = marginal_coverage_cost(
            city,
            agent_id=0,
            home_zone=0,
            own_node=0,
            believed_idle_positions={0: 0, 1: 1},
            rates_per_hour=[2.0, 3.0],
            busy_minutes=30.0,
            coverage_radius_minutes=1.0,
        )
        # The other ambulance still covers the home node; D nevertheless prices
        # demand during this unit's absence, while outside-home R sees no lost cover.
        self.assertEqual(marginal.outside_home_expected_calls, 0.0)
        self.assertEqual(marginal.home_expected_calls, 1.0)


if __name__ == "__main__":
    unittest.main()
