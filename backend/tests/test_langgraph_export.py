"""Tests for v2 export target behavior."""

import io
import json
import zipfile

import pytest

from agent_compiler.models.ir import Edge, EngineType, Flow, Node, NodeType
from agent_compiler.models.ir_v2 import AgentSpec, EntrypointSpec, FlowIRv2, GraphSpec
from agent_compiler.services.export_service import ExportService, ExportTarget


@pytest.fixture
def sample_flow_ir() -> FlowIRv2:
    return FlowIRv2(
        ir_version="2",
        flow=Flow(
            id="test-langgraph-agent",
            name="Test LangGraph Agent",
            version="1.0.0",
            description="A test agent for export testing",
            engine_preference=EngineType.LANGCHAIN,
        ),
        agents=[
            AgentSpec(
                id="main",
                name="Main",
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id="retriever",
                            type=NodeType.RETRIEVER,
                            name="Retriever",
                            params={"is_start": True},
                        ),
                        Node(id="llm", type=NodeType.LLM, name="LLM", params={}),
                        Node(id="output", type=NodeType.OUTPUT, name="Output", params={}),
                    ],
                    edges=[Edge(source="retriever", target="llm"), Edge(source="llm", target="output")],
                    root="retriever",
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="main")],
        handoffs=[],
    )


class TestExportTargets:
    def test_runtime_target_creates_valid_zip(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        assert zipfile.ZipFile(io.BytesIO(zip_bytes)).testzip() is None

    def test_langgraph_target_creates_valid_zip(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        zip_bytes = service.export_flow(sample_flow_ir, target=ExportTarget.LANGGRAPH)
        assert zipfile.ZipFile(io.BytesIO(zip_bytes)).testzip() is None

    def test_targets_share_same_v2_generator_contract(self, sample_flow_ir: FlowIRv2):
        service = ExportService()
        runtime_zip = service.export_flow(sample_flow_ir, target=ExportTarget.RUNTIME)
        langgraph_zip = service.export_flow(sample_flow_ir, target=ExportTarget.LANGGRAPH)

        runtime_names = set(zipfile.ZipFile(io.BytesIO(runtime_zip)).namelist())
        langgraph_names = set(zipfile.ZipFile(io.BytesIO(langgraph_zip)).namelist())
        assert runtime_names.issubset(langgraph_names)
        assert "runtime/langgraph_runner.py" in langgraph_names
        assert "ir.json" in runtime_names
        assert "runtime/supervisor.py" in runtime_names

    def test_router_flow_export_keeps_router_node(self):
        flow_ir = FlowIRv2(
            ir_version="2",
            flow=Flow(id="router-flow", name="Router Flow", engine_preference=EngineType.LANGCHAIN),
            agents=[
                AgentSpec(
                    id="main",
                    name="Main",
                    graph=GraphSpec(
                        nodes=[
                            Node(id="classifier", type=NodeType.LLM, name="Classifier", params={"is_start": True}),
                            Node(
                                id="router",
                                type=NodeType.ROUTER,
                                name="Router",
                                params={
                                    "routes": {"support": "support-llm", "sales": "sales-llm"},
                                    "default_route": "general-llm",
                                },
                            ),
                            Node(id="support-llm", type=NodeType.LLM, name="Support", params={}),
                            Node(id="sales-llm", type=NodeType.LLM, name="Sales", params={}),
                            Node(id="general-llm", type=NodeType.LLM, name="General", params={}),
                        ],
                        edges=[
                            Edge(source="classifier", target="router"),
                            Edge(source="router", target="support-llm"),
                            Edge(source="router", target="sales-llm"),
                            Edge(source="router", target="general-llm"),
                        ],
                        root="classifier",
                    ),
                )
            ],
            entrypoints=[EntrypointSpec(name="main", agent_id="main")],
            handoffs=[],
        )
        service = ExportService()
        zip_bytes = service.export_flow(flow_ir, target=ExportTarget.LANGGRAPH)
        payload = json.loads(zipfile.ZipFile(io.BytesIO(zip_bytes)).read("ir.json").decode("utf-8"))
        node_ids = {n["id"] for n in payload["agents"][0]["graph"]["nodes"]}
        assert "router" in node_ids
