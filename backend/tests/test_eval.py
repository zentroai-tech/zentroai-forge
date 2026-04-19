"""Tests for Eval Suites and Assertions functionality."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from agent_compiler.models.db import AssertionType
from agent_compiler.services.eval_service import AssertionEngine, EvalService


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with session_factory() as test_session:
        yield test_session

    await engine.dispose()


class TestAssertionEngine:
    """Tests for the AssertionEngine."""

    def test_contains_assertion_pass(self):
        """Test contains assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.CONTAINS.value, "expected": "hello"},
            output={"output": "hello world"},
        )
        assert result["passed"] is True

    def test_contains_assertion_fail(self):
        """Test contains assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.CONTAINS.value, "expected": "goodbye"},
            output={"output": "hello world"},
        )
        assert result["passed"] is False

    def test_not_contains_assertion_pass(self):
        """Test not_contains assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.NOT_CONTAINS.value, "expected": "error"},
            output={"output": "success"},
        )
        assert result["passed"] is True

    def test_not_contains_assertion_fail(self):
        """Test not_contains assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.NOT_CONTAINS.value, "expected": "success"},
            output={"output": "success"},
        )
        assert result["passed"] is False

    def test_equals_assertion_pass(self):
        """Test equals assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.EQUALS.value, "expected": "test"},
            output={"output": "test"},
        )
        assert result["passed"] is True

    def test_equals_assertion_fail(self):
        """Test equals assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.EQUALS.value, "expected": "test"},
            output={"output": "different"},
        )
        assert result["passed"] is False

    def test_regex_assertion_pass(self):
        """Test regex assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.REGEX.value, "expected": r"\d{3}-\d{4}"},
            output={"output": "Phone: 123-4567"},
        )
        assert result["passed"] is True

    def test_regex_assertion_fail(self):
        """Test regex assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.REGEX.value, "expected": r"\d{3}-\d{4}"},
            output={"output": "No phone number"},
        )
        assert result["passed"] is False

    def test_json_path_assertion_pass(self):
        """Test json_path assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.JSON_PATH.value,
                "path": "nested.value",
                "expected": 42,
            },
            output={"nested": {"value": 42}},
        )
        assert result["passed"] is True

    def test_json_path_assertion_fail(self):
        """Test json_path assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.JSON_PATH.value,
                "path": "nested.value",
                "expected": 42,
            },
            output={"nested": {"value": 100}},
        )
        assert result["passed"] is False

    def test_grounded_assertion_pass(self):
        """Test grounded assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.GROUNDED.value},
            output={"grounded": True, "abstained": False},
        )
        assert result["passed"] is True

    def test_grounded_assertion_fail_when_abstained(self):
        """Test grounded assertion fails when abstained."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.GROUNDED.value},
            output={"grounded": True, "abstained": True},
        )
        assert result["passed"] is False

    def test_abstained_assertion_pass(self):
        """Test abstained assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.ABSTAINED.value},
            output={"abstained": True},
        )
        assert result["passed"] is True

    def test_abstained_assertion_fail(self):
        """Test abstained assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.ABSTAINED.value},
            output={"abstained": False},
        )
        assert result["passed"] is False

    def test_min_citations_assertion_pass(self):
        """Test min_citations assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.MIN_CITATIONS.value, "expected": 2},
            output={"citations": [{"id": 1}, {"id": 2}, {"id": 3}]},
        )
        assert result["passed"] is True

    def test_min_citations_assertion_fail(self):
        """Test min_citations assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.MIN_CITATIONS.value, "expected": 3},
            output={"citations": [{"id": 1}]},
        )
        assert result["passed"] is False

    def test_latency_assertion_pass(self):
        """Test latency assertion passes."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.LATENCY_MS.value, "expected": 1000},
            output={},
            run_metadata={"duration_ms": 500},
        )
        assert result["passed"] is True

    def test_latency_assertion_fail(self):
        """Test latency assertion fails."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.LATENCY_MS.value, "expected": 100},
            output={},
            run_metadata={"duration_ms": 500},
        )
        assert result["passed"] is False

    def test_custom_field_assertion(self):
        """Test assertion on custom field."""
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.EQUALS.value,
                "field": "custom_field",
                "expected": "custom_value",
            },
            output={"custom_field": "custom_value"},
        )
        assert result["passed"] is True

    def test_nested_field_assertion(self):
        """Test assertion on nested field with dot notation."""
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.CONTAINS.value,
                "field": "response.message",
                "expected": "success",
            },
            output={"response": {"message": "operation success"}},
        )
        assert result["passed"] is True

    def test_unknown_assertion_type(self):
        """Test unknown assertion type."""
        result = AssertionEngine.evaluate(
            assertion={"type": "unknown_type", "expected": "test"},
            output={"output": "test"},
        )
        assert result["passed"] is False
        assert "Unknown assertion type" in result["message"]

    def test_assertion_result_structure(self):
        """Test assertion result has all required fields."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.CONTAINS.value, "expected": "test"},
            output={"output": "test value"},
        )
        assert "type" in result
        assert "field" in result
        assert "expected" in result
        assert "actual" in result
        assert "passed" in result
        assert "message" in result


class TestAssertionEngineEdgeCases:
    """Tests for edge cases in AssertionEngine."""

    def test_none_output_field(self):
        """Test handling of None output field."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.CONTAINS.value, "expected": "test"},
            output={"other": "value"},  # 'output' field missing
        )
        assert result["passed"] is False

    def test_empty_string_output(self):
        """Test handling of empty string output."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.CONTAINS.value, "expected": "test"},
            output={"output": ""},
        )
        assert result["passed"] is False

    def test_json_path_not_found(self):
        """Test json_path with non-existent path."""
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.JSON_PATH.value,
                "path": "does.not.exist",
                "expected": "value",
            },
            output={"other": "data"},
        )
        assert result["passed"] is False
        assert "not found" in result["message"]

    def test_contains_on_none_returns_false(self):
        """Test contains assertion on None field returns false."""
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.CONTAINS.value,
                "field": "missing",
                "expected": "test",
            },
            output={"output": "test"},
        )
        assert result["passed"] is False

    def test_not_contains_on_none_returns_true(self):
        """Test not_contains on None field returns true (None doesn't contain anything)."""
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.NOT_CONTAINS.value,
                "field": "missing",
                "expected": "test",
            },
            output={"output": "test"},
        )
        assert result["passed"] is True


class TestEvalServiceCaseCrud:
    """Tests for eval case update/delete service methods."""

    @pytest.mark.asyncio
    async def test_update_case_updates_payload_fields(self, session: AsyncSession):
        service = EvalService(session)
        suite = await service.create_suite(flow_id="flow_eval", name="Suite", description="", config={})
        case = await service.create_case(
            suite_id=suite.id,
            name="Case A",
            input_data={"input": "hello"},
            expected_data={"output": "world"},
            assertions=[{"type": AssertionType.CONTAINS.value, "expected": "world"}],
            tags=["smoke"],
        )

        updated = await service.update_case(
            case.id,
            name="Case B",
            input_data={"input": "updated"},
            expected_data={"output": "updated"},
            assertions=[{"type": AssertionType.EQUALS.value, "expected": "updated"}],
            tags=["regression"],
        )

        assert updated is not None
        assert updated.name == "Case B"
        assert updated.input_data == {"input": "updated"}
        assert updated.expected_data == {"output": "updated"}
        assert updated.assertions == [{"type": AssertionType.EQUALS.value, "expected": "updated"}]
        assert "regression" in (updated.tags or "")

    @pytest.mark.asyncio
    async def test_delete_case_removes_case(self, session: AsyncSession):
        service = EvalService(session)
        suite = await service.create_suite(flow_id="flow_eval", name="Suite", description="", config={})
        case = await service.create_case(
            suite_id=suite.id,
            name="Case A",
            input_data={"input": "hello"},
        )

        deleted = await service.delete_case(case.id)
        missing = await service.get_case(case.id)
        deleted_again = await service.delete_case(case.id)

        assert deleted is True
        assert missing is None
        assert deleted_again is False

    def test_latency_without_metadata(self):
        """Test latency assertion without metadata."""
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.LATENCY_MS.value, "expected": 1000},
            output={},
            run_metadata=None,
        )
        assert result["passed"] is False
        assert "No latency data" in result["message"]


class TestAssertionEngineV21:
    """Tests for v2.1 assertion types and event normalization."""

    def test_agent_handoff_normalizes_event_type_case(self):
        result = AssertionEngine.evaluate(
            assertion={
                "type": AssertionType.AGENT_HANDOFF.value,
                "from_agent": "supervisor",
                "to_agent": "writer",
            },
            output={},
            run_metadata={
                "agent_events": [
                    {
                        "event_type": "HANDOFF",
                        "agent_id": "supervisor",
                        "data": {"from_agent": "supervisor", "to_agent": "writer"},
                    }
                ]
            },
        )
        assert result["passed"] is True

    def test_budget_under_uses_lowercase_runtime_events(self):
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.BUDGET_UNDER.value},
            output={},
            run_metadata={
                "agent_events": [
                    {"event_type": "budget_warning", "agent_id": "supervisor", "data": {}}
                ]
            },
        )
        assert result["passed"] is True

    def test_retry_used_assertion_passes_with_min_count(self):
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.RETRY_USED.value, "min_count": 2},
            output={},
            run_metadata={
                "agent_events": [
                    {"event_type": "retry_attempt", "agent_id": "supervisor", "data": {}},
                    {"event_type": "retry_attempt", "agent_id": "supervisor", "data": {}},
                ]
            },
        )
        assert result["passed"] is True
        assert result["actual"] == 2

    def test_fallback_used_assertion_filters_agent(self):
        result = AssertionEngine.evaluate(
            assertion={"type": AssertionType.FALLBACK_USED.value, "agent_id": "writer"},
            output={},
            run_metadata={
                "agent_events": [
                    {"event_type": "fallback_used", "agent_id": "writer", "data": {}}
                ]
            },
        )
        assert result["passed"] is True

    def test_no_schema_errors_and_no_guard_block(self):
        schema_ok = AssertionEngine.evaluate(
            assertion={"type": AssertionType.NO_SCHEMA_ERRORS.value},
            output={},
            run_metadata={"agent_events": []},
        )
        guard_ok = AssertionEngine.evaluate(
            assertion={"type": AssertionType.NO_GUARD_BLOCK.value},
            output={},
            run_metadata={"agent_events": []},
        )
        assert schema_ok["passed"] is True
        assert guard_ok["passed"] is True
