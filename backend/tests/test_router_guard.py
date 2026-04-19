"""Tests for Router Guard and abstain/citations functionality."""

import pytest
from agent_compiler.models.ir import (
    RouterGuardMode,
    RouterGuardConfig,
    RouterParams,
)
from agent_compiler.adapters.base import RetrievalResult
from agent_compiler.runtime.context import ExecutionContext, GroundingDecision


class TestRouterGuardConfig:
    """Tests for RouterGuardConfig model."""

    def test_default_config(self):
        """Test default guard config values."""
        config = RouterGuardConfig()
        assert config.min_docs == 1
        assert config.min_top_score == 0.3
        assert config.else_branch == "abstain"

    def test_custom_config(self):
        """Test custom guard config."""
        config = RouterGuardConfig(
            min_docs=3,
            min_top_score=0.5,
            else_branch="fallback",
        )
        assert config.min_docs == 3
        assert config.min_top_score == 0.5
        assert config.else_branch == "fallback"


class TestRouterParams:
    """Tests for RouterParams with guard mode."""

    def test_default_guard_mode(self):
        """Test default guard mode is NONE."""
        params = RouterParams(
            routes={"query": "llm_node"},
            default_route="output",
        )
        assert params.guard_mode == RouterGuardMode.NONE

    def test_retrieval_guard_mode(self):
        """Test setting retrieval guard mode."""
        params = RouterParams(
            routes={"answer": "llm_node"},
            default_route="llm_node",
            guard_mode=RouterGuardMode.RETRIEVAL,
            guard_config=RouterGuardConfig(
                min_docs=2,
                min_top_score=0.4,
                else_branch="abstain_node",
            ),
        )
        assert params.guard_mode == RouterGuardMode.RETRIEVAL
        assert params.guard_config.min_docs == 2
        assert params.guard_config.else_branch == "abstain_node"


class TestRetrievalResult:
    """Tests for enhanced RetrievalResult."""

    def test_basic_retrieval_result(self):
        """Test basic retrieval result."""
        doc = RetrievalResult(
            content="Test content",
            source="test.pdf",
            score=0.85,
        )
        assert doc.content == "Test content"
        assert doc.source == "test.pdf"
        assert doc.score == 0.85

    def test_retrieval_result_with_structured_fields(self):
        """Test retrieval result with structured citation fields."""
        doc = RetrievalResult(
            content="Test content",
            source="test.pdf",
            score=0.85,
            doc_id="doc_123",
            chunk_index=2,
            title="Test Document",
            url="https://example.com/test.pdf",
        )
        assert doc.doc_id == "doc_123"
        assert doc.chunk_index == 2
        assert doc.title == "Test Document"
        assert doc.url == "https://example.com/test.pdf"

    def test_to_citation_with_all_fields(self):
        """Test citation formatting with all fields."""
        doc = RetrievalResult(
            content="Test content",
            source="test.pdf",
            score=0.85,
            doc_id="doc_123",
            title="Test Document",
            chunk_index=1,
        )
        citation = doc.to_citation()
        assert "doc_123" in citation
        assert "Test Document" in citation
        assert "test.pdf" in citation
        assert "Test content" in citation

    def test_to_dict(self):
        """Test to_dict serialization."""
        doc = RetrievalResult(
            content="Test content",
            source="test.pdf",
            score=0.85,
            doc_id="doc_123",
        )
        d = doc.to_dict()
        assert d["content"] == "Test content"
        assert d["source"] == "test.pdf"
        assert d["score"] == 0.85
        assert d["doc_id"] == "doc_123"


class TestGroundingDecision:
    """Tests for GroundingDecision dataclass."""

    def test_should_answer_decision(self):
        """Test decision to answer."""
        decision = GroundingDecision(
            should_answer=True,
            reason="Grounded with relevant docs",
            doc_count=3,
            top_score=0.9,
            citations_used=["doc_1", "doc_2"],
        )
        assert decision.should_answer is True
        assert decision.doc_count == 3
        assert len(decision.citations_used) == 2

    def test_should_abstain_decision(self):
        """Test decision to abstain."""
        decision = GroundingDecision(
            should_answer=False,
            reason="No relevant documents found",
            doc_count=0,
            top_score=0.0,
        )
        assert decision.should_answer is False
        assert decision.citations_used == []


class TestExecutionContextGrounding:
    """Tests for grounding evaluation in ExecutionContext."""

    def test_evaluate_grounding_no_docs(self):
        """Test grounding evaluation with no docs."""
        context = ExecutionContext()
        decision = context.evaluate_grounding(min_docs=1, min_top_score=0.3)

        assert decision.should_answer is False
        assert "Insufficient" in decision.reason
        assert decision.doc_count == 0

    def test_evaluate_grounding_insufficient_docs(self):
        """Test grounding evaluation with insufficient docs."""
        context = ExecutionContext()
        context.add_retrieved_docs([
            RetrievalResult(content="Doc 1", source="test.pdf", score=0.5),
        ])

        decision = context.evaluate_grounding(min_docs=2, min_top_score=0.3)

        assert decision.should_answer is False
        assert "Insufficient" in decision.reason

    def test_evaluate_grounding_low_score(self):
        """Test grounding evaluation with low score."""
        context = ExecutionContext()
        context.add_retrieved_docs([
            RetrievalResult(content="Doc 1", source="test.pdf", score=0.2),
            RetrievalResult(content="Doc 2", source="test2.pdf", score=0.1),
        ])

        decision = context.evaluate_grounding(min_docs=1, min_top_score=0.5)

        assert decision.should_answer is False
        assert "score too low" in decision.reason

    def test_evaluate_grounding_success(self):
        """Test successful grounding evaluation."""
        context = ExecutionContext()
        context.add_retrieved_docs([
            RetrievalResult(content="Doc 1", source="test.pdf", score=0.8, doc_id="doc_1"),
            RetrievalResult(content="Doc 2", source="test2.pdf", score=0.6, doc_id="doc_2"),
            RetrievalResult(content="Doc 3", source="test3.pdf", score=0.2, doc_id="doc_3"),
        ])

        decision = context.evaluate_grounding(min_docs=1, min_top_score=0.5)

        assert decision.should_answer is True
        assert decision.doc_count == 3
        assert decision.top_score == 0.8
        # Only docs above threshold should be in citations
        assert "doc_1" in decision.citations_used
        assert "doc_2" in decision.citations_used
        assert "doc_3" not in decision.citations_used

    def test_grounding_decision_stored_in_context(self):
        """Test that grounding decision is stored in context."""
        context = ExecutionContext()
        context.add_retrieved_docs([
            RetrievalResult(content="Doc 1", source="test.pdf", score=0.8),
        ])

        context.evaluate_grounding(min_docs=1, min_top_score=0.3)

        assert context.grounding_decision is not None
        assert context.grounding_decision.should_answer is True

    def test_to_dict_includes_grounding(self):
        """Test that to_dict includes grounding decision."""
        context = ExecutionContext()
        context.add_retrieved_docs([
            RetrievalResult(content="Doc 1", source="test.pdf", score=0.8),
        ])
        context.evaluate_grounding(min_docs=1, min_top_score=0.3)

        d = context.to_dict()
        assert "grounding" in d
        assert d["grounding"]["should_answer"] is True


class TestContextCitations:
    """Tests for citation handling in context."""

    def test_get_structured_citations(self):
        """Test getting structured citations."""
        context = ExecutionContext()
        context.add_retrieved_docs([
            RetrievalResult(
                content="Doc 1",
                source="test.pdf",
                score=0.8,
                doc_id="doc_1",
                title="Test Doc",
            ),
        ])

        citations = context.get_structured_citations()
        assert len(citations) == 1
        assert citations[0]["doc_id"] == "doc_1"
        assert citations[0]["title"] == "Test Doc"

    def test_mark_citations_used(self):
        """Test marking specific citations as used."""
        context = ExecutionContext()
        context.add_retrieved_docs([
            RetrievalResult(content="Doc 1", source="a.pdf", score=0.8, doc_id="doc_1"),
            RetrievalResult(content="Doc 2", source="b.pdf", score=0.6, doc_id="doc_2"),
            RetrievalResult(content="Doc 3", source="c.pdf", score=0.4, doc_id="doc_3"),
        ])

        context.mark_citations_used(["doc_1", "doc_3"])

        assert len(context.response_citations) == 2
        doc_ids = [c["doc_id"] for c in context.response_citations]
        assert "doc_1" in doc_ids
        assert "doc_3" in doc_ids
        assert "doc_2" not in doc_ids
