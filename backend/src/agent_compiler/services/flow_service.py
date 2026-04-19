"""Flow management service."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from agent_compiler.models.db import FlowRecord, FlowVersion
from agent_compiler.models.ir import parse_ir
from agent_compiler.models.ir_v2 import FlowIRv2
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class FlowService:
    """Service for managing flows."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_flow(
        self,
        ir_data: dict[str, Any],
        template_id: str | None = None,
        template_version: str | None = None,
    ) -> FlowRecord:
        """Create a new flow from IR data.

        Args:
            ir_data: The flow IR as a dictionary
            template_id: Optional template ID if created from template
            template_version: Optional template version for migration tracking

        Returns:
            The created flow record

        Raises:
            ValueError: If the IR is invalid
        """
        # Validate IR (v2 only)
        flow_ir = parse_ir(ir_data)

        # Check for existing flow with same ID
        existing = await self.get_flow(flow_ir.flow.id)
        if existing:
            raise ValueError(f"Flow with ID '{flow_ir.flow.id}' already exists")

        # Create record
        flow = FlowRecord(
            id=flow_ir.flow.id,
            name=flow_ir.flow.name,
            version=flow_ir.flow.version,
            description=flow_ir.flow.description,
            engine_preference=flow_ir.flow.engine_preference.value,
            ir_json=json.dumps(ir_data),
            template_id=template_id,
            template_version=template_version,
        )

        self.session.add(flow)
        await self.session.commit()
        await self.session.refresh(flow)

        logger.info(
            f"Created flow: {flow.id}",
            extra={
                "template_id": template_id,
                "template_version": template_version,
            } if template_id else {},
        )
        return flow

    async def get_flow(self, flow_id: str) -> FlowRecord | None:
        """Get a flow by ID."""
        statement = select(FlowRecord).where(FlowRecord.id == flow_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_flows(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FlowRecord]:
        """List all flows with pagination."""
        statement = (
            select(FlowRecord)
            .order_by(FlowRecord.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def update_flow(
        self,
        flow_id: str,
        ir_data: dict[str, Any],
    ) -> FlowRecord:
        """Update an existing flow.

        Args:
            flow_id: The flow ID to update
            ir_data: The new IR data

        Returns:
            The updated flow record

        Raises:
            ValueError: If flow not found or IR is invalid
        """
        # Get existing flow
        flow = await self.get_flow(flow_id)
        if flow is None:
            raise ValueError(f"Flow not found: {flow_id}")

        # Validate new IR (v2 only)
        flow_ir = parse_ir(ir_data)

        # Ensure ID matches
        if flow_ir.flow.id != flow_id:
            raise ValueError(f"Flow ID in IR ({flow_ir.flow.id}) doesn't match URL ({flow_id})")

        # Save a version snapshot before overwriting
        await self._create_version_snapshot(flow)

        # Update record
        flow.name = flow_ir.flow.name
        flow.version = flow_ir.flow.version
        flow.description = flow_ir.flow.description
        flow.engine_preference = flow_ir.flow.engine_preference.value
        flow.ir_json = json.dumps(ir_data)
        flow.updated_at = datetime.now(timezone.utc)

        self.session.add(flow)
        await self.session.commit()
        await self.session.refresh(flow)

        logger.info(f"Updated flow: {flow.id}")
        return flow

    async def delete_flow(self, flow_id: str) -> bool:
        """Delete a flow by ID.

        Args:
            flow_id: The flow ID to delete

        Returns:
            True if deleted, False if not found
        """
        flow = await self.get_flow(flow_id)
        if flow is None:
            return False

        await self.session.delete(flow)
        await self.session.commit()

        logger.info(f"Deleted flow: {flow_id}")
        return True

    def get_flow_ir(self, flow: FlowRecord) -> FlowIRv2:
        """Parse and return the FlowIRv2 from a flow record."""
        return parse_ir(json.loads(flow.ir_json))

    # ── Version History ──────────────────────────────────────────────

    async def _create_version_snapshot(self, flow: FlowRecord) -> FlowVersion:
        """Create a version snapshot of the current flow state."""
        # Get the next version number
        stmt = select(func.max(FlowVersion.version_number)).where(
            FlowVersion.flow_id == flow.id
        )
        result = await self.session.execute(stmt)
        max_ver = result.scalar_one_or_none() or 0
        next_ver = max_ver + 1

        version = FlowVersion(
            id=f"fv_{uuid.uuid4().hex[:12]}",
            flow_id=flow.id,
            version_number=next_ver,
            ir_json=flow.ir_json,
        )
        self.session.add(version)
        # Don't commit here — the caller (update_flow) will commit
        logger.debug(f"Saved version {next_ver} for flow {flow.id}")
        return version

    async def list_versions(
        self,
        flow_id: str,
        limit: int = 50,
    ) -> list[FlowVersion]:
        """List all versions for a flow, newest first."""
        stmt = (
            select(FlowVersion)
            .where(FlowVersion.flow_id == flow_id)
            .order_by(FlowVersion.version_number.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_version(
        self,
        flow_id: str,
        version_number: int,
    ) -> FlowVersion | None:
        """Get a specific version of a flow."""
        stmt = select(FlowVersion).where(
            FlowVersion.flow_id == flow_id,
            FlowVersion.version_number == version_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def restore_version(
        self,
        flow_id: str,
        version_number: int,
    ) -> FlowRecord:
        """Restore a flow to a specific historical version.

        This creates a new version snapshot of the current state before
        restoring, so nothing is lost.
        """
        flow = await self.get_flow(flow_id)
        if flow is None:
            raise ValueError(f"Flow not found: {flow_id}")

        version = await self.get_version(flow_id, version_number)
        if version is None:
            raise ValueError(f"Version {version_number} not found for flow {flow_id}")

        ir_data = json.loads(version.ir_json)
        return await self.update_flow(flow_id, ir_data)

    async def label_version(
        self,
        flow_id: str,
        version_number: int,
        label: str,
    ) -> FlowVersion:
        """Add/update a label on a version."""
        version = await self.get_version(flow_id, version_number)
        if version is None:
            raise ValueError(f"Version {version_number} not found for flow {flow_id}")

        version.label = label
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(version)
        return version
