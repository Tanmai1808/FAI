"""Deterministic event-driven ambulance-dispatch simulation."""

from __future__ import annotations

import heapq
import itertools
from collections import Counter
from dataclasses import asdict, dataclass, field
from math import inf
from typing import Any

from .communication import CommunicationChannel
from .config import ScenarioConfig
from .demand import DemandTape, build_rate_schedule, generate_incident_tape
from .graph import City
from .learning import DiscountedRateLearner, initialize_learners
from .model import Ambulance, AmbulanceStatus, Incident, RateInterval
from .policies.baselines import feasible_ambulances, select_b1, select_b2
from .policies.bidding import Bid, compute_bid, local_minimum_winners
from .policies.centralized import assign_b3
from .policies.costs import CostBreakdown, marginal_coverage_cost, weighted_dispatch_cost


BASE_POLICIES = ("B1", "B2", "B3", "BID")
POLICIES = ("B1", "B2", "B3", "BID", "B2q")
COMMUNICATION_REGIMES = ("full", "radius-limited", "lossy", "none")


@dataclass(frozen=True)
class RunSettings:
    policy: str = "BID"
    communication: str = "full"
    communication_radius_minutes: float = 12.0
    packet_loss_probability: float = 0.25
    oracle_demand: bool = False
    seed: int = 0
    scenario_id: str = "default"
    deviator_id: int | None = None
    deviation_rule: str | None = None

    def __post_init__(self) -> None:
        if self.policy not in POLICIES:
            raise ValueError(f"unknown policy: {self.policy}")
        if self.communication not in COMMUNICATION_REGIMES:
            raise ValueError(f"unknown communication regime: {self.communication}")
        if not 0 <= self.packet_loss_probability <= 1:
            raise ValueError("packet loss probability must be in [0, 1]")
        if self.deviation_rule not in {None, "nearest"}:
            raise ValueError("the implemented unilateral deviation is 'nearest' or None")
        if (self.deviator_id is None) != (self.deviation_rule is None):
            raise ValueError("deviator_id and deviation_rule must be set together")


@dataclass
class IncidentState:
    incident: Incident
    deadline_minute: float
    responders: list[int] = field(default_factory=list)
    response_minute: float | None = None
    resolved: bool = False
    missed: bool = False
    allocated: bool = False


@dataclass(frozen=True)
class RunResult:
    policy: str
    communication: str
    demand_knowledge: str
    scenario_id: str
    seed: int
    n_ambulances: int
    n_incidents: int
    served: int
    expired: int
    duplicate_incidents: int
    total_responder_commitments: int
    service_rate: float
    mean_response_minutes: float
    critical_mean_response_minutes: float
    mean_coverage: float
    utilization: float
    busy_ambulance_minutes: float
    messages_sent: int
    messages_delivered: int
    messages_per_incident: float
    demand_rmse: float
    response_cost: float
    external_coverage_cost: float
    home_demand_cost: float
    dispatch_cost: float
    expiration_cost: float
    total_cost: float
    arrival_horizon_minutes: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _initial_nodes(n_nodes: int, n_ambulances: int) -> tuple[int, ...]:
    if n_nodes < 1 or n_ambulances < 1:
        raise ValueError("node and ambulance counts must be positive")
    if n_ambulances == 1:
        return (n_nodes // 2,)
    return tuple(round(i * (n_nodes - 1) / (n_ambulances - 1)) for i in range(n_ambulances))


def _incident_priority(state: IncidentState, policy: str = "B1") -> tuple[float | int, float | int, int]:
    if policy == "B2q":
        return (-state.incident.criticality, state.incident.arrival_minute, state.incident.incident_id)
    return state.incident.arrival_minute, -state.incident.criticality, state.incident.incident_id


class Simulator:
    """One matched scenario and policy rollout with explicit local information."""

    def __init__(
        self,
        config: ScenarioConfig,
        settings: RunSettings,
        tape_override: DemandTape | None = None,
    ) -> None:
        self.config = config
        self.settings = settings
        self.city = City.grid(config.width, config.height, config.edge_minutes)
        self.tape = tape_override or self._make_tape()
        if any(incident.arrival_minute > config.horizon_minutes for incident in self.tape.incidents):
            raise ValueError("incident tape contains an arrival beyond the configured horizon")
        if any(len(interval.rates_per_hour) != config.n_zones for interval in self.tape.rate_schedule):
            raise ValueError("incident tape rate schedule does not match the city zone count")
        self.ambulances = self._make_ambulances()
        self.learners, self.zone_owners = initialize_learners(
            self.ambulances,
            self.city,
            config.n_zones,
            config.prior_total_rate_per_hour,
            config.learning_eta,
            config.learning_bin_minutes,
        )
        self.channel = CommunicationChannel(
            self.city,
            settings.communication,
            settings.communication_radius_minutes,
            settings.packet_loss_probability,
            self._child_seed(settings.seed, 1),
        )
        self.beliefs: dict[int, dict[int, tuple[int, AmbulanceStatus, float, float]]] = {
            ambulance.ambulance_id: {
                other.ambulance_id: (other.node, other.status, other.free_at, 0.0)
                for other in self.ambulances
            }
            for ambulance in self.ambulances
        }
        self.states: dict[int, IncidentState] = {}
        self.pending: set[int] = set()
        self.event_queue: list[tuple[float, int, int, str, Any]] = []
        self._event_sequence = itertools.count()
        self._schedule_initial_events()
        self.now = 0.0
        self.last_metric_time = 0.0
        self.coverage_integral = 0.0
        self.busy_minutes = 0.0
        self.response_times: list[tuple[int, float]] = []
        self.duplicate_incident_ids: set[int] = set()
        self.total_responder_commitments = 0
        self.response_cost = 0.0
        self.external_coverage_cost = 0.0
        self.home_demand_cost = 0.0
        self.dispatch_cost = 0.0
        self.expiration_cost = 0.0
        self.rmse_samples: list[float] = []
        self.message_totals_by_type: Counter[str] = Counter()

    @staticmethod
    def _child_seed(seed: int, stream_id: int) -> int:
        # Stable, documented integer mixing without Python's randomized hash().
        return (seed * 1_000_003 + stream_id * 97_409 + 0x9E3779B9) % (2**32)

    def _make_tape(self) -> DemandTape:
        rates = build_rate_schedule(
            self.config.n_zones,
            self.config.horizon_minutes,
            self.config.total_rate_per_hour,
            self.config.demand_pattern,
        )
        incidents = generate_incident_tape(rates, self.config.severity_probabilities, self.settings.seed)
        return DemandTape(incidents, rates)

    def _make_ambulances(self) -> list[Ambulance]:
        nodes = _initial_nodes(self.config.n_zones, self.config.n_ambulances)
        return [Ambulance(i, node, node) for i, node in enumerate(nodes)]

    def _schedule(self, time_minute: float, priority: int, kind: str, payload: Any) -> None:
        heapq.heappush(
            self.event_queue,
            (time_minute, priority, next(self._event_sequence), kind, payload),
        )

    def _schedule_initial_events(self) -> None:
        for incident in self.tape.incidents:
            deadline = self.config.deadline_for(incident.criticality)
            self._schedule(incident.arrival_minute, 4, "arrival", incident)
            self._schedule(incident.arrival_minute + deadline, 3, "deadline", incident.incident_id)
        self._schedule(self.config.horizon_minutes, 5, "arrival_horizon_end", None)
        bin_step = self.config.learning_bin_minutes
        bin_id = 1
        boundary = bin_step
        while boundary < self.config.horizon_minutes:
            self._schedule(boundary, 2, "learning_bin", bin_id)
            bin_id += 1
            boundary += bin_step

    def _advance_metrics(self, end_minute: float) -> None:
        start = self.last_metric_time
        metric_end = min(end_minute, self.config.horizon_minutes)
        if metric_end > start:
            busy_count = sum(a.status != AmbulanceStatus.IDLE for a in self.ambulances)
            self.busy_minutes += busy_count * (metric_end - start)
            idle_positions = [a.node for a in self.ambulances if a.status == AmbulanceStatus.IDLE]
            for interval in self.tape.rate_schedule:
                left = max(start, interval.start_minute)
                right = min(metric_end, interval.end_minute)
                if right > left:
                    coverage = self.city.coverage_fraction(
                        idle_positions,
                        interval.rates_per_hour,
                        self.config.coverage_radius_minutes,
                    )
                    self.coverage_integral += (right - left) * coverage
        self.last_metric_time = end_minute

    def _true_rates(self, time_minute: float | None = None) -> tuple[float, ...]:
        at = self.now if time_minute is None else time_minute
        if at >= self.config.horizon_minutes:
            at = max(0.0, self.config.horizon_minutes - 1e-9)
        return self.tape.true_rates_at(at)

    def _belief_positions(self, agent_id: int) -> dict[int, int]:
        positions: dict[int, int] = {}
        for other_id, (node, status, _free_at, observed_at) in self.beliefs[agent_id].items():
            if other_id == agent_id:
                own = self.ambulances[agent_id]
                if own.status == AmbulanceStatus.IDLE:
                    positions[agent_id] = own.node
                continue
            if self.now - observed_at > self.config.status_ttl_minutes:
                continue
            if status == AmbulanceStatus.IDLE:
                positions[other_id] = node
        own = self.ambulances[agent_id]
        if own.status == AmbulanceStatus.IDLE:
            positions[agent_id] = own.node
        return positions

    def _update_belief(self, receiver: int, sender: int, payload: dict[str, Any], sent_at: float) -> None:
        try:
            status = AmbulanceStatus(payload["status"])
            node = int(payload["node"])
            free_at = float(payload["free_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("malformed ambulance state message") from exc
        self.beliefs[receiver][sender] = (node, status, free_at, sent_at)

    def _broadcast_state(self, ambulance: Ambulance) -> None:
        if self.settings.policy != "BID":
            return
        positions = {a.ambulance_id: a.node for a in self.ambulances}
        payload = {
            "node": ambulance.node,
            "status": ambulance.status.value,
            "free_at": ambulance.free_at,
            "target_node": ambulance.target_node,
        }
        messages = self.channel.broadcast(
            ambulance.ambulance_id,
            positions,
            tuple(positions),
            "status",
            payload,
            self.now,
        )
        for message in messages:
            self._update_belief(message.receiver, message.sender, message.payload, message.sent_at)

    def _handle_arrival(self, incident: Incident) -> None:
        state = IncidentState(
            incident,
            incident.arrival_minute + self.config.deadline_for(incident.criticality),
        )
        self.states[incident.incident_id] = state
        self.pending.add(incident.incident_id)
        owner = self.zone_owners[incident.zone]
        self.learners[owner].observe_arrival(incident.zone, incident.arrival_minute)

    def _handle_deadline(self, incident_id: int) -> None:
        state = self.states.get(incident_id)
        if state is not None and not state.resolved:
            state.resolved = True
            state.missed = True
            self.pending.discard(incident_id)
            self.expiration_cost += self.config.weights.rho

    def _handle_learning_bin(self, bin_id: int) -> None:
        true_rates = self._true_rates(self.now - 1e-9)
        updates_by_owner: list[tuple[int, int, float]] = []
        for owner, learner in sorted(self.learners.items()):
            for zone, rate in learner.close_bin(bin_id):
                updates_by_owner.append((owner, zone, rate))
        if self.settings.policy == "BID":
            positions = {a.ambulance_id: a.node for a in self.ambulances}
            for owner, zone, rate in updates_by_owner:
                payload = {"zone": zone, "bin_id": bin_id, "rate": rate}
                for receiver in sorted(self.learners):
                    if receiver == owner:
                        continue
                    message = self.channel.send(
                        owner,
                        receiver,
                        positions[owner],
                        positions[receiver],
                        "rate",
                        payload,
                        self.now,
                    )
                    if message is not None:
                        self.learners[receiver].receive_rate(owner, zone, bin_id, rate)
        if self.settings.oracle_demand:
            self.rmse_samples.append(0.0)
        else:
            errors = [learner.rmse(true_rates) for learner in self.learners.values()]
            self.rmse_samples.append(sum(errors) / len(errors))

    def _rates_for_agent(self, agent_id: int) -> tuple[float, ...]:
        if self.settings.oracle_demand:
            return self._true_rates()
        return tuple(self.learners[agent_id].rates)

    def _record_sent_message_types(self) -> None:
        self.message_totals_by_type = self.channel.sent_by_kind.copy()

    def _eligible(self, incident_state: IncidentState) -> tuple[Ambulance, ...]:
        return feasible_ambulances(
            self.city,
            incident_state.incident,
            self.now,
            incident_state.deadline_minute - incident_state.incident.arrival_minute,
            self.ambulances,
        )

    def _bidding_winners(self, state: IncidentState, eligible: tuple[Ambulance, ...]) -> tuple[int, ...]:
        true_oracle = self._true_rates()
        bids: dict[int, Bid] = {}
        for ambulance in eligible:
            bid = compute_bid(
                self.city,
                ambulance,
                state.incident,
                self.now,
                state.deadline_minute - state.incident.arrival_minute,
                self.config.on_scene_minutes,
                self.config.weights,
                self._belief_positions(ambulance.ambulance_id),
                true_oracle if self.settings.oracle_demand else self._rates_for_agent(ambulance.ambulance_id),
                self.config.coverage_radius_minutes,
            )
            if bid is not None:
                if ambulance.ambulance_id == self.settings.deviator_id and self.settings.deviation_rule == "nearest":
                    # A unilateral time-only/nearest bid drops coverage and demand-away terms.
                    response = self.now - state.incident.arrival_minute + self.city.travel(
                        ambulance.node, state.incident.zone
                    )
                    bid = Bid(
                        ambulance.ambulance_id,
                        self.config.weights.alpha * state.incident.criticality * response,
                        ambulance.node,
                    )
                bids[ambulance.ambulance_id] = bid
        received: dict[int, list[Bid]] = {agent_id: [] for agent_id in bids}
        positions = {a.ambulance_id: a.node for a in self.ambulances}
        for sender, bid in sorted(bids.items()):
            payload = {
                "bid": bid,
                "state": {
                    "node": self.ambulances[sender].node,
                    "status": self.ambulances[sender].status.value,
                    "free_at": self.ambulances[sender].free_at,
                },
            }
            for receiver in sorted(bids):
                if receiver == sender:
                    continue
                message = self.channel.send(
                    sender,
                    receiver,
                    positions[sender],
                    positions[receiver],
                    "bid",
                    payload,
                    self.now,
                )
                if message is not None:
                    received[receiver].append(message.payload["bid"])
                    self._update_belief(receiver, sender, message.payload["state"], message.sent_at)
        return local_minimum_winners(bids, received)

    def _dispatch_cost(
        self,
        state: IncidentState,
        ambulance: Ambulance,
        idle_positions: dict[int, int] | None = None,
        true_rates: tuple[float, ...] | None = None,
    ) -> CostBreakdown:
        travel = self.city.travel(ambulance.node, state.incident.zone)
        response = self.now - state.incident.arrival_minute + travel
        busy = 2.0 * travel + self.config.on_scene_minutes
        coverage = marginal_coverage_cost(
            self.city,
            ambulance.ambulance_id,
            ambulance.home_zone,
            ambulance.node,
            idle_positions
            if idle_positions is not None
            else {a.ambulance_id: a.node for a in self.ambulances if a.status == AmbulanceStatus.IDLE},
            true_rates if true_rates is not None else self._true_rates(),
            busy,
            self.config.coverage_radius_minutes,
        )
        return weighted_dispatch_cost(response, state.incident.criticality, coverage, self.config.weights)

    def _dispatch(
        self,
        state: IncidentState,
        responder_ids: tuple[int, ...],
        cost_overrides: dict[int, CostBreakdown] | None = None,
    ) -> None:
        if not responder_ids or state.allocated:
            return
        state.allocated = True
        state.responders.extend(responder_ids)
        self.pending.discard(state.incident.incident_id)
        self.total_responder_commitments += len(responder_ids)
        if len(responder_ids) > 1:
            self.duplicate_incident_ids.add(state.incident.incident_id)
        idle_snapshot = {a.ambulance_id: a.node for a in self.ambulances if a.status == AmbulanceStatus.IDLE}
        rates_snapshot = self._true_rates()
        precomputed_costs: dict[int, CostBreakdown] = {
            ambulance_id: (
                cost_overrides[ambulance_id]
                if cost_overrides is not None and ambulance_id in cost_overrides
                else self._dispatch_cost(state, self.ambulances[ambulance_id], idle_snapshot, rates_snapshot)
            )
            for ambulance_id in responder_ids
        }
        for ambulance_id in responder_ids:
            ambulance = self.ambulances[ambulance_id]
            if ambulance.status != AmbulanceStatus.IDLE:
                raise RuntimeError("an ambulance received duplicate commitments in one time step")
            travel = self.city.travel(ambulance.node, state.incident.zone)
            response = self.now - state.incident.arrival_minute + travel
            if response > state.deadline_minute - state.incident.arrival_minute + 1e-9:
                raise RuntimeError("policy committed an ambulance that cannot meet the deadline")
            cost = precomputed_costs[ambulance_id]
            self.response_cost += cost.response_cost
            self.external_coverage_cost += cost.external_coverage_cost
            self.home_demand_cost += cost.home_demand_cost
            self.dispatch_cost += cost.total
            origin = ambulance.node
            busy_minutes = 2.0 * travel + self.config.on_scene_minutes
            ambulance.status = AmbulanceStatus.RESPONSE_BUSY
            ambulance.free_at = self.now + busy_minutes
            ambulance.dispatch_origin = origin
            ambulance.target_node = None
            self._broadcast_state(ambulance)
            self._schedule(self.now + travel, 1, "scene_arrival", state.incident.incident_id)
            self._schedule(ambulance.free_at, 0, "trip_complete", ambulance_id)

    def _allocate_b1_b2_or_bid(self) -> None:
        while self.pending:
            states = [self.states[i] for i in self.pending if not self.states[i].resolved]
            if not states:
                return
            state = min(states, key=lambda s: _incident_priority(s, self.settings.policy))
            eligible = self._eligible(state)
            if not eligible:
                # The oldest call may wait for a trip completion; a younger call could still be feasible.
                feasible_states = []
                for candidate in states:
                    candidate_eligible = self._eligible(candidate)
                    if candidate_eligible:
                        feasible_states.append((candidate, candidate_eligible))
                if not feasible_states:
                    return
                state, eligible = min(feasible_states, key=lambda pair: _incident_priority(pair[0], self.settings.policy))
            if self.settings.policy in ("B1", "B2q"):
                winner = select_b1(self.city, state.incident, eligible)
                winners = () if winner is None else (winner.ambulance_id,)
            elif self.settings.policy == "B2":
                winner = select_b2(self.city, state.incident, eligible, self.config.weights.alpha)
                winners = () if winner is None else (winner.ambulance_id,)
            else:
                winners = self._bidding_winners(state, eligible)
            if not winners:
                return
            self._dispatch(state, winners)
            self._reposition_decentralized()

    def _b3_pairwise_cost(self, state: IncidentState, ambulance: Ambulance, idle: dict[int, int]) -> CostBreakdown | None:
        travel = self.city.travel(ambulance.node, state.incident.zone)
        response = self.now - state.incident.arrival_minute + travel
        deadline = state.deadline_minute - state.incident.arrival_minute
        if response > deadline:
            return None
        busy = 2.0 * travel + self.config.on_scene_minutes
        coverage = marginal_coverage_cost(
            self.city,
            ambulance.ambulance_id,
            ambulance.home_zone,
            ambulance.node,
            idle,
            self._true_rates(),
            busy,
            self.config.coverage_radius_minutes,
        )
        return weighted_dispatch_cost(response, state.incident.criticality, coverage, self.config.weights)

    def _allocate_b3(self) -> None:
        states = sorted(
            (self.states[i] for i in self.pending if not self.states[i].resolved),
            key=lambda s: _incident_priority(s, self.settings.policy),
        )
        idle_agents = [a for a in self.ambulances if a.status == AmbulanceStatus.IDLE]
        if not states or not idle_agents:
            return
        idle = {a.ambulance_id: a.node for a in idle_agents}
        pairwise_breakdowns = [
            [self._b3_pairwise_cost(state, ambulance, idle) for state in states]
            for ambulance in idle_agents
        ]
        costs = [
            [b.total if b is not None else inf for b in row]
            for row in pairwise_breakdowns
        ]
        pairs = assign_b3(costs, self.config.weights.rho, idle_penalty=0.0)
        dispatches: list[tuple[IncidentState, int]] = []
        cost_overrides: dict[int, CostBreakdown] = {}
        for ambulance_index, incident_index in pairs:
            ambulance_id = idle_agents[ambulance_index].ambulance_id
            state = states[incident_index]
            dispatches.append((state, ambulance_id))
            breakdown = pairwise_breakdowns[ambulance_index][incident_index]
            assert breakdown is not None
            cost_overrides[ambulance_id] = breakdown
        for state, ambulance_id in dispatches:
            self._dispatch(state, (ambulance_id,), {ambulance_id: cost_overrides[ambulance_id]})
        self._reposition_centralized()

    def _coverage_fraction_for(self, positions: list[int], rates: tuple[float, ...]) -> float:
        return self.city.coverage_fraction(positions, rates, self.config.coverage_radius_minutes)

    def _reposition_decentralized(self) -> None:
        if self.settings.policy != "BID":
            return
        idle = [a for a in self.ambulances if a.status == AmbulanceStatus.IDLE]
        decisions: list[tuple[Ambulance, int, float]] = []
        for ambulance in idle:
            known = self._belief_positions(ambulance.ambulance_id)
            other_positions = [node for other, node in known.items() if other != ambulance.ambulance_id]
            current_rates = self._rates_for_agent(ambulance.ambulance_id)
            current = self._coverage_fraction_for([*other_positions, ambulance.node], current_rates)
            choices = []
            for node in self.city.nodes:
                gain = self._coverage_fraction_for([*other_positions, node], current_rates) - current
                choices.append((gain, -node, node))
            gain, _tie, destination = max(choices)
            if destination != ambulance.node and gain > self.config.reposition_epsilon:
                decisions.append((ambulance, destination, gain))
        for ambulance, destination, _gain in decisions:
            self._start_reposition(ambulance, destination)

    def _reposition_centralized(self) -> None:
        if self.settings.policy != "B3":
            return
        remaining = [a for a in self.ambulances if a.status == AmbulanceStatus.IDLE]
        planned_positions = {a.ambulance_id: a.node for a in remaining}
        rates = self._true_rates()
        while remaining:
            all_positions = list(planned_positions.values())
            current = self._coverage_fraction_for(all_positions, rates)
            best: tuple[float, int, int, Ambulance] | None = None
            for ambulance in remaining:
                others = [node for agent, node in planned_positions.items() if agent != ambulance.ambulance_id]
                for node in self.city.nodes:
                    gain = self._coverage_fraction_for([*others, node], rates) - current
                    proposal = (gain, -node, -ambulance.ambulance_id, ambulance)
                    if best is None or proposal[:3] > best[:3]:
                        best = proposal
                        best_node = node
            if best is None or best[0] <= self.config.reposition_epsilon:
                return
            ambulance = best[3]
            destination = best_node
            planned_positions[ambulance.ambulance_id] = destination
            self._start_reposition(ambulance, destination)
            remaining.remove(ambulance)

    def _start_reposition(self, ambulance: Ambulance, destination: int) -> None:
        if ambulance.status != AmbulanceStatus.IDLE or ambulance.node == destination:
            return
        origin = ambulance.node
        travel = self.city.travel(origin, destination)
        ambulance.status = AmbulanceStatus.REPOSITION_BUSY
        ambulance.free_at = self.now + travel
        ambulance.dispatch_origin = origin
        ambulance.target_node = destination
        self._broadcast_state(ambulance)
        self._schedule(ambulance.free_at, 0, "trip_complete", ambulance.ambulance_id)

    def _handle_trip_complete(self, ambulance_id: int) -> None:
        ambulance = self.ambulances[ambulance_id]
        if ambulance.status == AmbulanceStatus.RESPONSE_BUSY:
            if ambulance.dispatch_origin is not None:
                ambulance.node = ambulance.dispatch_origin
        elif ambulance.status == AmbulanceStatus.REPOSITION_BUSY:
            if ambulance.target_node is not None:
                ambulance.node = ambulance.target_node
        ambulance.status = AmbulanceStatus.IDLE
        ambulance.free_at = self.now
        ambulance.dispatch_origin = None
        ambulance.target_node = None
        self._broadcast_state(ambulance)

    def _handle_scene_arrival(self, incident_id: int) -> None:
        state = self.states[incident_id]
        if state.response_minute is None:
            state.response_minute = self.now
            state.resolved = True
            self.response_times.append((state.incident.criticality, self.now - state.incident.arrival_minute))
            self.pending.discard(incident_id)

    def _process_event(self, kind: str, payload: Any) -> None:
        if kind == "arrival":
            self._handle_arrival(payload)
        elif kind == "deadline":
            self._handle_deadline(payload)
        elif kind == "learning_bin":
            self._handle_learning_bin(payload)
        elif kind == "scene_arrival":
            self._handle_scene_arrival(payload)
        elif kind == "trip_complete":
            self._handle_trip_complete(payload)
        elif kind == "arrival_horizon_end":
            pass
        else:
            raise ValueError(f"unknown simulator event: {kind}")

    def run(self) -> RunResult:
        if self.config.horizon_minutes <= 0:
            raise ValueError("horizon must be positive")
        while self.event_queue:
            next_time = self.event_queue[0][0]
            if next_time > self.config.horizon_minutes and not any(not s.resolved for s in self.states.values()):
                if all(a.status == AmbulanceStatus.IDLE for a in self.ambulances):
                    break
            if next_time > self.config.horizon_minutes and not any(not s.resolved for s in self.states.values()):
                # Process outstanding response return trips but stop learning after the arrival horizon.
                if self.event_queue[0][3] not in {"trip_complete"}:
                    heapq.heappop(self.event_queue)
                    continue
            self._advance_metrics(next_time)
            self.now = next_time
            batch: list[tuple[float, int, int, str, Any]] = []
            while self.event_queue and self.event_queue[0][0] == next_time:
                batch.append(heapq.heappop(self.event_queue))
            for _time, _priority, _seq, kind, payload in sorted(batch, key=lambda item: (item[1], item[2])):
                self._process_event(kind, payload)
            if self.now <= self.config.horizon_minutes:
                if self.settings.policy == "B3":
                    self._allocate_b3()
                else:
                    self._allocate_b1_b2_or_bid()
            if (
                self.now >= self.config.horizon_minutes
                and all(state.resolved for state in self.states.values())
                and all(a.status == AmbulanceStatus.IDLE for a in self.ambulances)
            ):
                break

        # Counts are tracked by the channel and already include all actual sends.
        self._record_sent_message_types()
        self._check_invariants()
        n_incidents = len(self.states)
        served = sum(state.response_minute is not None for state in self.states.values())
        expired = sum(state.missed for state in self.states.values())
        responses = [minutes for _criticality, minutes in self.response_times]
        critical = [minutes for severity, minutes in self.response_times if severity >= 4]
        return RunResult(
            policy=self.settings.policy,
            communication=self.settings.communication,
            demand_knowledge="oracle" if self.settings.oracle_demand else "learned",
            scenario_id=self.settings.scenario_id,
            seed=self.settings.seed,
            n_ambulances=self.config.n_ambulances,
            n_incidents=n_incidents,
            served=served,
            expired=expired,
            duplicate_incidents=len(self.duplicate_incident_ids),
            total_responder_commitments=self.total_responder_commitments,
            service_rate=served / n_incidents if n_incidents else 1.0,
            mean_response_minutes=sum(responses) / len(responses) if responses else 0.0,
            critical_mean_response_minutes=sum(critical) / len(critical) if critical else 0.0,
            mean_coverage=self.coverage_integral / self.config.horizon_minutes,
            utilization=self.busy_minutes / (self.config.n_ambulances * self.config.horizon_minutes),
            busy_ambulance_minutes=self.busy_minutes,
            messages_sent=self.channel.messages_sent,
            messages_delivered=self.channel.messages_delivered,
            messages_per_incident=self.channel.messages_sent / n_incidents if n_incidents else 0.0,
            demand_rmse=sum(self.rmse_samples) / len(self.rmse_samples) if self.rmse_samples else 0.0,
            response_cost=self.response_cost,
            external_coverage_cost=self.external_coverage_cost,
            home_demand_cost=self.home_demand_cost,
            dispatch_cost=self.dispatch_cost,
            expiration_cost=self.expiration_cost,
            total_cost=self.dispatch_cost + self.expiration_cost,
            arrival_horizon_minutes=self.config.horizon_minutes,
        )

    def _check_invariants(self) -> None:
        for state in self.states.values():
            if len(state.responders) > 1 and state.incident.incident_id not in self.duplicate_incident_ids:
                raise RuntimeError("duplicate responder accounting is inconsistent")
            if state.missed and state.response_minute is not None:
                raise RuntimeError("an incident cannot be both missed and served")
        for ambulance in self.ambulances:
            if ambulance.status == AmbulanceStatus.IDLE and ambulance.free_at > self.now + 1e-9:
                raise RuntimeError("idle ambulance has a future free time")


def simulate(
    config: ScenarioConfig | None = None,
    settings: RunSettings | None = None,
    tape_override: DemandTape | None = None,
) -> RunResult:
    """Run one deterministic episode."""
    return Simulator(config or ScenarioConfig(), settings or RunSettings(), tape_override).run()

