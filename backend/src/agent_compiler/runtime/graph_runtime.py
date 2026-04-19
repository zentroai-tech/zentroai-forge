"""Runtime graph adapter for executing agent-local DAGs."""

from __future__ import annotations

from collections import defaultdict, deque

from agent_compiler.models.ir import Edge, Flow, Node


class AgentGraphRuntime:
    """Adapter that exposes graph helpers for a single agent graph."""

    def __init__(self, flow: Flow, nodes: list[Node], edges: list[Edge]):
        self.flow = flow
        self.nodes = nodes
        self.edges = edges

    def get_node(self, node_id: str) -> Node | None:
        """Get node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_successors(self, node_id: str) -> list[str]:
        """Get all immediate successor node IDs for a node."""
        return [edge.target for edge in self.edges if edge.source == node_id]

    def get_predecessors(self, node_id: str) -> list[str]:
        """Get all immediate predecessor node IDs for a node."""
        return [edge.source for edge in self.edges if edge.target == node_id]

    def get_topological_order(self) -> list[str]:
        """Topologically sort the DAG."""
        in_degree: dict[str, int] = defaultdict(int)
        graph: dict[str, list[str]] = defaultdict(list)

        node_ids = [node.id for node in self.nodes]
        for node_id in node_ids:
            in_degree[node_id] = 0

        for edge in self.edges:
            graph[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        queue = deque([node_id for node_id in node_ids if in_degree[node_id] == 0])
        order: list[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for successor in graph[current]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(order) != len(self.nodes):
            raise ValueError("Graph contains a cycle")

        return order
