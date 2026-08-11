from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx

from fraud_engine.domain import PaymentEvent

GRAPH_FEATURE_NAMES = (
    "shared_device_customers",
    "shared_ip_customers",
    "suspicious_component_size",
    "merchant_fraud_concentration",
    "max_entity_degree",
    "neighborhood_confirmed_fraud_rate",
    "merchant_customer_count",
    "device_observations",
    "ip_observations",
)


def _node(kind: str, identifier: str) -> str:
    return f"{kind}:{identifier}"


@dataclass(frozen=True)
class GraphSnapshot:
    features: dict[str, float]
    graph_score: float


class FraudGraph:
    """Incremental heterogeneous entity graph.

    Signals are calculated before inserting the current event. Confirmed fraud must be
    supplied through ``confirm_fraud``; authorization-time labels are never consumed.
    """

    def __init__(self) -> None:
        self.graph = nx.Graph()
        self.entity_observations: dict[str, int] = defaultdict(int)
        self.entity_confirmed_fraud: dict[str, int] = defaultdict(int)
        self._parent: dict[str, str] = {}
        self._component_size: dict[str, int] = {}
        self._component_observations: dict[str, int] = {}
        self._component_confirmed_fraud: dict[str, int] = {}

    @staticmethod
    def event_nodes(event: PaymentEvent) -> dict[str, str]:
        return {
            "customer": _node("customer", event.customer_id),
            "card": _node("card", event.card_id),
            "device": _node("device", event.device_id),
            "ip": _node("ip", event.ip_address),
            "merchant": _node("merchant", event.merchant_id),
        }

    def compute(self, event: PaymentEvent, *, update: bool = True) -> GraphSnapshot:
        nodes = self.event_nodes(event)
        device_customers = self._neighbor_count(nodes["device"], "customer")
        ip_customers = self._neighbor_count(nodes["ip"], "customer")
        component_size, observed, confirmed = self._candidate_component_totals(nodes.values())
        merchant_observed = self.entity_observations[nodes["merchant"]]
        merchant_fraud = self.entity_confirmed_fraud[nodes["merchant"]]
        max_degree = max(
            self.graph.degree(node) if node in self.graph else 0 for node in nodes.values()
        )
        features = {
            "shared_device_customers": float(device_customers),
            "shared_ip_customers": float(ip_customers),
            "suspicious_component_size": float(component_size),
            "merchant_fraud_concentration": merchant_fraud / max(merchant_observed, 1),
            "max_entity_degree": float(max_degree),
            "neighborhood_confirmed_fraud_rate": confirmed / max(observed, 1),
            "merchant_customer_count": float(self._neighbor_count(nodes["merchant"], "customer")),
            "device_observations": float(self.entity_observations[nodes["device"]]),
            "ip_observations": float(self.entity_observations[nodes["ip"]]),
        }
        graph_score = min(
            1.0,
            0.22 * min(device_customers / 3, 1)
            + 0.22 * min(ip_customers / 3, 1)
            + 0.18 * min(math.log1p(component_size) / math.log(30), 1)
            + 0.18 * features["merchant_fraud_concentration"]
            + 0.20 * features["neighborhood_confirmed_fraud_rate"],
        )
        if update:
            self.update(event)
        return GraphSnapshot(features=features, graph_score=graph_score)

    def _neighbor_count(self, node: str, kind: str) -> int:
        if node not in self.graph:
            return 0
        return sum(neighbor.startswith(f"{kind}:") for neighbor in self.graph.neighbors(node))

    def _find(self, node: str) -> str:
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[node] != node:
            parent = self._parent[node]
            self._parent[node] = root
            node = parent
        return root

    def _ensure_component_node(self, node: str) -> None:
        if node not in self._parent:
            self._parent[node] = node
            self._component_size[node] = 1
            self._component_observations[node] = 0
            self._component_confirmed_fraud[node] = 0

    def _union(self, left: str, right: str) -> None:
        left_root, right_root = self._find(left), self._find(right)
        if left_root == right_root:
            return
        if self._component_size[left_root] < self._component_size[right_root]:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        self._component_size[left_root] += self._component_size.pop(right_root)
        self._component_observations[left_root] += self._component_observations.pop(right_root)
        self._component_confirmed_fraud[left_root] += self._component_confirmed_fraud.pop(
            right_root
        )

    def _candidate_component_totals(self, nodes: Iterable[str]) -> tuple[int, int, int]:
        roots: set[str] = set()
        unseen = 0
        for node in nodes:
            if node in self._parent:
                roots.add(self._find(node))
            else:
                unseen += 1
        return (
            unseen + sum(self._component_size[root] for root in roots),
            sum(self._component_observations[root] for root in roots),
            sum(self._component_confirmed_fraud[root] for root in roots),
        )

    def update(self, event: PaymentEvent) -> None:
        nodes = self.event_nodes(event)
        for kind, node in nodes.items():
            self.graph.add_node(node, kind=kind, identifier=node.split(":", 1)[1])
            self._ensure_component_node(node)
            self.entity_observations[node] += 1
            self._component_observations[self._find(node)] += 1
        customer = nodes["customer"]
        for kind in ("card", "device", "ip", "merchant"):
            edge = self.graph.get_edge_data(customer, nodes[kind], default={})
            self.graph.add_edge(
                customer, nodes[kind], observations=int(edge.get("observations", 0)) + 1
            )
            self._union(customer, nodes[kind])

    def confirm_fraud(self, event: PaymentEvent) -> None:
        for node in self.event_nodes(event).values():
            self.entity_confirmed_fraud[node] += 1
            if node in self.graph:
                self.graph.nodes[node]["confirmed_fraud"] = self.entity_confirmed_fraud[node]
                self._component_confirmed_fraud[self._find(node)] += 1

    def suspicious_subgraph(self, minimum_customers: int = 3) -> dict[str, list[dict[str, object]]]:
        suspicious: set[str] = set()
        for node, data in self.graph.nodes(data=True):
            if (
                data["kind"] in {"device", "ip"}
                and self._neighbor_count(node, "customer") >= minimum_customers
            ):
                suspicious.add(node)
                suspicious.update(self.graph.neighbors(node))
        graph = self.graph.subgraph(suspicious)
        return {
            "nodes": [
                {
                    "id": node,
                    "kind": data["kind"],
                    "confirmed_fraud": data.get("confirmed_fraud", 0),
                }
                for node, data in graph.nodes(data=True)
            ],
            "edges": [{"source": left, "target": right} for left, right in graph.edges()],
        }
