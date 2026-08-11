from __future__ import annotations

import math
from collections import defaultdict
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
        component_nodes: set[str] = set(nodes.values())
        for node in nodes.values():
            if node in self.graph:
                component_nodes.update(nx.node_connected_component(self.graph, node))
        observed = sum(self.entity_observations[node] for node in component_nodes)
        confirmed = sum(self.entity_confirmed_fraud[node] for node in component_nodes)
        merchant_observed = self.entity_observations[nodes["merchant"]]
        merchant_fraud = self.entity_confirmed_fraud[nodes["merchant"]]
        max_degree = max(
            self.graph.degree(node) if node in self.graph else 0 for node in nodes.values()
        )
        features = {
            "shared_device_customers": float(device_customers),
            "shared_ip_customers": float(ip_customers),
            "suspicious_component_size": float(len(component_nodes)),
            "merchant_fraud_concentration": merchant_fraud / max(merchant_observed, 1),
            "max_entity_degree": float(max_degree),
            "neighborhood_confirmed_fraud_rate": confirmed / max(observed, 1),
        }
        graph_score = min(
            1.0,
            0.22 * min(device_customers / 3, 1)
            + 0.22 * min(ip_customers / 3, 1)
            + 0.18 * min(math.log1p(len(component_nodes)) / math.log(30), 1)
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

    def update(self, event: PaymentEvent) -> None:
        nodes = self.event_nodes(event)
        for kind, node in nodes.items():
            self.graph.add_node(node, kind=kind, identifier=node.split(":", 1)[1])
            self.entity_observations[node] += 1
        customer = nodes["customer"]
        for kind in ("card", "device", "ip", "merchant"):
            edge = self.graph.get_edge_data(customer, nodes[kind], default={})
            self.graph.add_edge(
                customer, nodes[kind], observations=int(edge.get("observations", 0)) + 1
            )

    def confirm_fraud(self, event: PaymentEvent) -> None:
        for node in self.event_nodes(event).values():
            self.entity_confirmed_fraud[node] += 1
            if node in self.graph:
                self.graph.nodes[node]["confirmed_fraud"] = self.entity_confirmed_fraud[node]

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
