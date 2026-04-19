"""Event recorder for fine-grained run debug timeline.

Records RunEvent records from step execution data, mapping node types to
the appropriate event type pair (prompt/call + response/result).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import RunEvent, RunEventType
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

# Map node_type (uppercase) to the "call" event emitted before the result
_CALL_EVENT: dict[str, RunEventType] = {
    "LLM": RunEventType.LLM_PROMPT,
    "TOOL": RunEventType.TOOL_CALL,
    "RETRIEVER": RunEventType.RETRIEVAL,
}

# Map node_type (uppercase) to the "result" event emitted from the output
_RESULT_EVENT: dict[str, RunEventType] = {
    "LLM": RunEventType.LLM_RESPONSE,
    "TOOL": RunEventType.TOOL_RESULT,
}


class EventRecorder:
    """Records fine-grained execution events for a run's debug timeline.

    Designed to be called once per completed step inside the executor.
    Uses session.add() without committing — the caller (executor) handles
    the commit so events are persisted atomically with the step record.
    """

    def __init__(
        self,
        session: AsyncSession,
        run_id: str,
        capture_prompts: bool = True,
    ) -> None:
        self.session = session
        self.run_id = run_id
        self.capture_prompts = capture_prompts
        self._seq = 0

    async def record_step(
        self,
        node_id: str,
        node_type: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None,
        error: str | None = None,
    ) -> None:
        """Record events for a completed (or failed) step.

        Emits:
        - LLM_PROMPT / TOOL_CALL / RETRIEVAL — from the node input
        - LLM_RESPONSE / TOOL_RESULT — from the node output (LLM and Tool only)
        - ROUTER_DECISION — from a Router node's output
        - POLICY_BLOCK — if the output signals a policy or guard block
        """
        try:
            ntype = (node_type or "").upper()

            # "Call" event — derived from input
            call_type = _CALL_EVENT.get(ntype)
            if call_type:
                call_payload = self._build_call_payload(ntype, input_data, call_type)
                await self._emit(node_id, call_type, call_payload)

            # "Result" event — derived from output
            result_type = _RESULT_EVENT.get(ntype)
            if result_type and output_data is not None:
                result_payload = self._build_result_payload(ntype, output_data)
                await self._emit(node_id, result_type, result_payload)

            # Router decision
            if ntype == "ROUTER" and output_data is not None:
                await self._emit(node_id, RunEventType.ROUTER_DECISION, {
                    "selected_route": output_data.get("selected_route"),
                    "condition_matched": output_data.get("condition_matched"),
                    "guard_mode": output_data.get("guard_mode"),
                    "grounding_decision": output_data.get("grounding_decision"),
                })

            # Policy / guard block
            if output_data and (
                output_data.get("policy_blocked")
                or output_data.get("guard_blocked")
                or output_data.get("abstained")
            ):
                await self._emit(node_id, RunEventType.POLICY_BLOCK, {
                    "reason": (
                        output_data.get("block_reason")
                        or output_data.get("abstain_reason")
                        or "policy_block"
                    ),
                    "node_id": node_id,
                })

        except Exception as exc:
            logger.warning(f"EventRecorder.record_step failed for {node_id}: {exc}")

    def _build_call_payload(
        self,
        node_type: str,
        input_data: dict[str, Any],
        event_type: RunEventType,
    ) -> dict[str, Any]:
        current = input_data.get("current_value") or input_data.get("input", "")
        if event_type == RunEventType.LLM_PROMPT:
            return {
                "prompt": "[REDACTED]" if not self.capture_prompts else str(current)[:2000],
            }
        if event_type == RunEventType.TOOL_CALL:
            return {"input": str(current)[:500]}
        if event_type == RunEventType.RETRIEVAL:
            return {"query": str(current)[:500]}
        return {}

    def _build_result_payload(
        self,
        node_type: str,
        output_data: dict[str, Any],
    ) -> dict[str, Any]:
        if node_type == "LLM":
            payload: dict[str, Any] = {
                "model": output_data.get("model"),
                "tokens_used": output_data.get("tokens_used"),
            }
            if self.capture_prompts:
                content = output_data.get("output") or output_data.get("content", "")
                payload["content"] = str(content)[:2000]
            return payload
        if node_type == "TOOL":
            return {"result": output_data.get("result")}
        return {}

    async def _emit(
        self,
        node_id: str,
        event_type: RunEventType,
        payload: dict[str, Any],
    ) -> None:
        payload_str = json.dumps(payload, default=str)
        event_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:16]
        event = RunEvent(
            id=f"evt_{self.run_id}_{self._seq}_{uuid.uuid4().hex[:6]}",
            run_id=self.run_id,
            ts=datetime.now(timezone.utc),
            seq=self._seq,
            node_id=node_id,
            type=event_type,
            payload_json=payload_str,
            hash=event_hash,
        )
        self._seq += 1
        self.session.add(event)
        # No commit here — caller (executor) commits after each step
