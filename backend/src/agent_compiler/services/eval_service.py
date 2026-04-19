"""Eval suites runner service with assertion engine.

Supports running test cases against flows with various assertions.
"""

import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import (
    AgentEventRecord,
    AssertionType,
    CaseResultStatus,
    EvalCase,
    EvalCaseResult,
    EvalRun,
    EvalRunStatus,
    EvalSuite,
    FlowRecord,
    StepRecord,
)
from agent_compiler.models.ir import parse_ir
from agent_compiler.models.ir_v2 import FlowIRv2
from agent_compiler.observability.logging import get_logger
from agent_compiler.runtime.executor import FlowExecutor

logger = get_logger(__name__)


class AssertionError(Exception):
    """Raised when an assertion fails."""

    def __init__(self, assertion_type: str, message: str, expected: Any, actual: Any):
        self.assertion_type = assertion_type
        self.message = message
        self.expected = expected
        self.actual = actual
        super().__init__(message)


class AssertionEngine:
    """Engine for evaluating assertions on flow outputs."""

    @staticmethod
    def evaluate(
        assertion: dict[str, Any],
        output: dict[str, Any],
        run_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a single assertion.

        Args:
            assertion: Assertion definition with type and expected value
            output: The actual output from the flow
            run_metadata: Optional metadata about the run (timing, etc.)

        Returns:
            Dictionary with assertion result
        """
        assertion_type = assertion.get("type")
        expected = assertion.get("expected")
        field = assertion.get("field", "output")  # Default to 'output' field

        # Get the actual value from the output
        actual = AssertionEngine._get_field_value(output, field)

        result = {
            "type": assertion_type,
            "field": field,
            "expected": expected,
            "actual": actual,
            "passed": False,
            "message": "",
        }

        try:
            agent_events = run_metadata.get("agent_events", []) if run_metadata else []
            normalized_event_types = [
                str(evt.get("event_type", "")).lower() for evt in agent_events
            ]

            if assertion_type == AssertionType.CONTAINS.value:
                if actual is None:
                    result["message"] = f"Field '{field}' is None"
                elif expected in str(actual):
                    result["passed"] = True
                    result["message"] = f"Output contains '{expected}'"
                else:
                    result["message"] = f"Output does not contain '{expected}'"

            elif assertion_type == AssertionType.NOT_CONTAINS.value:
                if actual is None:
                    result["passed"] = True
                    result["message"] = f"Field '{field}' is None (not containing anything)"
                elif expected not in str(actual):
                    result["passed"] = True
                    result["message"] = f"Output does not contain '{expected}'"
                else:
                    result["message"] = f"Output contains '{expected}' but should not"

            elif assertion_type == AssertionType.EQUALS.value:
                if actual == expected:
                    result["passed"] = True
                    result["message"] = "Output equals expected value"
                else:
                    result["message"] = f"Expected '{expected}', got '{actual}'"

            elif assertion_type == AssertionType.REGEX.value:
                pattern = re.compile(expected)
                if actual is not None and pattern.search(str(actual)):
                    result["passed"] = True
                    result["message"] = f"Output matches pattern '{expected}'"
                else:
                    result["message"] = f"Output does not match pattern '{expected}'"

            elif assertion_type == AssertionType.JSON_PATH.value:
                json_path = assertion.get("path", "")
                try:
                    value = AssertionEngine._get_json_path_value(output, json_path)
                    result["actual"] = value
                    if value == expected:
                        result["passed"] = True
                        result["message"] = f"JSON path '{json_path}' equals expected"
                    else:
                        result["message"] = f"JSON path '{json_path}': expected '{expected}', got '{value}'"
                except (KeyError, IndexError, TypeError) as e:
                    result["message"] = f"JSON path '{json_path}' not found: {e}"

            elif assertion_type == AssertionType.GROUNDED.value:
                grounded = output.get("grounded", False)
                abstained = output.get("abstained", False)
                if grounded and not abstained:
                    result["passed"] = True
                    result["message"] = "Response is grounded"
                else:
                    result["message"] = f"Response is not grounded (grounded={grounded}, abstained={abstained})"

            elif assertion_type == AssertionType.ABSTAINED.value:
                abstained = output.get("abstained", False)
                if abstained:
                    result["passed"] = True
                    result["message"] = "Response abstained as expected"
                else:
                    result["message"] = "Response did not abstain"

            elif assertion_type == AssertionType.MIN_CITATIONS.value:
                citations = output.get("citations", [])
                min_count = int(expected)
                if len(citations) >= min_count:
                    result["passed"] = True
                    result["message"] = f"Has {len(citations)} citations (>= {min_count})"
                else:
                    result["message"] = f"Only {len(citations)} citations (< {min_count})"

            elif assertion_type == AssertionType.LATENCY_MS.value:
                if run_metadata and "duration_ms" in run_metadata:
                    actual_ms = run_metadata["duration_ms"]
                    result["actual"] = actual_ms
                    max_ms = float(expected)
                    if actual_ms <= max_ms:
                        result["passed"] = True
                        result["message"] = f"Latency {actual_ms:.1f}ms <= {max_ms}ms"
                    else:
                        result["message"] = f"Latency {actual_ms:.1f}ms > {max_ms}ms"
                else:
                    result["message"] = "No latency data available"

            elif assertion_type == AssertionType.LLM_JUDGE.value:
                # LLM-as-Judge: uses a model to evaluate the output quality.
                # Config keys in assertion:
                #   model: judge model (default "gemini-2.5-flash")
                #   criteria: what to evaluate (default "relevance, coherence, helpfulness")
                #   rubric: optional scoring rubric
                #   threshold: minimum score 1-5 to pass (default 3)
                judge_result = AssertionEngine._run_llm_judge(
                    assertion=assertion,
                    output=output,
                    actual=actual,
                )
                result.update(judge_result)

            elif assertion_type == AssertionType.AGENT_HANDOFF.value:
                # Verify a handoff event exists in agent_events
                from_agent = assertion.get("from_agent")
                to_agent = assertion.get("to_agent", expected)
                handoff_found = any(
                    str(evt.get("event_type", "")).lower() == "handoff"
                    and (not from_agent or evt.get("data", {}).get("from_agent") == from_agent)
                    and (not to_agent or evt.get("data", {}).get("to_agent") == to_agent)
                    for evt in agent_events
                )
                if handoff_found:
                    result["passed"] = True
                    result["message"] = f"Handoff to '{to_agent}' occurred"
                else:
                    result["message"] = f"Expected handoff to '{to_agent}' not found"

            elif assertion_type == AssertionType.AGENT_ISOLATION.value:
                # Verify agent only used allowed tools
                agent_id = assertion.get("agent_id", expected)
                allowed_tools = assertion.get("allowed_tools", [])
                steps = run_metadata.get("steps", []) if run_metadata else []
                violations = []
                for step in steps:
                    if (
                        step.get("agent_id") == agent_id
                        and step.get("node_type") == "Tool"
                    ):
                        tool_name = step.get("output", {}).get("tool_name", "")
                        if allowed_tools and tool_name not in allowed_tools:
                            violations.append(tool_name)
                if not violations:
                    result["passed"] = True
                    result["message"] = f"Agent '{agent_id}' used only allowed tools"
                else:
                    result["message"] = (
                        f"Agent '{agent_id}' used disallowed tools: {violations}"
                    )

            elif assertion_type == AssertionType.BUDGET_UNDER.value:
                # Verify tokens/tool_calls under budget threshold
                budget_exceeded = "budget_exceeded" in normalized_event_types
                if not budget_exceeded:
                    result["passed"] = True
                    result["message"] = "No budget exceeded"
                else:
                    result["message"] = "Budget was exceeded"

            elif assertion_type == AssertionType.RETRY_USED.value:
                # Verify retry attempts occurred (optionally for a specific agent)
                agent_id = assertion.get("agent_id")
                min_count = int(assertion.get("min_count", expected or 1))
                retry_events = [
                    evt
                    for evt in agent_events
                    if str(evt.get("event_type", "")).lower() == "retry_attempt"
                    and (not agent_id or evt.get("agent_id") == agent_id)
                ]
                actual_count = len(retry_events)
                result["actual"] = actual_count
                result["expected"] = min_count
                if actual_count >= min_count:
                    result["passed"] = True
                    result["message"] = (
                        f"Observed {actual_count} retry events"
                        + (f" for agent '{agent_id}'" if agent_id else "")
                    )
                else:
                    result["message"] = (
                        f"Expected at least {min_count} retry events, got {actual_count}"
                    )

            elif assertion_type == AssertionType.FALLBACK_USED.value:
                # Verify fallback was used (optionally for a specific agent)
                agent_id = assertion.get("agent_id")
                fallback_found = any(
                    str(evt.get("event_type", "")).lower() == "fallback_used"
                    and (not agent_id or evt.get("agent_id") == agent_id)
                    for evt in agent_events
                )
                if fallback_found:
                    result["passed"] = True
                    result["message"] = (
                        "Fallback was used"
                        + (f" by agent '{agent_id}'" if agent_id else "")
                    )
                else:
                    result["message"] = (
                        "Expected fallback_used event not found"
                        + (f" for agent '{agent_id}'" if agent_id else "")
                    )

            elif assertion_type == AssertionType.NO_SCHEMA_ERRORS.value:
                # Verify schema validation did not fail
                has_schema_errors = "schema_validation_error" in normalized_event_types
                if not has_schema_errors:
                    result["passed"] = True
                    result["message"] = "No schema validation errors"
                else:
                    result["message"] = "Schema validation errors were emitted"

            elif assertion_type == AssertionType.NO_GUARD_BLOCK.value:
                # Verify policy guard did not block the run
                has_guard_block = "guard_block" in normalized_event_types
                if not has_guard_block:
                    result["passed"] = True
                    result["message"] = "No guard blocks"
                else:
                    result["message"] = "Guard block events were emitted"

            elif assertion_type == AssertionType.SCHEMA_VALID.value:
                # Validate output against an inline JSON schema
                schema = assertion.get("schema") or {}
                target = actual if actual is not None else output
                try:
                    try:
                        import jsonschema  # type: ignore[import]
                        jsonschema.validate(instance=target, schema=schema)
                        result["passed"] = True
                        result["message"] = "Output is schema-valid"
                    except ImportError:
                        # Fallback: check required keys and basic types
                        required = schema.get("required", [])
                        props = schema.get("properties", {})
                        missing = [k for k in required if k not in (target or {})]
                        if missing:
                            result["message"] = f"Missing required fields: {missing}"
                        else:
                            type_errors = []
                            for prop, spec in props.items():
                                if prop in (target or {}):
                                    expected_type = spec.get("type")
                                    _type_map = {
                                        "string": str, "number": (int, float),
                                        "integer": int, "boolean": bool,
                                        "array": list, "object": dict,
                                    }
                                    if expected_type and expected_type in _type_map:
                                        if not isinstance(target[prop], _type_map[expected_type]):
                                            type_errors.append(prop)
                            if type_errors:
                                result["message"] = f"Type mismatch for fields: {type_errors}"
                            else:
                                result["passed"] = True
                                result["message"] = "Output is schema-valid (lite check)"
                except Exception as e:
                    result["message"] = f"Schema validation error: {e}"

            elif assertion_type == AssertionType.CITATION_REQUIRED.value:
                # Heuristic: look for citation markers in output text
                text_to_check = str(actual) if actual is not None else str(output)
                citation_patterns = [
                    r"\[\d+\]",           # [1], [2]
                    r"\(\w[\w\s]*,\s*\d{4}\)",  # (Author, 2024)
                    r"https?://\S+",      # URLs as citations
                    r"Source:",           # "Source:" prefix
                    r"Reference:",        # "Reference:" prefix
                    r"\bsee\b.{0,80}\b(section|chapter|table|figure)\b",
                ]
                import re as _re2
                found = any(_re2.search(p, text_to_check, _re2.IGNORECASE) for p in citation_patterns)
                if found:
                    result["passed"] = True
                    result["message"] = "Output contains citation markers"
                else:
                    result["message"] = "No citation markers found in output"

            elif assertion_type == AssertionType.ABSTAIN_CORRECTNESS.value:
                # Check that abstained flag matches expected_abstain from dataset
                abstained = output.get("abstained", False)
                expected_abstain = expected  # from assertion's "expected" field
                if expected_abstain is None:
                    # Try reading from the outer expected dict
                    expected_abstain = (run_metadata or {}).get("expected_abstain")
                if expected_abstain is None:
                    result["message"] = "No expected_abstain value provided"
                elif bool(abstained) == bool(expected_abstain):
                    result["passed"] = True
                    result["message"] = (
                        f"Abstain correctness OK: abstained={abstained}"
                    )
                else:
                    result["message"] = (
                        f"Expected abstained={expected_abstain}, got abstained={abstained}"
                    )

            elif assertion_type == AssertionType.TOOL_SUCCESS_RATE.value:
                # Check tool call success rate >= threshold
                min_rate = float(expected) if expected is not None else 1.0
                steps = (run_metadata or {}).get("steps", [])
                tool_steps = [s for s in steps if (s.get("node_type") or "").upper() == "TOOL"]
                if not tool_steps:
                    result["passed"] = True
                    result["message"] = "No tool steps (vacuously true)"
                    result["actual"] = 1.0
                else:
                    succeeded = sum(
                        1 for s in tool_steps
                        if (s.get("output") or {}).get("success", True)
                        and not (s.get("output") or {}).get("error")
                    )
                    rate = succeeded / len(tool_steps)
                    result["actual"] = rate
                    if rate >= min_rate:
                        result["passed"] = True
                        result["message"] = f"Tool success rate {rate:.0%} >= {min_rate:.0%}"
                    else:
                        result["message"] = f"Tool success rate {rate:.0%} < {min_rate:.0%}"

            else:
                result["message"] = f"Unknown assertion type: {assertion_type}"

        except Exception as e:
            result["message"] = f"Assertion error: {e}"

        return result

    @staticmethod
    def _run_llm_judge(
        assertion: dict[str, Any],
        output: dict[str, Any],
        actual: Any,
    ) -> dict[str, Any]:
        """Run LLM-as-Judge evaluation (sync wrapper).

        Returns dict with: passed, message, score, reasoning
        """
        import asyncio

        async def _judge():
            model = assertion.get("model", "gemini-2.5-flash")
            criteria = assertion.get(
                "criteria", "relevance, coherence, helpfulness"
            )
            rubric = assertion.get("rubric", "")
            threshold = int(assertion.get("threshold", 3))

            prompt = (
                "You are an expert evaluator. Rate the following AI response on a scale of 1-5.\n\n"
                f"Criteria: {criteria}\n"
            )
            if rubric:
                prompt += f"Rubric:\n{rubric}\n"
            prompt += (
                f"\nResponse to evaluate:\n{actual}\n\n"
                "Reply ONLY with a JSON object: {\"score\": <1-5>, \"reasoning\": \"<brief explanation>\"}"
            )

            try:
                from agent_compiler.adapters.langchain_adapter import (
                    build_chat_model,
                )

                # Determine provider from model name
                provider = "openai"
                if model.startswith("gemini"):
                    provider = "gemini"
                elif model.startswith("claude"):
                    provider = "anthropic"

                import os

                api_key = None
                if provider == "gemini":
                    api_key = os.environ.get("GOOGLE_API_KEY")
                elif provider == "openai":
                    api_key = os.environ.get("OPENAI_API_KEY")
                elif provider == "anthropic":
                    api_key = os.environ.get("ANTHROPIC_API_KEY")

                llm = build_chat_model(
                    model=model,
                    temperature=0.0,
                    api_key=api_key,
                    provider=provider,
                )

                from langchain_core.messages import HumanMessage

                response = await llm.ainvoke([HumanMessage(content=prompt)])
                text = response.content if hasattr(response, "content") else str(response)

                # Parse JSON from response
                import re as _re

                json_match = _re.search(r"\{[^}]+\}", text)
                if json_match:
                    judge_data = json.loads(json_match.group())
                    score = int(judge_data.get("score", 0))
                    reasoning = judge_data.get("reasoning", "")
                else:
                    return {
                        "passed": False,
                        "message": f"Judge response not parseable: {text[:200]}",
                        "score": 0,
                        "reasoning": text[:200],
                    }

                return {
                    "passed": score >= threshold,
                    "message": f"Judge score: {score}/5 (threshold: {threshold})",
                    "score": score,
                    "reasoning": reasoning,
                    "model": model,
                }

            except ImportError as e:
                return {
                    "passed": False,
                    "message": f"LLM judge dependency missing: {e}",
                }
            except Exception as e:
                return {
                    "passed": False,
                    "message": f"LLM judge error: {e}",
                }

        # Run the async judge. This static method is called from async context
        # via _run_case, but evaluate() is synchronous. We store the coroutine
        # and the caller (evaluate_async) handles awaiting it.
        # For synchronous fallback, use asyncio.run.
        try:
            loop = asyncio.get_running_loop()
            # Can't use asyncio.run inside running loop — return a sentinel
            # The async caller should use evaluate_async instead
            return {"_async_coro": _judge(), "passed": False, "message": "pending async evaluation"}
        except RuntimeError:
            return asyncio.run(_judge())

    @staticmethod
    async def evaluate_async(
        assertion: dict[str, Any],
        output: dict[str, Any],
        run_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Async version of evaluate — handles LLM_JUDGE coroutines."""
        result = AssertionEngine.evaluate(assertion, output, run_metadata)
        # If the result contains an async coroutine (from LLM judge), await it
        if "_async_coro" in result:
            coro = result.pop("_async_coro")
            judge_result = await coro
            result.update(judge_result)
        return result

    @staticmethod
    def _get_field_value(output: dict[str, Any], field: str) -> Any:
        """Get a field value from output using dot notation."""
        if "." not in field:
            return output.get(field)

        parts = field.split(".")
        value = output
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit():
                idx = int(part)
                value = value[idx] if idx < len(value) else None
            else:
                return None
        return value

    @staticmethod
    def _get_json_path_value(data: dict[str, Any], path: str) -> Any:
        """Get a value from data using a simple JSON path."""
        # Simple path parsing (e.g., "grounding.top_score" or "citations.0.source")
        parts = path.split(".")
        value = data
        for part in parts:
            if isinstance(value, dict):
                value = value[part]
            elif isinstance(value, list) and part.isdigit():
                value = value[int(part)]
            else:
                raise KeyError(f"Cannot access '{part}' in {type(value)}")
        return value


class EvalService:
    """Service for managing and running eval suites."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================================
    # Suite CRUD
    # =========================================================================

    async def create_suite(
        self,
        flow_id: str,
        name: str,
        description: str = "",
        config: dict[str, Any] | None = None,
    ) -> EvalSuite:
        """Create a new eval suite."""
        suite = EvalSuite(
            id=f"suite_{uuid.uuid4().hex[:12]}",
            flow_id=flow_id,
            name=name,
            description=description,
            config_json=json.dumps(config or {}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self.session.add(suite)
        await self.session.commit()
        await self.session.refresh(suite)

        logger.info(f"Created eval suite: {suite.id}")
        return suite

    async def get_suite(self, suite_id: str) -> EvalSuite | None:
        """Get a suite by ID."""
        statement = select(EvalSuite).where(EvalSuite.id == suite_id)
        result = await self.session.exec(statement)
        return result.one_or_none()

    async def list_suites(
        self,
        flow_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EvalSuite]:
        """List eval suites."""
        statement = select(EvalSuite)
        if flow_id:
            statement = statement.where(EvalSuite.flow_id == flow_id)
        statement = statement.limit(limit).offset(offset)

        result = await self.session.exec(statement)
        return list(result.all())

    async def delete_suite(self, suite_id: str) -> bool:
        """Delete a suite and all its cases."""
        suite = await self.get_suite(suite_id)
        if not suite:
            return False

        await self.session.delete(suite)
        await self.session.commit()
        return True

    # =========================================================================
    # Case CRUD
    # =========================================================================

    async def create_case(
        self,
        suite_id: str,
        name: str,
        input_data: dict[str, Any],
        expected_data: dict[str, Any] | None = None,
        assertions: list[dict[str, Any]] | None = None,
        description: str = "",
        tags: list[str] | None = None,
    ) -> EvalCase:
        """Create a new test case."""
        case = EvalCase(
            id=f"case_{uuid.uuid4().hex[:12]}",
            suite_id=suite_id,
            name=name,
            description=description,
            input_json=json.dumps(input_data),
            expected_json=json.dumps(expected_data or {}),
            assertions_json=json.dumps(assertions or []),
            tags=json.dumps(tags or []),
            created_at=datetime.now(timezone.utc),
        )

        self.session.add(case)
        await self.session.commit()
        await self.session.refresh(case)

        logger.info(f"Created eval case: {case.id}")
        return case

    async def get_case(self, case_id: str) -> EvalCase | None:
        """Get a case by ID."""
        statement = select(EvalCase).where(EvalCase.id == case_id)
        result = await self.session.exec(statement)
        return result.one_or_none()

    async def update_case(
        self,
        case_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        input_data: dict[str, Any] | None = None,
        expected_data: dict[str, Any] | None = None,
        assertions: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
    ) -> EvalCase | None:
        """Update an existing eval case."""
        case = await self.get_case(case_id)
        if not case:
            return None

        if name is not None:
            case.name = name
        if description is not None:
            case.description = description
        if input_data is not None:
            case.input_data = input_data
        if expected_data is not None:
            case.expected_data = expected_data
        if assertions is not None:
            case.assertions = assertions
        if tags is not None:
            case.tags = json.dumps(tags)

        self.session.add(case)
        await self.session.commit()
        await self.session.refresh(case)
        return case

    async def delete_case(self, case_id: str) -> bool:
        """Delete a test case."""
        case = await self.get_case(case_id)
        if not case:
            return False

        await self.session.delete(case)
        await self.session.commit()
        return True

    async def list_cases(
        self,
        suite_id: str,
        tags: list[str] | None = None,
    ) -> list[EvalCase]:
        """List cases in a suite."""
        statement = select(EvalCase).where(EvalCase.suite_id == suite_id)
        result = await self.session.exec(statement)
        cases = list(result.all())

        # Filter by tags if provided
        if tags:
            filtered = []
            for case in cases:
                case_tags = json.loads(case.tags) if case.tags else []
                if any(t in case_tags for t in tags):
                    filtered.append(case)
            return filtered

        return cases

    # =========================================================================
    # Suite Runner
    # =========================================================================

    async def run_suite(
        self,
        suite_id: str,
        tags: list[str] | None = None,
    ) -> EvalRun:
        """Run all cases in a suite.

        Args:
            suite_id: The suite to run
            tags: Optional filter to run only cases with specific tags

        Returns:
            EvalRun record with results
        """
        # Get suite
        suite = await self.get_suite(suite_id)
        if not suite:
            raise ValueError(f"Suite not found: {suite_id}")

        # Get flow
        statement = select(FlowRecord).where(FlowRecord.id == suite.flow_id)
        result = await self.session.exec(statement)
        flow = result.one_or_none()
        if not flow:
            raise ValueError(f"Flow not found: {suite.flow_id}")

        # Parse flow IR (supports v1 and v2)
        flow_ir = parse_ir(json.loads(flow.ir_json))

        # Get cases
        cases = await self.list_cases(suite_id, tags=tags)
        if not cases:
            raise ValueError(f"No cases found in suite: {suite_id}")

        # Create eval run
        eval_run = EvalRun(
            id=f"eval_run_{uuid.uuid4().hex[:12]}",
            suite_id=suite_id,
            status=EvalRunStatus.RUNNING,
            total_cases=len(cases),
            started_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(eval_run)
        await self.session.commit()

        logger.info(f"Starting eval run {eval_run.id} with {len(cases)} cases")

        # Run each case
        executor = FlowExecutor(self.session)
        passed = 0
        failed = 0

        for case in cases:
            case_result = await self._run_case(
                eval_run=eval_run,
                case=case,
                flow_ir=flow_ir,
                executor=executor,
            )

            if case_result.status == CaseResultStatus.PASSED:
                passed += 1
            else:
                failed += 1

        # Update eval run
        eval_run.status = EvalRunStatus.COMPLETED
        eval_run.passed_cases = passed
        eval_run.failed_cases = failed
        eval_run.finished_at = datetime.now(timezone.utc)

        # Threshold gating: read min_pass_rate from suite config
        thresholds = suite.config.get("thresholds", {})
        min_pass_rate = thresholds.get("min_pass_rate", 0.0)
        pass_rate = passed / len(cases) if cases else 1.0
        eval_run.gate_passed = pass_rate >= min_pass_rate

        # Build downloadable report
        eval_run.report_json = json.dumps({
            "eval_run_id": eval_run.id,
            "suite_id": suite_id,
            "suite_name": suite.name,
            "total_cases": len(cases),
            "passed_cases": passed,
            "failed_cases": failed,
            "pass_rate": pass_rate,
            "gate_passed": eval_run.gate_passed,
            "thresholds": thresholds,
            "started_at": eval_run.started_at.isoformat() if eval_run.started_at else None,
            "finished_at": eval_run.finished_at.isoformat() if eval_run.finished_at else None,
        })

        self.session.add(eval_run)
        await self.session.commit()
        await self.session.refresh(eval_run)

        logger.info(
            f"Eval run {eval_run.id} completed: {passed}/{len(cases)} passed "
            f"(gate_passed={eval_run.gate_passed})"
        )
        return eval_run

    async def _run_case(
        self,
        eval_run: EvalRun,
        case: EvalCase,
        flow_ir: FlowIRv2,
        executor: FlowExecutor,
    ) -> EvalCaseResult:
        """Run a single test case."""
        start_time = time.time()

        case_result = EvalCaseResult(
            id=f"result_{uuid.uuid4().hex[:12]}",
            eval_run_id=eval_run.id,
            case_id=case.id,
            status=CaseResultStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        try:
            # Execute the flow
            run = await executor.execute(flow_ir, case.input_data)
            case_result.run_id = run.id

            # Get output
            output = json.loads(run.output_json) if run.output_json else {}

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            case_result.duration_ms = duration_ms

            # Run assertions
            assertions = case.assertions
            assertion_results = []
            all_passed = True
            run_metadata = await self._build_run_metadata(run.id, duration_ms)

            for assertion in assertions:
                result = await AssertionEngine.evaluate_async(
                    assertion=assertion,
                    output=output,
                    run_metadata=run_metadata,
                )
                assertion_results.append(result)
                if not result["passed"]:
                    all_passed = False

            case_result.assertion_results = assertion_results
            case_result.status = (
                CaseResultStatus.PASSED if all_passed else CaseResultStatus.FAILED
            )

        except Exception as e:
            logger.error(f"Case {case.id} error: {e}")
            case_result.status = CaseResultStatus.ERROR
            case_result.error_message = str(e)
            case_result.duration_ms = (time.time() - start_time) * 1000

        self.session.add(case_result)
        await self.session.commit()
        await self.session.refresh(case_result)

        return case_result

    async def _build_run_metadata(
        self,
        run_id: str,
        duration_ms: float,
    ) -> dict[str, Any]:
        """Build eval assertion metadata from persisted run artifacts."""
        steps_stmt = (
            select(StepRecord)
            .where(StepRecord.run_id == run_id)
            .order_by(StepRecord.step_order)
        )
        steps_res = await self.session.exec(steps_stmt)
        steps = list(steps_res.all())

        events_stmt = (
            select(AgentEventRecord)
            .where(AgentEventRecord.run_id == run_id)
            .order_by(AgentEventRecord.timestamp)
        )
        events_res = await self.session.exec(events_stmt)
        agent_events = list(events_res.all())

        return {
            "duration_ms": duration_ms,
            "steps": [
                {
                    "node_id": step.node_id,
                    "node_type": step.node_type,
                    "agent_id": step.agent_id,
                    "output": json.loads(step.output_json) if step.output_json else {},
                }
                for step in steps
            ],
            "agent_events": [
                {
                    "event_type": evt.event_type.value,
                    "agent_id": evt.agent_id,
                    "data": json.loads(evt.data_json) if evt.data_json else {},
                }
                for evt in agent_events
            ],
        }

    # =========================================================================
    # Results
    # =========================================================================

    async def get_eval_run(self, eval_run_id: str) -> EvalRun | None:
        """Get an eval run by ID."""
        statement = select(EvalRun).where(EvalRun.id == eval_run_id)
        result = await self.session.exec(statement)
        return result.one_or_none()

    async def list_eval_runs(
        self,
        suite_id: str,
        limit: int = 20,
    ) -> list[EvalRun]:
        """List eval runs for a suite."""
        statement = (
            select(EvalRun)
            .where(EvalRun.suite_id == suite_id)
            .order_by(EvalRun.created_at.desc())
            .limit(limit)
        )
        result = await self.session.exec(statement)
        return list(result.all())

    async def get_case_results(
        self,
        eval_run_id: str,
    ) -> list[EvalCaseResult]:
        """Get all case results for an eval run."""
        statement = select(EvalCaseResult).where(
            EvalCaseResult.eval_run_id == eval_run_id
        )
        result = await self.session.exec(statement)
        return list(result.all())

    async def get_report(self, eval_run_id: str) -> dict[str, Any] | None:
        """Get the JSON report for an eval run."""
        eval_run = await self.get_eval_run(eval_run_id)
        if eval_run is None:
            return None
        if not eval_run.report_json:
            return None
        return json.loads(eval_run.report_json)

    async def import_dataset_jsonl(
        self,
        suite_id: str,
        jsonl_content: str,
    ) -> list[EvalCase]:
        """Import test cases from JSONL content.

        Each line must be a JSON object with at minimum an "input" field.
        Optional fields: id, expected, assertions, tags.

        JSONL format:
            {"id": "case-001", "input": "...", "expected": {"must_cite": true}}
        """
        suite = await self.get_suite(suite_id)
        if not suite:
            raise ValueError(f"Suite not found: {suite_id}")

        created: list[EvalCase] = []
        for line_no, line in enumerate(jsonl_content.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSONL parse error on line {line_no}: {e}") from e

            input_val = row.get("input")
            if input_val is None:
                raise ValueError(f"Line {line_no}: missing 'input' field")

            input_data = {"input": input_val} if isinstance(input_val, str) else input_val
            expected_data = row.get("expected", {})
            assertions = row.get("assertions", [])
            tags = row.get("tags", [])
            case_id_hint = row.get("id", "")
            name = case_id_hint or f"case-{line_no:03d}"

            case = await self.create_case(
                suite_id=suite_id,
                name=name,
                input_data=input_data,
                expected_data=expected_data,
                assertions=assertions,
                tags=tags,
            )
            created.append(case)

        logger.info(f"Imported {len(created)} cases into suite {suite_id} from JSONL")
        return created
