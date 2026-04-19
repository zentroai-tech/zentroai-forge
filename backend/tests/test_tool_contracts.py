"""Tests for the Tool Contracts Registry, IR validation, and stub generator."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from agent_compiler.models.ir import Edge, EngineType, Flow, Node, NodeType
from agent_compiler.models.ir_v2 import (
    AgentSpec,
    EntrypointSpec,
    FlowIRv2,
    GraphSpec,
    ResourceRegistry,
)
from agent_compiler.tools.contracts import (
    ToolContract,
    ToolContractRegistry,
    get_tool_contract_registry,
)
from agent_compiler.ir.validate import (
    IRToolValidationError,
    collect_tool_names,
    validate_tool_references,
)
from agent_compiler.export.generate_tools import ToolStubGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ToolContractRegistry:
    return get_tool_contract_registry()


@pytest.fixture
def ir_with_contracts() -> FlowIRv2:
    """IR that references known contract-only tools."""
    return FlowIRv2(
        ir_version="2",
        flow=Flow(
            id="test-contracts",
            name="Contracts Test",
            version="1.0.0",
            engine_preference=EngineType.LANGCHAIN,
        ),
        agents=[
            AgentSpec(
                id="toolsmith",
                name="Toolsmith",
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id="sql",
                            type=NodeType.TOOL,
                            name="SQL Tool",
                            params={"tool_name": "sql_query", "is_start": True},
                        ),
                        Node(
                            id="s3",
                            type=NodeType.TOOL,
                            name="S3 Tool",
                            params={"tool_name": "s3_get_object"},
                        ),
                        Node(
                            id="out",
                            type=NodeType.OUTPUT,
                            name="Output",
                            params={"output_template": "{current}", "format": "json"},
                        ),
                    ],
                    edges=[
                        Edge(source="sql", target="s3"),
                        Edge(source="s3", target="out"),
                    ],
                    root="sql",
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="toolsmith")],
        handoffs=[],
        resources=ResourceRegistry(
            global_tools=["web_search", "calculator"],
        ),
    )


@pytest.fixture
def ir_with_unknown_tool() -> FlowIRv2:
    """IR that references a tool NOT in the registry."""
    return FlowIRv2(
        ir_version="2",
        flow=Flow(
            id="test-unknown",
            name="Unknown Tool Test",
            version="1.0.0",
            engine_preference=EngineType.LANGCHAIN,
        ),
        agents=[
            AgentSpec(
                id="agent",
                name="Agent",
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id="mystery",
                            type=NodeType.TOOL,
                            name="Mystery Tool",
                            params={"tool_name": "totally_unknown_tool", "is_start": True},
                        ),
                        Node(
                            id="out",
                            type=NodeType.OUTPUT,
                            name="Output",
                            params={"output_template": "{current}", "format": "text"},
                        ),
                    ],
                    edges=[Edge(source="mystery", target="out")],
                    root="mystery",
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="agent")],
        handoffs=[],
    )


@pytest.fixture
def ir_with_mcp_tool() -> FlowIRv2:
    """IR that references an MCP wildcard tool."""
    return FlowIRv2(
        ir_version="2",
        flow=Flow(
            id="test-mcp",
            name="MCP Tool Test",
            version="1.0.0",
            engine_preference=EngineType.LANGCHAIN,
        ),
        agents=[
            AgentSpec(
                id="agent",
                name="Agent",
                graph=GraphSpec(
                    nodes=[
                        Node(
                            id="pub",
                            type=NodeType.TOOL,
                            name="PubMed",
                            params={"tool_name": "mcp:pubmed.search", "is_start": True},
                        ),
                        Node(
                            id="out",
                            type=NodeType.OUTPUT,
                            name="Output",
                            params={"output_template": "{current}", "format": "text"},
                        ),
                    ],
                    edges=[Edge(source="pub", target="out")],
                    root="pub",
                ),
            )
        ],
        entrypoints=[EntrypointSpec(name="main", agent_id="agent")],
        handoffs=[],
    )


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestToolContractRegistry:
    def test_singleton(self):
        r1 = get_tool_contract_registry()
        r2 = get_tool_contract_registry()
        assert r1 is r2

    def test_builtin_tools_registered(self, registry: ToolContractRegistry):
        for name in ["web_search", "search", "url_reader", "calculator", "datetime"]:
            assert registry.get(name) is not None, f"Missing built-in: {name}"

    def test_contract_only_tools_registered(self, registry: ToolContractRegistry):
        for name in ["sql_query", "http_request", "python_sandbox", "s3_get_object"]:
            c = registry.get(name)
            assert c is not None, f"Missing contract-only tool: {name}"
            assert c.contract_only is True

    def test_builtin_tools_not_contract_only(self, registry: ToolContractRegistry):
        for name in ["web_search", "calculator", "datetime"]:
            c = registry.get(name)
            assert c is not None
            assert c.contract_only is False

    def test_mcp_is_wildcard(self, registry: ToolContractRegistry):
        assert registry.is_mcp("mcp:pubmed.search") is True
        assert registry.is_mcp("mcp:anything") is True
        assert registry.is_mcp("web_search") is False

    def test_resolve_known(self, registry: ToolContractRegistry):
        contract, is_known = registry.resolve("sql_query")
        assert is_known is True
        assert contract is not None
        assert contract.name == "sql_query"

    def test_resolve_mcp(self, registry: ToolContractRegistry):
        contract, is_known = registry.resolve("mcp:custom.tool")
        assert is_known is True
        assert contract is None  # MCP wildcard has no individual contract

    def test_resolve_unknown(self, registry: ToolContractRegistry):
        contract, is_known = registry.resolve("totally_unknown")
        assert is_known is False
        assert contract is None

    def test_list_names_contains_all(self, registry: ToolContractRegistry):
        names = registry.list_names()
        assert "web_search" in names
        assert "sql_query" in names
        assert "python_sandbox" in names

    def test_contract_schemas_are_valid(self, registry: ToolContractRegistry):
        for c in registry.get_all():
            assert isinstance(c.input_schema, dict), f"{c.name}: bad input_schema"
            assert c.input_schema.get("type") == "object", f"{c.name}: input_schema must be object"
            assert isinstance(c.output_schema, dict), f"{c.name}: bad output_schema"

    def test_custom_registration(self):
        """A custom contract can be registered at runtime."""
        reg = ToolContractRegistry()
        custom = ToolContract(
            name="my_custom_tool",
            version="2.0",
            description="Custom tool",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"y": {"type": "string"}}},
            contract_only=True,
        )
        reg.register(custom)
        assert reg.get("my_custom_tool") is not None
        assert reg.get("my_custom_tool").version == "2.0"


# ---------------------------------------------------------------------------
# IR validation tests
# ---------------------------------------------------------------------------


class TestCollectToolNames:
    def test_collects_tool_nodes(self, ir_with_contracts: FlowIRv2):
        names = collect_tool_names(ir_with_contracts)
        assert "sql_query" in names
        assert "s3_get_object" in names

    def test_collects_global_tools(self, ir_with_contracts: FlowIRv2):
        names = collect_tool_names(ir_with_contracts)
        assert "web_search" in names
        assert "calculator" in names

    def test_mcp_tool_collected(self, ir_with_mcp_tool: FlowIRv2):
        names = collect_tool_names(ir_with_mcp_tool)
        assert "mcp:pubmed.search" in names

    def test_non_tool_nodes_excluded(self):
        ir = FlowIRv2(
            ir_version="2",
            flow=Flow(id="x", name="x", version="1.0.0", engine_preference=EngineType.LANGCHAIN),
            agents=[
                AgentSpec(
                    id="a",
                    name="A",
                    graph=GraphSpec(
                        nodes=[
                            Node(id="llm", type=NodeType.LLM, name="LLM", params={"is_start": True}),
                            Node(id="out", type=NodeType.OUTPUT, name="Out", params={"output_template": "{current}"}),
                        ],
                        edges=[Edge(source="llm", target="out")],
                        root="llm",
                    ),
                )
            ],
            entrypoints=[EntrypointSpec(name="main", agent_id="a")],
            handoffs=[],
        )
        names = collect_tool_names(ir)
        assert len(names) == 0


class TestValidateToolReferences:
    def test_known_tools_pass(self, ir_with_contracts: FlowIRv2):
        warnings = validate_tool_references(ir_with_contracts)
        assert warnings == []

    def test_mcp_tools_pass(self, ir_with_mcp_tool: FlowIRv2):
        warnings = validate_tool_references(ir_with_mcp_tool)
        assert warnings == []

    def test_unknown_tool_raises(self, ir_with_unknown_tool: FlowIRv2):
        with pytest.raises(IRToolValidationError) as exc_info:
            validate_tool_references(ir_with_unknown_tool, allow_unknown=False)
        assert "totally_unknown_tool" in exc_info.value.unknown_tools

    def test_unknown_tool_soft_fail(self, ir_with_unknown_tool: FlowIRv2):
        warnings = validate_tool_references(ir_with_unknown_tool, allow_unknown=True)
        assert any("totally_unknown_tool" in w for w in warnings)

    def test_error_includes_locations(self, ir_with_unknown_tool: FlowIRv2):
        with pytest.raises(IRToolValidationError) as exc_info:
            validate_tool_references(ir_with_unknown_tool, allow_unknown=False)
        err = exc_info.value
        assert "totally_unknown_tool" in err.locations
        assert any("agent 'agent' node 'mystery'" in loc for loc in err.locations["totally_unknown_tool"])

    def test_pharma_copilot_passes(self):
        """Pharma Research Copilot IR must pass tool validation."""
        from agent_compiler.templates import ProjectTemplateId, TargetEngine, TemplateFactory
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-validate",
            project_name="Pharma Validation",
        )
        warnings = validate_tool_references(ir)
        assert warnings == []


# ---------------------------------------------------------------------------
# Stub generator tests
# ---------------------------------------------------------------------------


class TestToolStubGenerator:
    def test_generates_contract_json(self, ir_with_contracts: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_contracts)
        gen.generate(tmp_path, include_tests=False)

        sql_contract = tmp_path / "app" / "tools" / "contracts" / "sql_query.json"
        assert sql_contract.exists(), "sql_query contract JSON not generated"
        data = json.loads(sql_contract.read_text())
        assert data["name"] == "sql_query"
        assert data["contract_only"] is True
        assert "input_schema" in data

    def test_generates_stub_py(self, ir_with_contracts: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_contracts)
        gen.generate(tmp_path, include_tests=False)

        stub = tmp_path / "app" / "tools" / "impl" / "sql_query.py"
        assert stub.exists(), "sql_query stub not generated"
        content = stub.read_text()
        assert "class Input(BaseModel)" in content
        assert "class Output(BaseModel)" in content
        assert "async def sql_query" in content
        assert "_check_readonly" in content  # real implementation was emitted

    def test_generates_contract_test(self, ir_with_contracts: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_contracts)
        gen.generate(tmp_path, include_tests=True)

        test_file = tmp_path / "tests" / "test_tool_contract_sql_query.py"
        assert test_file.exists(), "contract test not generated"
        content = test_file.read_text()
        assert "pytest" in content
        assert "_check_readonly" in content  # real integration test was emitted

    def test_impl_init_written(self, ir_with_contracts: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_contracts)
        gen.generate(tmp_path, include_tests=False)
        assert (tmp_path / "app" / "tools" / "impl" / "__init__.py").exists()

    def test_mcp_tools_skipped(self, ir_with_mcp_tool: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_mcp_tool)
        gen.generate(tmp_path, include_tests=False)
        contracts_dir = tmp_path / "app" / "tools" / "contracts"
        # MCP tools must NOT produce a contract file
        assert not list(contracts_dir.glob("mcp*.json"))

    def test_builtin_tools_generate_contract_json(self, ir_with_contracts: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_contracts)
        gen.generate(tmp_path, include_tests=False)
        # web_search is a global_tool in the fixture IR
        ws_contract = tmp_path / "app" / "tools" / "contracts" / "web_search.json"
        assert ws_contract.exists()

    def test_unknown_tool_generates_minimal_stub(self, ir_with_unknown_tool: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_unknown_tool)
        gen.generate(tmp_path, include_tests=False)
        stub = tmp_path / "app" / "tools" / "impl" / "totally_unknown_tool.py"
        assert stub.exists()
        content = stub.read_text()
        assert "NotImplementedError" in content

    def test_generates_settings_module(self, ir_with_contracts: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_contracts)
        gen.generate(tmp_path, include_tests=False)
        settings = tmp_path / "app" / "tools" / "settings.py"
        assert settings.exists(), "settings.py not generated"
        content = settings.read_text()
        assert "HTTP_ALLOWED_HOSTS" in content
        assert "DATABASE_URL" in content

    def test_real_implementations_have_no_not_implemented(self, tmp_path: Path):
        """The 4 contract tools must NOT have NotImplementedError in generated impl."""
        from agent_compiler.templates import ProjectTemplateId, TargetEngine, TemplateFactory
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-real-impls",
            project_name="Real Impl Test",
        )
        gen = ToolStubGenerator(ir)
        gen.generate(tmp_path, include_tests=False)
        for name in ["sql_query", "http_request", "python_sandbox", "s3_get_object"]:
            content = (tmp_path / "app" / "tools" / "impl" / f"{name}.py").read_text()
            assert "NotImplementedError" not in content, f"{name} still has NotImplementedError stub"

    def test_allowlist_code_present_in_http_request(self, tmp_path: Path):
        from agent_compiler.templates import ProjectTemplateId, TargetEngine, TemplateFactory
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="pharma-allowlist-test",
            project_name="Pharma Allowlist",
        )
        gen = ToolStubGenerator(ir)
        gen.generate(tmp_path, include_tests=False)
        content = (tmp_path / "app" / "tools" / "impl" / "http_request.py").read_text()
        assert "HTTP_ALLOWED_HOSTS" in content
        assert "PermissionError" in content

    def test_unknown_tool_still_gets_not_implemented(self, ir_with_unknown_tool: FlowIRv2, tmp_path: Path):
        gen = ToolStubGenerator(ir_with_unknown_tool)
        gen.generate(tmp_path, include_tests=False)
        content = (tmp_path / "app" / "tools" / "impl" / "totally_unknown_tool.py").read_text()
        assert "NotImplementedError" in content

    def test_all_pharma_contract_tools_get_stubs(self, tmp_path: Path):
        """Pharma copilot export must include stubs for all 4 contract tools."""
        from agent_compiler.templates import ProjectTemplateId, TargetEngine, TemplateFactory
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="pharma-stub-test",
            project_name="Pharma Stub",
        )
        gen = ToolStubGenerator(ir)
        gen.generate(tmp_path, include_tests=False)

        contracts_dir = tmp_path / "app" / "tools" / "contracts"
        for name in ["sql_query", "http_request", "python_sandbox", "s3_get_object"]:
            assert (contracts_dir / f"{name}.json").exists(), f"Missing contract: {name}"
            assert (tmp_path / "app" / "tools" / "impl" / f"{name}.py").exists(), f"Missing stub: {name}"


# ---------------------------------------------------------------------------
# Export integration: stubs end up in ZIP
# ---------------------------------------------------------------------------


class TestExportIncludesToolStubs:
    def test_pharma_export_includes_tool_stubs(self):
        """Full export of pharma copilot ZIP must contain tool stubs and contracts."""
        from agent_compiler.templates import ProjectTemplateId, TargetEngine, TemplateFactory
        from agent_compiler.services.export_service import ExportService, ExportTarget

        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="pharma-export-test",
            project_name="Pharma Export",
        )

        service = ExportService()
        zip_bytes = service.export_flow(ir, target=ExportTarget.RUNTIME)
        names = set(zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist())

        for tool in ["sql_query", "http_request", "python_sandbox", "s3_get_object"]:
            assert f"app/tools/contracts/{tool}.json" in names, f"Missing contract in ZIP: {tool}"
            assert f"app/tools/impl/{tool}.py" in names, f"Missing stub in ZIP: {tool}"
