"""OpenTelemetry tracing support (optional)."""

from contextlib import contextmanager
from typing import Any, Generator

from agent_compiler.config import get_settings
from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)

# Try to import OpenTelemetry, but don't fail if not installed
_otel_available = False
_tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource

    _otel_available = True
except ImportError:
    logger.debug("OpenTelemetry not installed, tracing disabled")


def setup_tracing() -> bool:
    """Set up OpenTelemetry tracing if available and enabled.

    Returns:
        True if tracing was set up successfully, False otherwise
    """
    global _tracer

    settings = get_settings()

    if not settings.otel_enabled:
        logger.debug("OpenTelemetry disabled via config")
        return False

    if not _otel_available:
        logger.warning("OpenTelemetry requested but not installed. Install with: pip install opentelemetry-api opentelemetry-sdk")
        return False

    try:
        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)

        # Add console exporter for development
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)

        # If OTLP endpoint is configured, add that exporter too
        if settings.otel_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

                otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"OTLP exporter configured: {settings.otel_endpoint}")
            except ImportError:
                logger.warning("OTLP exporter not available, using console only")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(__name__)

        logger.info("OpenTelemetry tracing initialized")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {e}")
        return False


@contextmanager
def create_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Create a tracing span if OpenTelemetry is available.

    Args:
        name: Name of the span
        attributes: Optional attributes to add to the span

    Yields:
        The span object (or a no-op context if tracing is disabled)
    """
    if _tracer is not None:
        with _tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, str(value))
            yield span
    else:
        # No-op context manager when tracing is disabled
        yield None


class NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass


def get_current_span() -> Any:
    """Get the current span if tracing is enabled."""
    if _otel_available and _tracer is not None:
        return trace.get_current_span()
    return NoOpSpan()
