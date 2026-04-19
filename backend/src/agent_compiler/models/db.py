"""Database models for persisting flows and runs."""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlmodel import Field, Relationship, SQLModel


class RunStatus(str, Enum):
    """Status of a flow run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Status of a run step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExportStatus(str, Enum):
    """Status of a flow export."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"  # Cleaned up by TTL


class FlowRecord(SQLModel, table=True):
    """Persistent record of a flow definition."""

    __tablename__ = "flows"

    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    version: str = "1.0.0"
    description: str = ""
    engine_preference: str = "langchain"
    ir_json: str = Field(description="Full IR JSON for the flow")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Template tracking fields (nullable for backwards compatibility)
    template_id: str | None = Field(
        default=None,
        description="Template ID used to create this flow (blank, simple_agent, rag_agent)",
    )
    template_version: str | None = Field(
        default=None,
        description="Version of the template used at creation time",
    )

    # Relationships - use selectin for async compatibility and cascade delete
    runs: list["RunRecord"] = Relationship(
        back_populates="flow",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
        },
    )

    @property
    def ir_data(self) -> dict[str, Any]:
        """Parse and return IR data."""
        return json.loads(self.ir_json)

    @ir_data.setter
    def ir_data(self, value: dict[str, Any]) -> None:
        """Set IR data from dict."""
        self.ir_json = json.dumps(value)

    @property
    def created_from_template(self) -> bool:
        """Check if flow was created from a template."""
        return self.template_id is not None


class RunRecord(SQLModel, table=True):
    """Persistent record of a flow execution run."""

    __tablename__ = "runs"

    id: str = Field(primary_key=True)
    flow_id: str = Field(foreign_key="flows.id", index=True)
    status: RunStatus = RunStatus.PENDING
    input_json: str = Field(default="{}", description="Input data for the run")
    output_json: str | None = Field(default=None, description="Final output of the run")
    ir_snapshot_json: str = Field(description="Snapshot of IR at run time for replay")
    error_message: str | None = None
    meta_json: str = Field(default="{}", description="Arbitrary run metadata (e.g. replay info)")
    entrypoint: str = Field(default="main", description="Entrypoint name for multi-agent v2 runs")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships - use selectin for async compatibility
    flow: FlowRecord = Relationship(
        back_populates="runs",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    steps: list["StepRecord"] = Relationship(
        back_populates="run",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
        },
    )

    @property
    def input_data(self) -> dict[str, Any]:
        """Parse and return input data."""
        return json.loads(self.input_json) if self.input_json else {}

    @input_data.setter
    def input_data(self, value: dict[str, Any]) -> None:
        """Set input data from dict."""
        self.input_json = json.dumps(value)

    @property
    def output_data(self) -> dict[str, Any] | None:
        """Parse and return output data."""
        return json.loads(self.output_json) if self.output_json else None

    @output_data.setter
    def output_data(self, value: dict[str, Any] | None) -> None:
        """Set output data from dict."""
        self.output_json = json.dumps(value) if value else None

    @property
    def meta(self) -> dict[str, Any]:
        """Parse and return run metadata."""
        return json.loads(self.meta_json) if self.meta_json else {}

    @meta.setter
    def meta(self, value: dict[str, Any]) -> None:
        """Set run metadata from dict."""
        self.meta_json = json.dumps(value)

    @property
    def ir_snapshot(self) -> dict[str, Any]:
        """Parse and return IR snapshot."""
        return json.loads(self.ir_snapshot_json)


class StepRecord(SQLModel, table=True):
    """Record of a single step in a run's execution timeline."""

    __tablename__ = "steps"

    id: str = Field(primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    node_id: str
    node_type: str
    step_order: int = Field(description="Order of execution")
    status: StepStatus = StepStatus.PENDING
    input_json: str = Field(default="{}")
    output_json: str | None = None
    meta_json: str = Field(default="{}")
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Token tracking for LLM nodes
    tokens_input: int | None = Field(default=None, description="Input/prompt tokens")
    tokens_output: int | None = Field(default=None, description="Output/completion tokens")
    tokens_total: int | None = Field(default=None, description="Total tokens used")
    model_name: str | None = Field(default=None, description="Model used for this step")

    # Multi-agent tracking (v2)
    agent_id: str | None = Field(default=None, description="Agent that owns this step")
    parent_step_id: str | None = Field(default=None, description="Parent step for nested agent calls")
    depth: int = Field(default=0, description="Nesting depth in multi-agent execution")

    # Relationships - use selectin for async compatibility
    run: RunRecord = Relationship(
        back_populates="steps",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    @property
    def input_data(self) -> dict[str, Any]:
        """Parse and return input data."""
        return json.loads(self.input_json) if self.input_json else {}

    @input_data.setter
    def input_data(self, value: dict[str, Any]) -> None:
        """Set input data from dict."""
        self.input_json = json.dumps(value)

    @property
    def output_data(self) -> dict[str, Any] | None:
        """Parse and return output data."""
        return json.loads(self.output_json) if self.output_json else None

    @output_data.setter
    def output_data(self, value: dict[str, Any] | None) -> None:
        """Set output data from dict."""
        self.output_json = json.dumps(value) if value else None

    @property
    def meta(self) -> dict[str, Any]:
        """Parse and return metadata."""
        return json.loads(self.meta_json) if self.meta_json else {}

    @meta.setter
    def meta(self, value: dict[str, Any]) -> None:
        """Set metadata from dict."""
        self.meta_json = json.dumps(value)


class ExportRecord(SQLModel, table=True):
    """Persistent record of a flow export for code preview."""

    __tablename__ = "exports"

    id: str = Field(primary_key=True, description="Unique export ID (UUID)")
    flow_id: str = Field(foreign_key="flows.id", index=True)
    status: ExportStatus = ExportStatus.PENDING
    target: str = Field(default="langgraph", description="Export target: langgraph or runtime")
    export_dir_path: str | None = Field(default=None, description="Server path to export directory")
    zip_path: str | None = Field(default=None, description="Server path to ZIP file")
    manifest_json: str | None = Field(default=None, description="Cached manifest JSON")
    manifest_etag: str | None = Field(default=None, description="ETag hash for manifest caching")
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def manifest_data(self) -> dict[str, Any] | None:
        """Parse and return manifest data."""
        return json.loads(self.manifest_json) if self.manifest_json else None

    @manifest_data.setter
    def manifest_data(self, value: dict[str, Any] | None) -> None:
        """Set manifest data from dict."""
        self.manifest_json = json.dumps(value) if value else None


class FlowEnvVar(SQLModel, table=True):
    """Per-flow, per-profile environment variable."""

    __tablename__ = "flow_env_vars"

    id: str = Field(primary_key=True)
    flow_id: str = Field(foreign_key="flows.id", index=True)
    profile: str = Field(default="development", description="Environment profile name")
    key: str = Field(description="Variable name")
    value: str = Field(default="", description="Variable value")
    is_secret: bool = Field(default=False, description="Whether to mask value in UI")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FlowVersion(SQLModel, table=True):
    """A historical version snapshot of a flow's IR."""

    __tablename__ = "flow_versions"

    id: str = Field(primary_key=True)
    flow_id: str = Field(foreign_key="flows.id", index=True)
    version_number: int
    ir_json: str = Field(description="Snapshot of IR at this version")
    label: str = Field(default="", description="Optional human label")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def ir_data(self) -> dict[str, Any]:
        """Parse and return IR data."""
        return json.loads(self.ir_json)


# =============================================================================
# Replay and Artifact Models
# =============================================================================


class ArtifactType(str, Enum):
    """Types of artifacts stored during execution."""

    LLM_RESPONSE = "llm_response"
    TOOL_OUTPUT = "tool_output"
    RETRIEVAL_RESULT = "retrieval_result"
    ROUTER_DECISION = "router_decision"


class StepArtifact(SQLModel, table=True):
    """Artifact captured during step execution for deterministic replay."""

    __tablename__ = "step_artifacts"

    id: str = Field(primary_key=True)
    step_id: str = Field(foreign_key="steps.id", index=True)
    artifact_type: ArtifactType
    artifact_json: str = Field(description="Serialized artifact data")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def artifact_data(self) -> dict[str, Any]:
        """Parse and return artifact data."""
        return json.loads(self.artifact_json)

    @artifact_data.setter
    def artifact_data(self, value: dict[str, Any]) -> None:
        """Set artifact data from dict."""
        self.artifact_json = json.dumps(value)


class ReplayMode(str, Enum):
    """Modes for replaying a run."""

    EXACT = "exact"  # Use exact artifacts from original run
    MOCK_TOOLS = "mock_tools"  # Mock only tool calls, re-run LLMs
    MOCK_ALL = "mock_all"  # Mock all external calls


class ReplayConfig(SQLModel):
    """Configuration for a replay run."""

    mode: ReplayMode = ReplayMode.EXACT
    mock_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Override specific step outputs by node_id",
    )
    skip_nodes: list[str] = Field(
        default_factory=list,
        description="Node IDs to skip during replay",
    )


# =============================================================================
# Eval Suite Models
# =============================================================================


class GitOpsJobStatus(str, Enum):
    """Status of a GitOps job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class GitOpsJob(SQLModel, table=True):
    """Tracks async GitOps PR creation jobs."""

    __tablename__ = "gitops_jobs"

    id: str = Field(primary_key=True)
    export_id: str = Field(index=True)
    status: GitOpsJobStatus = GitOpsJobStatus.PENDING
    repo: str = Field(description="owner/name")
    base_branch: str
    branch_name: str
    pr_title: str | None = None
    pr_body: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    commit_sha: str | None = None
    files_total: int = 0
    files_uploaded: int = 0
    logs_json: str = Field(default="[]")
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def logs(self) -> list[str]:
        return json.loads(self.logs_json) if self.logs_json else []

    @logs.setter
    def logs(self, value: list[str]) -> None:
        self.logs_json = json.dumps(value)

    def add_log(self, message: str) -> None:
        current = self.logs
        current.append(message)
        self.logs_json = json.dumps(current)

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "export_id": self.export_id,
            "status": self.status.value,
            "repo": self.repo,
            "base_branch": self.base_branch,
            "branch_name": self.branch_name,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "commit_sha": self.commit_sha,
            "files_total": self.files_total,
            "files_uploaded": self.files_uploaded,
            "logs": self.logs,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EvalRunStatus(str, Enum):
    """Status of an eval suite run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TimelineEventType(str, Enum):
    """Types of multi-agent timeline events."""

    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    HANDOFF = "handoff"
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    RETRY_ATTEMPT = "retry_attempt"
    FALLBACK_USED = "fallback_used"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"
    GUARD_BLOCK = "guard_block"


class AgentEventRecord(SQLModel, table=True):
    """Timeline event for multi-agent execution."""

    __tablename__ = "agent_events"

    id: str = Field(primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    event_type: TimelineEventType
    agent_id: str
    parent_agent_id: str | None = None
    data_json: str = Field(default="{}", description="Event-specific data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    depth: int = Field(default=0)

    @property
    def data(self) -> dict[str, Any]:
        """Parse and return event data."""
        return json.loads(self.data_json) if self.data_json else {}

    @data.setter
    def data(self, value: dict[str, Any]) -> None:
        """Set event data from dict."""
        self.data_json = json.dumps(value)


# =============================================================================
# Debug Timeline / Run Events
# =============================================================================


class RunEventType(str, Enum):
    """Fine-grained event types for the run debug timeline."""

    LLM_PROMPT = "LLM_PROMPT"
    LLM_RESPONSE = "LLM_RESPONSE"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    RETRIEVAL = "RETRIEVAL"
    ROUTER_DECISION = "ROUTER_DECISION"
    POLICY_BLOCK = "POLICY_BLOCK"


class RunEvent(SQLModel, table=True):
    """Fine-grained execution event for the debug timeline.

    One run produces multiple events in sequence, giving step-level visibility
    into LLM prompts, tool calls, retrievals, and routing decisions.
    """

    __tablename__ = "run_events"

    id: str = Field(primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    seq: int = Field(description="Monotonic sequence number within the run")
    node_id: str = Field(description="Node that emitted this event")
    type: RunEventType
    payload_json: str = Field(default="{}", description="Event payload, redacted if capture_prompts=False")
    hash: str | None = Field(default=None, description="SHA-256 (16 hex) of payload for determinism checks")

    @property
    def payload(self) -> dict[str, Any]:
        """Parse and return payload data."""
        return json.loads(self.payload_json) if self.payload_json else {}

    @payload.setter
    def payload(self, value: dict[str, Any]) -> None:
        self.payload_json = json.dumps(value)


class AssertionType(str, Enum):
    """Types of assertions for eval cases."""

    CONTAINS = "contains"  # Output contains substring
    NOT_CONTAINS = "not_contains"  # Output does not contain substring
    EQUALS = "equals"  # Output equals expected value
    REGEX = "regex"  # Output matches regex pattern
    JSON_PATH = "json_path"  # JSON path returns expected value
    GROUNDED = "grounded"  # Response is grounded (not abstained)
    ABSTAINED = "abstained"  # Response abstained
    MIN_CITATIONS = "min_citations"  # Minimum number of citations
    LATENCY_MS = "latency_ms"  # Max latency threshold
    LLM_JUDGE = "llm_judge"  # LLM-based evaluation (uses model as judge)
    # Multi-agent assertion types (v2)
    AGENT_HANDOFF = "agent_handoff"  # Verify handoff event exists
    AGENT_ISOLATION = "agent_isolation"  # Verify agent only used allowed tools
    BUDGET_UNDER = "budget_under"  # Verify tokens/tool_calls under budget
    RETRY_USED = "retry_used"  # Verify retry_attempt event exists
    FALLBACK_USED = "fallback_used"  # Verify fallback_used event exists
    NO_SCHEMA_ERRORS = "no_schema_errors"  # Verify no schema_validation_error events
    NO_GUARD_BLOCK = "no_guard_block"  # Verify no guard_block events
    # PR3 assertion types
    SCHEMA_VALID = "schema_valid"  # Validate output against a JSON schema
    CITATION_REQUIRED = "citation_required"  # Output must include citation markers
    ABSTAIN_CORRECTNESS = "abstain_correctness"  # Abstain flag matches expected_abstain
    TOOL_SUCCESS_RATE = "tool_success_rate"  # Tool success rate >= threshold


class EvalSuite(SQLModel, table=True):
    """A suite of evaluation test cases for a flow."""

    __tablename__ = "eval_suites"

    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    description: str = ""
    flow_id: str = Field(foreign_key="flows.id", index=True)
    config_json: str = Field(default="{}", description="Suite configuration")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def config(self) -> dict[str, Any]:
        """Parse and return config data."""
        return json.loads(self.config_json) if self.config_json else {}

    @config.setter
    def config(self, value: dict[str, Any]) -> None:
        """Set config from dict."""
        self.config_json = json.dumps(value)


class EvalCase(SQLModel, table=True):
    """A single test case in an eval suite."""

    __tablename__ = "eval_cases"

    id: str = Field(primary_key=True)
    suite_id: str = Field(foreign_key="eval_suites.id", index=True)
    name: str
    description: str = ""
    input_json: str = Field(description="Input data for the test case")
    expected_json: str = Field(default="{}", description="Expected output data")
    assertions_json: str = Field(default="[]", description="List of assertions")
    tags: str = Field(default="[]", description="Tags for filtering")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def input_data(self) -> dict[str, Any]:
        """Parse and return input data."""
        return json.loads(self.input_json)

    @input_data.setter
    def input_data(self, value: dict[str, Any]) -> None:
        """Set input data from dict."""
        self.input_json = json.dumps(value)

    @property
    def expected_data(self) -> dict[str, Any]:
        """Parse and return expected data."""
        return json.loads(self.expected_json) if self.expected_json else {}

    @expected_data.setter
    def expected_data(self, value: dict[str, Any]) -> None:
        """Set expected data from dict."""
        self.expected_json = json.dumps(value)

    @property
    def assertions(self) -> list[dict[str, Any]]:
        """Parse and return assertions."""
        return json.loads(self.assertions_json) if self.assertions_json else []

    @assertions.setter
    def assertions(self, value: list[dict[str, Any]]) -> None:
        """Set assertions from list."""
        self.assertions_json = json.dumps(value)


class EvalRun(SQLModel, table=True):
    """A run of an eval suite."""

    __tablename__ = "eval_runs"

    id: str = Field(primary_key=True)
    suite_id: str = Field(foreign_key="eval_suites.id", index=True)
    status: EvalRunStatus = EvalRunStatus.PENDING
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    gate_passed: bool | None = Field(default=None, description="True if suite thresholds were met")
    report_json: str | None = Field(default=None, description="Serialised JSON report for download")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CaseResultStatus(str, Enum):
    """Status of an individual case result."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class EvalCaseResult(SQLModel, table=True):
    """Result of running a single eval case."""

    __tablename__ = "eval_case_results"

    id: str = Field(primary_key=True)
    eval_run_id: str = Field(foreign_key="eval_runs.id", index=True)
    case_id: str = Field(foreign_key="eval_cases.id")
    run_id: str | None = Field(default=None, foreign_key="runs.id")
    status: CaseResultStatus = CaseResultStatus.PENDING
    assertions_json: str = Field(default="[]", description="Assertion results")
    error_message: str | None = None
    duration_ms: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def assertion_results(self) -> list[dict[str, Any]]:
        """Parse and return assertion results."""
        return json.loads(self.assertions_json) if self.assertions_json else []

    @assertion_results.setter
    def assertion_results(self, value: list[dict[str, Any]]) -> None:
        """Set assertion results from list."""
        self.assertions_json = json.dumps(value)
