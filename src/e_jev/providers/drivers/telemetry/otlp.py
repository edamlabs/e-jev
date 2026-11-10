"""providers/drivers/telemetry/otlp: OpenTelemetry spans out over OTLP/HTTP — Phoenix reads them as OpenInference.

Built before the app (the HTTP plugin needs the provider at construction), opened by the lifespan: entering installs it
as the process provider and instruments httpx, so every outbound call carries the trace context and an upstream's own
spans (vLLM's) nest under the readout that caused them; leaving flushes and shuts the exporter down."""

from typing import ClassVar, Self

from openinference.semconv.resource import ResourceAttributes
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from e_jev.infra.logger import logger
from e_jev.ports.provider import Isolation, Locality, ProviderSpec, Workload


##### TYPES #####
class OtlpTelemetryDriver:
    __slots__ = ("_endpoint", "provider")

    spec: ClassVar[ProviderSpec] = ProviderSpec("otlp", Locality.REMOTE, Workload.IO_BOUND, Isolation.THREAD)

    def __init__(self, *, endpoint: str, project: str, service: str | None = None) -> None:
        self._endpoint = endpoint
        self.provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: service or project, ResourceAttributes.PROJECT_NAME: project})
        )

    ##### PUBLIC #####

    @staticmethod
    def headers() -> dict[str, str]:
        """The current trace context as HTTP headers, for clients no instrumentor reaches (the TypeSafe SDK's)."""
        carrier: dict[str, str] = {}
        inject(carrier)
        return carrier

    async def __aenter__(self) -> Self:
        self.provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=self._endpoint)))
        trace.set_tracer_provider(self.provider)
        HTTPXClientInstrumentor().instrument(tracer_provider=self.provider)
        logger.info("telemetry opened", endpoint=self._endpoint)
        return self

    async def __aexit__(self, *exc: object) -> None:
        HTTPXClientInstrumentor().uninstrument()
        self.provider.shutdown()

    async def health(self) -> bool:
        return True
