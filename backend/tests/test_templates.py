"""Tests for Project Templates functionality."""

import json
import pytest
from agent_compiler.templates import (
    ProjectTemplateId,
    TargetEngine,
    TemplateFactory,
    get_template_registry,
)
from agent_compiler.templates.enums import get_template_version, TEMPLATE_VERSIONS
from agent_compiler.templates.factory import TemplateValidationError
from agent_compiler.models.ir import NodeType
from agent_compiler.models.ir_v2 import FlowIRv2


class TestTemplateEnums:
    """Tests for template enums."""

    def test_project_template_id_values(self):
        """Test ProjectTemplateId enum values."""
        assert ProjectTemplateId.BLANK.value == "blank"
        assert ProjectTemplateId.SIMPLE_AGENT.value == "simple_agent"
        assert ProjectTemplateId.RAG_AGENT.value == "rag_agent"
        assert ProjectTemplateId.SUPERVISOR_WORKERS.value == "supervisor_workers"
        assert ProjectTemplateId.ONCOLOGY_RESEARCH_TEAM.value == "oncology_research_team"
        assert ProjectTemplateId.FULLSTACK_MULTIAGENT.value == "fullstack_multiagent"
        assert ProjectTemplateId.PHARMA_RESEARCH_COPILOT.value == "pharma_research_copilot"

    def test_target_engine_values(self):
        """Test TargetEngine enum values."""
        assert TargetEngine.LLAMAINDEX.value == "llamaindex"
        assert TargetEngine.LANGGRAPH.value == "langgraph"

    def test_target_engine_default(self):
        """Test default engine is LangGraph."""
        assert TargetEngine.default() == TargetEngine.LANGGRAPH

    def test_template_versions_exist(self):
        """Test all templates have versions."""
        for template_id in ProjectTemplateId:
            version = get_template_version(template_id)
            assert version is not None
            assert version == "1.0.0"


class TestTemplateRegistry:
    """Tests for TemplateRegistry."""

    def test_registry_singleton(self):
        """Test registry returns same instance."""
        registry1 = get_template_registry()
        registry2 = get_template_registry()
        assert registry1 is registry2

    def test_registry_has_all_templates(self):
        """Test registry contains all defined templates."""
        registry = get_template_registry()
        templates = registry.get_all()
        assert len(templates) == len(ProjectTemplateId)

        template_ids = {t.id for t in templates}
        assert ProjectTemplateId.BLANK in template_ids
        assert ProjectTemplateId.SIMPLE_AGENT in template_ids
        assert ProjectTemplateId.RAG_AGENT in template_ids
        assert ProjectTemplateId.SUPERVISOR_WORKERS in template_ids
        assert ProjectTemplateId.ONCOLOGY_RESEARCH_TEAM in template_ids
        assert ProjectTemplateId.FULLSTACK_MULTIAGENT in template_ids
        assert ProjectTemplateId.PHARMA_RESEARCH_COPILOT in template_ids

    def test_get_template_by_id(self):
        """Test getting template by ID."""
        registry = get_template_registry()

        blank = registry.get(ProjectTemplateId.BLANK)
        assert blank is not None
        assert blank.name == "Blank Project"

        simple = registry.get(ProjectTemplateId.SIMPLE_AGENT)
        assert simple is not None
        assert simple.name == "Simple Agent Project"

        rag = registry.get(ProjectTemplateId.RAG_AGENT)
        assert rag is not None
        assert rag.name == "RAG Agent Project"

    def test_template_supports_engine(self):
        """Test engine support checking."""
        registry = get_template_registry()

        blank = registry.get(ProjectTemplateId.BLANK)
        assert blank.supports_engine(TargetEngine.LANGGRAPH)
        assert blank.supports_engine(TargetEngine.LLAMAINDEX)

    def test_template_to_dict(self):
        """Test template serialization."""
        registry = get_template_registry()
        blank = registry.get(ProjectTemplateId.BLANK)

        d = blank.to_dict()
        assert d["id"] == "blank"
        assert d["name"] == "Blank Project"
        assert "langgraph" in d["supported_engines"]
        assert "llamaindex" in d["supported_engines"]


class TestTemplateFactoryBlank:
    """Tests for blank template generation."""

    def test_create_blank_langgraph(self):
        """Test blank template with LangGraph."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.BLANK,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-blank-lg",
            project_name="Test Blank LangGraph",
        )

        assert isinstance(ir, FlowIRv2)
        assert ir.flow.id == "test-blank-lg"
        assert ir.flow.name == "Test Blank LangGraph"
        assert ir.flow.engine_preference.value == "langchain"
        assert len(ir.agents) == 1
        assert len(ir.agents[0].graph.nodes) == 1
        assert ir.agents[0].graph.nodes[0].type == NodeType.OUTPUT
        assert len(ir.agents[0].graph.edges) == 0

    def test_create_blank_llamaindex(self):
        """Test blank template with LlamaIndex."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.BLANK,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-blank-li",
            project_name="Test Blank LlamaIndex",
        )

        assert ir.flow.engine_preference.value == "llamaindex"
        assert len(ir.agents[0].graph.nodes) == 1

    def test_blank_is_deterministic(self):
        """Test blank template produces identical output."""
        ir1 = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.BLANK,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-id",
            project_name="Test",
        )
        ir2 = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.BLANK,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-id",
            project_name="Test",
        )

        assert ir1.model_dump() == ir2.model_dump()


class TestTemplateFactorySimpleAgent:
    """Tests for simple agent template generation."""

    def test_create_simple_agent_langgraph(self):
        """Test simple agent with LangGraph."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-agent-lg",
            project_name="Test Agent",
        )

        assert ir.flow.id == "test-agent-lg"
        assert ir.flow.engine_preference.value == "langchain"

        # Should have multiple nodes
        assert len(ir.agents[0].graph.nodes) >= 4
        node_types = {n.type for n in ir.agents[0].graph.nodes}
        assert NodeType.LLM in node_types
        assert NodeType.ROUTER in node_types
        assert NodeType.OUTPUT in node_types

    def test_create_simple_agent_llamaindex(self):
        """Test simple agent with LlamaIndex."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-agent-li",
            project_name="Test Agent",
        )

        assert ir.flow.engine_preference.value == "llamaindex"

    def test_simple_agent_with_memory(self):
        """Test simple agent includes memory when requested."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-agent-mem",
            project_name="Test Agent Memory",
            params={"include_memory": True},
        )

        node_types = {n.type for n in ir.agents[0].graph.nodes}
        assert NodeType.MEMORY in node_types

    def test_simple_agent_without_memory(self):
        """Test simple agent excludes memory when disabled."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-agent-nomem",
            project_name="Test Agent No Memory",
            params={"include_memory": False},
        )

        node_types = {n.type for n in ir.agents[0].graph.nodes}
        assert NodeType.MEMORY not in node_types

    def test_simple_agent_custom_model(self):
        """Test simple agent with custom model."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-agent-model",
            project_name="Test Agent Model",
            params={"model": "gpt-4-turbo"},
        )

        # Check LLM nodes use the custom model
        llm_nodes = [n for n in ir.agents[0].graph.nodes if n.type == NodeType.LLM]
        for node in llm_nodes:
            assert node.params["model"] == "gpt-4-turbo"

    def test_simple_agent_is_valid_ir(self):
        """Test simple agent produces valid IR."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-agent-valid",
            project_name="Test Agent Valid",
        )

        # Should validate without errors
        validated = FlowIRv2.model_validate(ir.model_dump())
        assert validated.flow.id == "test-agent-valid"


class TestTemplateFactoryRAGAgent:
    """Tests for RAG agent template generation."""

    def test_create_rag_agent_llamaindex(self):
        """Test RAG agent with LlamaIndex (default for RAG)."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-rag-li",
            project_name="Test RAG Agent",
        )

        assert ir.flow.id == "test-rag-li"
        assert ir.flow.engine_preference.value == "llamaindex"

        # Should have retriever node
        node_types = {n.type for n in ir.agents[0].graph.nodes}
        assert NodeType.RETRIEVER in node_types
        assert NodeType.LLM in node_types

    def test_create_rag_agent_langgraph(self):
        """Test RAG agent with LangGraph."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-rag-lg",
            project_name="Test RAG Agent",
        )

        assert ir.flow.engine_preference.value == "langchain"

    def test_rag_agent_with_query_rewrite(self):
        """Test RAG agent includes query rewrite when enabled."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-rag-qr",
            project_name="Test RAG QR",
            params={"include_query_rewrite": True},
        )

        # Check for query rewrite node
        node_names = [n.name.lower() for n in ir.agents[0].graph.nodes]
        assert any("rewrite" in name for name in node_names)

    def test_rag_agent_without_query_rewrite(self):
        """Test RAG agent excludes query rewrite when disabled."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-rag-noqr",
            project_name="Test RAG No QR",
            params={"include_query_rewrite": False},
        )

        node_ids = {n.id for n in ir.agents[0].graph.nodes}
        assert "query_rewrite" not in node_ids

    def test_rag_agent_with_citations(self):
        """Test RAG agent includes citation guard when enabled."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-rag-cite",
            project_name="Test RAG Citations",
            params={"include_citations": True},
        )

        # Check for citation guard router
        router_nodes = [n for n in ir.agents[0].graph.nodes if n.type == NodeType.ROUTER]
        assert len(router_nodes) >= 1

        # Check for guard mode
        citation_guard = next((n for n in router_nodes if "guard" in n.id.lower()), None)
        assert citation_guard is not None
        assert citation_guard.params.get("guard_mode") == "retrieval"

    def test_rag_agent_custom_top_k(self):
        """Test RAG agent with custom top_k."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-rag-topk",
            project_name="Test RAG Top K",
            params={"top_k": 10},
        )

        retriever = next(n for n in ir.agents[0].graph.nodes if n.type == NodeType.RETRIEVER)
        assert retriever.params["top_k"] == 10

    def test_rag_agent_is_valid_ir(self):
        """Test RAG agent produces valid IR."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="test-rag-valid",
            project_name="Test RAG Valid",
        )

        # Should validate without errors
        validated = FlowIRv2.model_validate(ir.model_dump())
        assert validated.flow.id == "test-rag-valid"


class TestTemplateFactoryValidation:
    """Tests for template factory validation."""

    def test_invalid_template_id(self):
        """Test invalid template ID raises error."""
        with pytest.raises(TemplateValidationError) as exc_info:
            TemplateFactory.create_ir(
                template_id="invalid",  # type: ignore
                engine=TargetEngine.LANGGRAPH,
                project_id="test",
                project_name="Test",
            )

    def test_unsupported_engine(self):
        """Test unsupported engine combination raises error."""
        # This test would only apply if we had templates that don't support all engines
        # Currently all templates support both engines
        pass

    def test_validate_params_valid(self):
        """Test parameter validation with valid params."""
        errors = TemplateFactory.validate_params(
            ProjectTemplateId.SIMPLE_AGENT,
            {"include_memory": True, "model": "gpt-4o"},
        )
        assert len(errors) == 0

    def test_validate_params_invalid_type(self):
        """Test parameter validation with wrong type."""
        errors = TemplateFactory.validate_params(
            ProjectTemplateId.SIMPLE_AGENT,
            {"include_memory": "yes"},  # Should be boolean
        )
        assert len(errors) > 0
        assert any("boolean" in e.lower() for e in errors)

    def test_validate_params_invalid_select(self):
        """Test parameter validation with invalid select option."""
        errors = TemplateFactory.validate_params(
            ProjectTemplateId.SIMPLE_AGENT,
            {"tools": "invalid_option"},
        )
        assert len(errors) > 0


class TestTemplateFactoryOncologyResearchTeam:
    """Tests for oncology research multi-agent template generation."""

    def test_create_oncology_research_team_defaults(self):
        """Template should generate v2 IR with supervisor + specialists."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.ONCOLOGY_RESEARCH_TEAM,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-oncology-team",
            project_name="Oncology Team",
        )

        assert isinstance(ir, FlowIRv2)
        assert ir.ir_version == "2"
        assert ir.entrypoints[0].name == "main"
        assert ir.entrypoints[0].agent_id == "supervisor"

        agent_ids = {a.id for a in ir.agents}
        assert "supervisor" in agent_ids
        assert "genomics_analyst" in agent_ids
        assert "pathology_analyst" in agent_ids
        assert "trials_scout" in agent_ids

    def test_create_oncology_research_team_with_optional_agents_disabled(self):
        """Optional specialists should be configurable by template params."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.ONCOLOGY_RESEARCH_TEAM,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-oncology-min",
            project_name="Oncology Minimal",
            params={
                "include_pathology": False,
                "include_clinical_trials": False,
            },
        )

        assert isinstance(ir, FlowIRv2)
        agent_ids = {a.id for a in ir.agents}
        assert "supervisor" in agent_ids
        assert "genomics_analyst" in agent_ids
        assert "pathology_analyst" not in agent_ids
        assert "trials_scout" not in agent_ids

        handoff_targets = {h.to_agent_id for h in ir.handoffs}
        assert handoff_targets == {"genomics_analyst"}


class TestTemplateFactoryFullstackMultiAgent:
    """Tests for fullstack multi-agent template generation."""

    def test_create_fullstack_multiagent_defaults(self):
        """Template should include most node types + policy/retry/fallback/schema."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.FULLSTACK_MULTIAGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-fullstack",
            project_name="Fullstack Team",
        )

        assert isinstance(ir, FlowIRv2)
        assert ir.ir_version == "2"
        assert len(ir.agents) >= 5

        node_types = {n.type for a in ir.agents for n in a.graph.nodes}
        assert NodeType.LLM in node_types
        assert NodeType.ROUTER in node_types
        assert NodeType.RETRIEVER in node_types
        assert NodeType.MEMORY in node_types
        assert NodeType.TOOL in node_types
        assert NodeType.OUTPUT in node_types
        assert NodeType.PARALLEL in node_types
        assert NodeType.JOIN in node_types
        assert NodeType.ERROR in node_types

        assert ir.policies is not None
        assert len(ir.handoffs) >= 4
        assert all(h.input_schema is not None for h in ir.handoffs)
        assert all(h.output_schema is not None for h in ir.handoffs)
        assert all(h.input_schema.ref.startswith("schema://") for h in ir.handoffs if h.input_schema)
        assert all(h.output_schema.ref.startswith("schema://") for h in ir.handoffs if h.output_schema)
        assert "handoff_input" in ir.resources.schema_contracts
        assert "handoff_output" in ir.resources.schema_contracts

        supervisor = next(a for a in ir.agents if a.id == "supervisor")
        assert supervisor.retries is not None
        assert supervisor.fallbacks is not None
        assert len(supervisor.fallbacks.llm_chain) >= 1

    def test_create_fullstack_multiagent_strict_schema(self):
        """Strict schema mode should disable soft-fail."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.FULLSTACK_MULTIAGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-fullstack-strict",
            project_name="Fullstack Strict",
            params={"strict_schema": True, "include_mcp_tool": False},
        )
        assert ir.policies.allow_schema_soft_fail is False

        tool_agent = next(a for a in ir.agents if a.id == "toolsmith")
        tool_node = next(n for n in tool_agent.graph.nodes if n.type == NodeType.TOOL)
        assert tool_node.params["tool_name"] == "search"


class TestTemplateFactoryDeterminism:
    """Tests for deterministic template generation."""

    def test_same_inputs_same_output(self):
        """Test same inputs produce identical output."""
        params = {"include_memory": True, "model": "gpt-4"}

        ir1 = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="determinism-test",
            project_name="Determinism Test",
            params=params,
        )
        ir2 = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="determinism-test",
            project_name="Determinism Test",
            params=params,
        )

        # Compare JSON dumps for exact equality
        assert json.dumps(ir1.model_dump(), sort_keys=True) == json.dumps(
            ir2.model_dump(), sort_keys=True
        )

    def test_compute_template_hash(self):
        """Test template hash computation."""
        hash1 = TemplateFactory.compute_template_hash(
            ProjectTemplateId.SIMPLE_AGENT,
            TargetEngine.LANGGRAPH,
            {"include_memory": True},
        )
        hash2 = TemplateFactory.compute_template_hash(
            ProjectTemplateId.SIMPLE_AGENT,
            TargetEngine.LANGGRAPH,
            {"include_memory": True},
        )
        hash3 = TemplateFactory.compute_template_hash(
            ProjectTemplateId.SIMPLE_AGENT,
            TargetEngine.LANGGRAPH,
            {"include_memory": False},  # Different param
        )

        assert hash1 == hash2
        assert hash1 != hash3


class TestTemplateIRSnapshots:
    """Snapshot tests for template IR outputs."""

    def test_blank_langgraph_snapshot(self):
        """Snapshot test for blank + LangGraph."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.BLANK,
            engine=TargetEngine.LANGGRAPH,
            project_id="snapshot-blank-lg",
            project_name="Snapshot Blank LG",
        )

        # Verify structure
        assert ir.ir_version == "2"
        assert ir.flow.id == "snapshot-blank-lg"
        assert len(ir.agents[0].graph.nodes) == 1
        assert ir.agents[0].graph.nodes[0].id == "output"
        assert ir.agents[0].graph.nodes[0].type == NodeType.OUTPUT

    def test_simple_agent_default_snapshot(self):
        """Snapshot test for simple agent defaults."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.SIMPLE_AGENT,
            engine=TargetEngine.LANGGRAPH,
            project_id="snapshot-agent",
            project_name="Snapshot Agent",
        )

        # Verify expected nodes exist
        node_ids = {n.id for n in ir.agents[0].graph.nodes}
        assert "input_processor" in node_ids
        assert "router" in node_ids
        assert "output" in node_ids

        # Verify edges connect properly
        edge_sources = {e.source for e in ir.agents[0].graph.edges}
        edge_targets = {e.target for e in ir.agents[0].graph.edges}
        assert "input_processor" in edge_sources
        assert "output" in edge_targets

    def test_rag_agent_default_snapshot(self):
        """Snapshot test for RAG agent defaults."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.RAG_AGENT,
            engine=TargetEngine.LLAMAINDEX,
            project_id="snapshot-rag",
            project_name="Snapshot RAG",
        )

        # Verify expected nodes exist
        node_ids = {n.id for n in ir.agents[0].graph.nodes}
        assert "input" in node_ids
        assert "retriever" in node_ids
        assert "answer_generator" in node_ids
        assert "output" in node_ids

        # Verify retriever has correct params
        retriever = next(n for n in ir.nodes if n.id == "retriever")
        assert retriever.params["top_k"] == 5
        assert retriever.params["engine"] == "llamaindex"


class TestTemplateFactoryPharmaResearchCopilot:
    """Tests for Pharma Research Copilot template generation."""

    def test_pharma_copilot_in_registry(self):
        """Template must appear in the registry listing."""
        registry = get_template_registry()
        template_ids = registry.list_ids()
        assert ProjectTemplateId.PHARMA_RESEARCH_COPILOT in template_ids

    def test_pharma_copilot_metadata(self):
        """Registry entry should have correct name and tags."""
        registry = get_template_registry()
        tmpl = registry.get(ProjectTemplateId.PHARMA_RESEARCH_COPILOT)
        assert tmpl is not None
        assert tmpl.name == "Pharma Research Copilot (RAG + Tools + QA)"
        assert TargetEngine.LANGGRAPH in tmpl.supported_engines
        tag_labels = {t.label for t in tmpl.tags}
        assert "Pharma/RAG" in tag_labels
        assert "QA" in tag_labels

    def test_pharma_copilot_to_dict(self):
        """to_dict() must serialise without errors."""
        registry = get_template_registry()
        tmpl = registry.get(ProjectTemplateId.PHARMA_RESEARCH_COPILOT)
        assert tmpl is not None
        d = tmpl.to_dict()
        assert d["id"] == "pharma_research_copilot"
        assert d["preview_type"] == "supervisor_workers"
        assert "langgraph" in d["supported_engines"]

    def test_pharma_copilot_create_ir_defaults(self):
        """Factory must produce valid FlowIRv2 with 6 agents."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma",
            project_name="Pharma Copilot",
        )

        assert isinstance(ir, FlowIRv2)
        assert ir.ir_version == "2"

        agent_ids = {a.id for a in ir.agents}
        assert "supervisor" in agent_ids
        assert "researcher" in agent_ids
        assert "toolsmith" in agent_ids
        assert "validator" in agent_ids
        assert "synthesizer" in agent_ids
        assert "reliability" in agent_ids

    def test_pharma_copilot_node_types(self):
        """IR must contain all expected node types across agents."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-nodes",
            project_name="Pharma Nodes",
        )

        node_types = {n.type for a in ir.agents for n in a.graph.nodes}
        assert NodeType.LLM in node_types
        assert NodeType.ROUTER in node_types
        assert NodeType.RETRIEVER in node_types
        assert NodeType.MEMORY in node_types
        assert NodeType.TOOL in node_types
        assert NodeType.OUTPUT in node_types
        assert NodeType.ERROR in node_types

    def test_pharma_copilot_contract_tools_present(self):
        """Contract tool nodes (sql_query, http_request, python_sandbox, s3_get_object) must be declared."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-contracts",
            project_name="Pharma Contracts",
        )

        toolsmith = next(a for a in ir.agents if a.id == "toolsmith")
        tool_names = {
            n.params.get("tool_name")
            for n in toolsmith.graph.nodes
            if n.type == NodeType.TOOL
        }
        assert "sql_query" in tool_names
        assert "http_request" in tool_names
        assert "python_sandbox" in tool_names
        assert "s3_get_object" in tool_names

    def test_pharma_copilot_handoffs_and_schema(self):
        """Supervisor must hand off to all 5 specialists with schema refs."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-handoffs",
            project_name="Pharma Handoffs",
        )

        assert len(ir.handoffs) == 5
        targets = {h.to_agent_id for h in ir.handoffs}
        assert {"researcher", "toolsmith", "validator", "synthesizer", "reliability"} == targets
        assert all(h.input_schema is not None for h in ir.handoffs)
        assert all(h.output_schema is not None for h in ir.handoffs)
        assert "handoff_input" in ir.resources.schema_contracts
        assert "handoff_output" in ir.resources.schema_contracts

    def test_pharma_copilot_policies(self):
        """Global policies must be set and include contract tool names."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-policies",
            project_name="Pharma Policies",
        )

        assert ir.policies is not None
        assert ir.policies.abstain is not None
        assert ir.policies.abstain.enabled is True
        assert ir.policies.redaction is not None
        assert ir.policies.redaction.enabled is True
        for contract in ["sql_query", "http_request", "python_sandbox", "s3_get_object"]:
            assert contract in ir.policies.tool_allowlist

    def test_pharma_copilot_strict_schema(self):
        """strict_schema=True must disable allow_schema_soft_fail."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-strict",
            project_name="Pharma Strict",
            params={"strict_schema": True},
        )
        assert ir.policies.allow_schema_soft_fail is False

    def test_pharma_copilot_llamaindex_not_supported(self):
        """LlamaIndex engine must be rejected for this template."""
        with pytest.raises(TemplateValidationError):
            TemplateFactory.create_ir(
                template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
                engine=TargetEngine.LLAMAINDEX,
                project_id="test-pharma-bad-engine",
                project_name="Bad Engine",
            )

    def test_pharma_copilot_entrypoints(self):
        """Five named entrypoints must be declared (default, no vector)."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-ep",
            project_name="Pharma Entrypoints",
        )

        ep_names = {e.name for e in ir.entrypoints}
        assert {"main", "research", "tools", "validate", "recovery"} == ep_names

    def test_pharma_copilot_vector_db_qdrant(self):
        """vector_db_provider=qdrant adds vector_indexer agent, handoff, and entrypoint."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-vector-qdrant",
            project_name="Pharma Vector Qdrant",
            params={"vector_db_provider": "qdrant"},
        )

        agent_ids = {a.id for a in ir.agents}
        assert "vector_indexer" in agent_ids
        assert len(ir.agents) == 7

        targets = {h.to_agent_id for h in ir.handoffs}
        assert "vector_indexer" in targets
        assert len(ir.handoffs) == 6

        ep_names = {e.name for e in ir.entrypoints}
        assert "vector" in ep_names

        vi = next(a for a in ir.agents if a.id == "vector_indexer")
        tool_names = {n.params.get("tool_name") for n in vi.graph.nodes if n.type == NodeType.TOOL}
        assert "qdrant_vector_ops" in tool_names

        assert "vector_memory" in ir.resources.shared_memory_namespaces
        assert "qdrant_vector_ops" in ir.policies.tool_allowlist

    def test_pharma_copilot_vector_db_pinecone(self):
        """vector_db_provider=pinecone uses pinecone_vector_ops tool."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-vector-pinecone",
            project_name="Pharma Vector Pinecone",
            params={"vector_db_provider": "pinecone"},
        )

        vi = next(a for a in ir.agents if a.id == "vector_indexer")
        tool_names = {n.params.get("tool_name") for n in vi.graph.nodes if n.type == NodeType.TOOL}
        assert "pinecone_vector_ops" in tool_names
        assert "pinecone_vector_ops" in ir.policies.tool_allowlist

    def test_pharma_copilot_vector_db_none_preserves_defaults(self):
        """Default (none) keeps original 6-agent, 5-handoff, 5-entrypoint structure."""
        ir = TemplateFactory.create_ir(
            template_id=ProjectTemplateId.PHARMA_RESEARCH_COPILOT,
            engine=TargetEngine.LANGGRAPH,
            project_id="test-pharma-vector-none",
            project_name="Pharma Vector None",
            params={"vector_db_provider": "none"},
        )

        assert len(ir.agents) == 6
        assert len(ir.handoffs) == 5
        assert len(ir.entrypoints) == 5
        assert "vector_indexer" not in {a.id for a in ir.agents}
        assert "vector_memory" not in ir.resources.shared_memory_namespaces

    def test_pharma_copilot_vector_db_param_in_registry(self):
        """vector_db_provider param must be advertised in the template registry."""
        from agent_compiler.templates.registry import get_template_registry
        registry = get_template_registry()
        tmpl = registry.get(ProjectTemplateId.PHARMA_RESEARCH_COPILOT)
        assert tmpl is not None
        param_names = {p.name for p in tmpl.params}
        assert "vector_db_provider" in param_names
        vp = next(p for p in tmpl.params if p.name == "vector_db_provider")
        assert vp.type == "select"
        assert "qdrant" in (vp.options or [])
        assert "pinecone" in (vp.options or [])
        tag_labels = {t.label for t in tmpl.tags}
        assert "Vector DB" in tag_labels
