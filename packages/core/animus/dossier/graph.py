"""Animus Dossier — Entity Graph Analysis.

Network analysis for entity co-occurrence relationships.
Ported from Dossier and adapted for Animus knowledge representation.

Requires: networkx >= 3.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import networkx as nx


def _require_networkx() -> None:
    """Ensure networkx is available."""
    try:
        import networkx as nx  # noqa: F401
    except ImportError:
        raise ImportError(
            "networkx is required for graph analysis. "
            "Install it with: pip install 'animus[dossier-graph]'"
        )


# ═══════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════


@dataclass
class NodeMetrics:
    """Centrality metrics for a single entity node."""

    entity_id: str
    name: str
    type: str
    degree: int = 0
    weighted_degree: int = 0
    betweenness: float = 0.0
    closeness: float = 0.0
    eigenvector: float = 0.0


@dataclass
class Community:
    """A detected community/cluster of entities."""

    id: int
    members: list[dict] = field(default_factory=list)
    size: int = 0
    density: float = 0.0


@dataclass
class PathResult:
    """Shortest path between two entities."""

    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    total_weight: int = 0
    hops: int = 0


@dataclass
class GraphStats:
    """Summary statistics for the entity graph."""

    node_count: int = 0
    edge_count: int = 0
    density: float = 0.0
    components: int = 0
    avg_degree: float = 0.0
    avg_weighted_degree: float = 0.0


# ═══════════════════════════════════════════════════════════════════
# Graph Analyzer
# ═══════════════════════════════════════════════════════════════════

VALID_METRICS = {"degree", "betweenness", "closeness", "eigenvector"}


class GraphAnalyzer:
    """Builds and analyzes entity co-occurrence graphs.

    Works with any data source that provides entity nodes and weighted
    co-occurrence edges. Adapted from Dossier's graph_analysis module.

    Usage:
        analyzer = GraphAnalyzer()
        analyzer.add_node("alice", type="person")
        analyzer.add_node("acme", type="org")
        analyzer.add_edge("alice", "acme", weight=3)

        stats = analyzer.get_stats()
        top = analyzer.get_centrality(metric="betweenness", limit=10)
    """

    def __init__(self) -> None:
        _require_networkx()
        import networkx as nx

        self.nx = nx
        self._graph: nx.Graph = nx.Graph()
        self._nodes: dict[str, dict] = {}

    def add_node(self, entity_id: str, name: str, entity_type: str, **attrs) -> None:
        """Add an entity node to the graph.

        Args:
            entity_id: Unique identifier
            name: Human-readable name
            entity_type: Type of entity (person, org, etc.)
            **attrs: Additional node attributes
        """
        self._nodes[entity_id] = {"name": name, "type": entity_type, **attrs}
        self._graph.add_node(entity_id, name=name, type=entity_type, **attrs)

    def add_edge(self, source_id: str, target_id: str, weight: float = 1.0, **attrs) -> None:
        """Add a weighted co-occurrence edge between entities.

        Duplicate edges have their weights summed.
        """
        if self._graph.has_edge(source_id, target_id):
            self._graph[source_id][target_id]["weight"] += weight
        else:
            self._graph.add_edge(source_id, target_id, weight=weight, **attrs)

    def get_stats(self) -> GraphStats:
        """Overall network statistics."""
        graph = self._graph
        n = graph.number_of_nodes()
        if n == 0:
            return GraphStats()

        degrees = [d for _, d in graph.degree()]
        weighted_degrees = [d for _, d in graph.degree(weight="weight")]

        return GraphStats(
            node_count=n,
            edge_count=graph.number_of_edges(),
            density=self.nx.density(graph),
            components=self.nx.number_connected_components(graph),
            avg_degree=sum(degrees) / n,
            avg_weighted_degree=sum(weighted_degrees) / n,
        )

    def get_centrality(
        self,
        metric: str = "degree",
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[NodeMetrics]:
        """Top entities by centrality metric.

        Supported metrics: degree, betweenness, closeness, eigenvector.

        Args:
            metric: Centrality metric to compute
            entity_type: Filter by entity type (optional)
            limit: Maximum results to return

        Returns:
            List of NodeMetrics sorted by centrality
        """
        if metric not in VALID_METRICS:
            raise ValueError(
                f"Invalid metric '{metric}'. Must be one of: {', '.join(sorted(VALID_METRICS))}"
            )

        graph = self._get_subgraph(entity_type)
        if graph.number_of_nodes() == 0:
            return []

        # Compute requested centrality
        if metric == "degree":
            scores = self.nx.degree_centrality(graph)
        elif metric == "betweenness":
            scores = self.nx.betweenness_centrality(graph, weight="weight")
        elif metric == "closeness":
            scores = self.nx.closeness_centrality(graph, distance="weight")
        else:  # eigenvector
            try:
                scores = self.nx.eigenvector_centrality(graph, weight="weight", max_iter=1000)
            except self.nx.PowerIterationFailedConvergence:
                scores = {n: 0.0 for n in graph.nodes()}

        degrees = dict(graph.degree())
        weighted_degrees = dict(graph.degree(weight="weight"))

        results = []
        for node_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]:
            attrs = graph.nodes[node_id]
            nm = NodeMetrics(
                entity_id=node_id,
                name=attrs.get("name", ""),
                type=attrs.get("type", ""),
                degree=degrees.get(node_id, 0),
                weighted_degree=weighted_degrees.get(node_id, 0),
            )
            setattr(nm, metric, score)
            results.append(nm)

        return results

    def get_communities(self, min_size: int = 2) -> list[Community]:
        """Detect communities using Louvain method.

        Args:
            min_size: Minimum community size to include

        Returns:
            List of communities sorted by size descending
        """
        graph = self._graph
        if graph.number_of_nodes() == 0:
            return []

        communities = self.nx.community.louvain_communities(graph, weight="weight", seed=42)

        results = []
        for idx, members in enumerate(communities):
            if len(members) < min_size:
                continue

            sub = graph.subgraph(members)
            density = self.nx.density(sub)

            member_list = []
            for nid in sorted(members):
                attrs = graph.nodes[nid]
                member_list.append(
                    {
                        "entity_id": nid,
                        "name": attrs.get("name", ""),
                        "type": attrs.get("type", ""),
                    }
                )

            results.append(
                Community(
                    id=idx,
                    members=member_list,
                    size=len(members),
                    density=density,
                )
            )

        results.sort(key=lambda c: c.size, reverse=True)
        return results

    def find_shortest_path(self, source_id: str, target_id: str) -> PathResult | None:
        """Shortest path between two entities (Dijkstra, weight=1/co-occurrence).

        Returns:
            PathResult or None if no path exists
        """
        graph = self._graph
        if source_id not in graph or target_id not in graph:
            return None

        # Invert weights: high co-occurrence = short distance
        inverse_graph = graph.copy()
        for u, v, data in inverse_graph.edges(data=True):
            data["distance"] = 1.0 / max(data["weight"], 0.001)

        try:
            path_nodes = self.nx.shortest_path(
                inverse_graph, source_id, target_id, weight="distance"
            )
        except self.nx.NetworkXNoPath:
            return None

        nodes = []
        edges = []
        total_weight = 0

        for nid in path_nodes:
            attrs = graph.nodes[nid]
            nodes.append(
                {
                    "entity_id": nid,
                    "name": attrs.get("name", ""),
                    "type": attrs.get("type", ""),
                }
            )

        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            w = graph[u][v]["weight"]
            total_weight += w
            edges.append({"source": u, "target": v, "weight": w})

        return PathResult(
            nodes=nodes,
            edges=edges,
            total_weight=total_weight,
            hops=len(path_nodes) - 1,
        )

    def get_neighbors(
        self,
        entity_id: str,
        hops: int = 1,
        min_weight: float = 1.0,
    ) -> list[dict]:
        """BFS neighbors within N hops, filtered by min edge weight.

        Args:
            entity_id: Starting entity
            hops: Number of hops to traverse
            min_weight: Minimum edge weight to include

        Returns:
            List of neighbor dicts with name, type, weight, hop distance
        """
        graph = self._graph
        if entity_id not in graph:
            return []

        visited = {entity_id}
        frontier = {entity_id}
        results = []

        for hop in range(hops):
            next_frontier = set()
            for node in frontier:
                for neighbor in graph.neighbors(node):
                    if neighbor in visited:
                        continue
                    weight = graph[node][neighbor]["weight"]
                    if weight >= min_weight:
                        attrs = graph.nodes[neighbor]
                        results.append(
                            {
                                "entity_id": neighbor,
                                "name": attrs.get("name", ""),
                                "type": attrs.get("type", ""),
                                "weight": weight,
                                "hop": hop + 1,
                            }
                        )
                        next_frontier.add(neighbor)
                    visited.add(neighbor)
            frontier = next_frontier

        results.sort(key=lambda x: x["weight"], reverse=True)
        return results

    def get_subgraph(self, entity_ids: list[str]) -> dict:
        """Extract induced subgraph for given entity IDs.

        Args:
            entity_ids: List of entity IDs to include

        Returns:
            Dict with "nodes" and "edges" lists
        """
        graph = self._graph
        valid_ids = [eid for eid in entity_ids if eid in graph]

        if not valid_ids:
            return {"nodes": [], "edges": []}

        sub = graph.subgraph(valid_ids)

        nodes = []
        for nid in sub.nodes():
            attrs = sub.nodes[nid]
            nodes.append(
                {
                    "entity_id": nid,
                    "name": attrs.get("name", ""),
                    "type": attrs.get("type", ""),
                }
            )

        edges = []
        for u, v, data in sub.edges(data=True):
            edges.append({"source": u, "target": v, "weight": data["weight"]})

        return {"nodes": nodes, "edges": edges}

    def _get_subgraph(self, entity_type: str | None = None) -> nx.Graph:
        """Get full graph or type-filtered subgraph."""
        if entity_type is None:
            return self._graph

        nodes_of_type = [
            nid for nid, attrs in self._graph.nodes(data=True) if attrs.get("type") == entity_type
        ]
        return self._graph.subgraph(nodes_of_type)

    def to_dict(self) -> dict:
        """Serialize graph to dictionary format."""
        return {
            "nodes": [{"id": nid, **attrs} for nid, attrs in self._graph.nodes(data=True)],
            "edges": [
                {"source": u, "target": v, **data} for u, v, data in self._graph.edges(data=True)
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> GraphAnalyzer:
        """Deserialize from dictionary."""
        analyzer = cls()
        for node in data.get("nodes", []):
            nid = node.pop("id")
            name = node.pop("name", nid)
            entity_type = node.pop("type", "unknown")
            analyzer.add_node(nid, name=name, entity_type=entity_type, **node)
        for edge in data.get("edges", []):
            source = edge.pop("source")
            target = edge.pop("target")
            analyzer.add_edge(source, target, **edge)
        return analyzer
