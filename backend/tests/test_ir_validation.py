"""Tests for IR validation."""

import pytest
from pydantic import ValidationError

from agent_compiler.models.ir import (
    Edge,
    EngineType,
    Flow,
    LLMParams,
    Node,
    NodeType,
    RetrieverParams,
)
from agent_compiler.models.ir_v2 import GraphSpec
from agent_compiler.runtime.graph_runtime import AgentGraphRuntime


def _build_runtime_graph(
    *,
    flow: Flow,
    nodes: list[Node],
    edges: list[Edge],
    root: str,
) -> AgentGraphRuntime:
    graph = GraphSpec(nodes=nodes, edges=edges, root=root)
    return AgentGraphRuntime(flow=flow, nodes=graph.nodes, edges=graph.edges)


class TestNodeValidation:
    """Tests for Node model validation."""

    def test_valid_llm_node(self):
        """Test valid LLM node creation."""
        node = Node(
            id="llm1",
            type=NodeType.LLM,
            name="My LLM",
            params={
                "model": "gpt-4",
                "temperature": 0.5,
                "prompt_template": "Answer: {input}",
            },
        )
        assert node.id == "llm1"
        assert node.type == NodeType.LLM

        typed_params = node.get_typed_params()
        assert isinstance(typed_params, LLMParams)
        assert typed_params.model == "gpt-4"

    def test_valid_retriever_node(self):
        """Test valid Retriever node creation."""
        node = Node(
            id="retriever1",
            type=NodeType.RETRIEVER,
            name="Doc Retriever",
            params={
                "query_template": "{input}",
                "top_k": 10,
            },
        )
        typed_params = node.get_typed_params()
        assert isinstance(typed_params, RetrieverParams)
        assert typed_params.top_k == 10

    def test_invalid_temperature(self):
        """Test that invalid temperature is rejected."""
        with pytest.raises(ValidationError):
            Node(
                id="llm1",
                type=NodeType.LLM,
                name="Bad LLM",
                params={"temperature": 5.0},  # Max is 2.0
            )

    def test_empty_id_rejected(self):
        """Test that empty ID is rejected."""
        with pytest.raises(ValidationError):
            Node(
                id="",
                type=NodeType.LLM,
                name="Test",
                params={},
            )


class TestEdgeValidation:
    """Tests for Edge model validation."""

    def test_valid_edge(self):
        """Test valid edge creation."""
        edge = Edge(source="node1", target="node2")
        assert edge.source == "node1"
        assert edge.target == "node2"

    def test_self_loop_rejected(self):
        """Test that self-loops are rejected."""
        with pytest.raises(ValidationError, match="Self-loops are not allowed"):
            Edge(source="node1", target="node1")


class TestGraphValidation:
    """Tests for agent graph validation under IR v2."""

    def test_valid_simple_flow(self):
        """Test valid simple flow with two nodes."""
        graph = _build_runtime_graph(
            flow=Flow(id="test-flow", name="Test Flow"),
            nodes=[
                Node(id="start", type=NodeType.LLM, name="Start", params={}),
                Node(id="output", type=NodeType.OUTPUT, name="Output", params={}),
            ],
            edges=[Edge(source="start", target="output")],
            root="start",
        )
        assert graph.get_node("start") is not None
        assert len(graph.get_topological_order()) == 2

    def test_valid_rag_flow(self):
        """Test valid RAG flow with retriever and LLM."""
        graph = _build_runtime_graph(
            flow=Flow(
                id="rag-flow",
                name="RAG Flow",
                engine_preference=EngineType.AUTO,
            ),
            nodes=[
                Node(
                    id="retriever",
                    type=NodeType.RETRIEVER,
                    name="Retriever",
                    params={"query_template": "{input}", "top_k": 5},
                ),
                Node(
                    id="llm",
                    type=NodeType.LLM,
                    name="LLM",
                    params={"prompt_template": "Based on context: {citations}\nAnswer: {input}"},
                ),
                Node(
                    id="output",
                    type=NodeType.OUTPUT,
                    name="Output",
                    params={"output_template": "{current}"},
                ),
            ],
            edges=[
                Edge(source="retriever", target="llm"),
                Edge(source="llm", target="output"),
            ],
            root="retriever",
        )
        order = graph.get_topological_order()
        assert order == ["retriever", "llm", "output"]

    def test_explicit_root_node(self):
        """Test explicit root node selection."""
        graph = _build_runtime_graph(
            flow=Flow(id="test", name="Test"),
            nodes=[
                Node(id="a", type=NodeType.LLM, name="A", params={}),
                Node(id="b", type=NodeType.LLM, name="B", params={}),
            ],
            edges=[],
            root="b",
        )
        assert graph.get_topological_order() == ["a", "b"] or graph.get_topological_order() == ["b", "a"]

    def test_cycle_detection(self):
        """Test that cycles are rejected."""
        with pytest.raises(ValidationError, match="cycle"):
            GraphSpec(
                nodes=[
                    Node(id="a", type=NodeType.LLM, name="A", params={"is_start": True}),
                    Node(id="b", type=NodeType.LLM, name="B", params={}),
                    Node(id="c", type=NodeType.LLM, name="C", params={}),
                ],
                edges=[
                    Edge(source="a", target="b"),
                    Edge(source="b", target="c"),
                    Edge(source="c", target="a"),  # Creates cycle
                ],
                root="a",
            )

    def test_unknown_root_rejected(self):
        """Test that graphs with an unknown root are rejected."""
        with pytest.raises(ValidationError, match="Graph root"):
            GraphSpec(
                nodes=[
                    Node(id="a", type=NodeType.LLM, name="A", params={}),
                    Node(id="b", type=NodeType.OUTPUT, name="B", params={}),
                ],
                edges=[Edge(source="a", target="b")],
                root="missing",
            )

    def test_invalid_edge_reference(self):
        """Test that edges referencing non-existent nodes are rejected."""
        with pytest.raises(ValidationError, match="references unknown node"):
            GraphSpec(
                nodes=[
                    Node(id="a", type=NodeType.LLM, name="A", params={}),
                ],
                edges=[
                    Edge(source="a", target="nonexistent"),
                ],
                root="a",
            )

    def test_no_nodes_rejected(self):
        """Test that flows with no nodes are rejected."""
        with pytest.raises(ValidationError):
            GraphSpec(
                nodes=[],
                edges=[],
                root="start",
            )


class TestTopologicalOrder:
    """Tests for topological ordering."""

    def test_linear_flow_order(self):
        """Test topological order for linear flow."""
        graph = _build_runtime_graph(
            flow=Flow(id="test", name="Test"),
            nodes=[
                Node(id="a", type=NodeType.LLM, name="A", params={}),
                Node(id="b", type=NodeType.LLM, name="B", params={}),
                Node(id="c", type=NodeType.OUTPUT, name="C", params={}),
            ],
            edges=[
                Edge(source="a", target="b"),
                Edge(source="b", target="c"),
            ],
            root="a",
        )
        order = graph.get_topological_order()
        assert order == ["a", "b", "c"]

    def test_branching_flow_order(self):
        """Test topological order for branching flow."""
        graph = _build_runtime_graph(
            flow=Flow(id="test", name="Test"),
            nodes=[
                Node(id="start", type=NodeType.LLM, name="Start", params={}),
                Node(id="branch1", type=NodeType.LLM, name="Branch1", params={}),
                Node(id="branch2", type=NodeType.LLM, name="Branch2", params={}),
                Node(id="end", type=NodeType.OUTPUT, name="End", params={}),
            ],
            edges=[
                Edge(source="start", target="branch1"),
                Edge(source="start", target="branch2"),
                Edge(source="branch1", target="end"),
                Edge(source="branch2", target="end"),
            ],
            root="start",
        )
        order = graph.get_topological_order()
        # start must be first, end must be last
        assert order[0] == "start"
        assert order[-1] == "end"
        # branch1 and branch2 must be in the middle (order between them is deterministic due to sort)
        assert set(order[1:3]) == {"branch1", "branch2"}

    def test_get_successors(self):
        """Test getting node successors."""
        graph = _build_runtime_graph(
            flow=Flow(id="test", name="Test"),
            nodes=[
                Node(id="a", type=NodeType.LLM, name="A", params={}),
                Node(id="b", type=NodeType.LLM, name="B", params={}),
                Node(id="c", type=NodeType.OUTPUT, name="C", params={}),
            ],
            edges=[
                Edge(source="a", target="b"),
                Edge(source="a", target="c"),
            ],
            root="a",
        )
        successors = graph.get_successors("a")
        assert set(successors) == {"b", "c"}

    def test_get_predecessors(self):
        """Test getting node predecessors."""
        graph = _build_runtime_graph(
            flow=Flow(id="test", name="Test"),
            nodes=[
                Node(id="a", type=NodeType.LLM, name="A", params={}),
                Node(id="b", type=NodeType.LLM, name="B", params={}),
                Node(id="c", type=NodeType.OUTPUT, name="C", params={}),
            ],
            edges=[
                Edge(source="a", target="b"),
                Edge(source="a", target="c"),
                Edge(source="b", target="c"),
            ],
            root="a",
        )
        predecessors = graph.get_predecessors("c")
        assert set(predecessors) == {"a", "b"}
