"""Runner fixtures: the deterministic reading fleet, and an in-memory span sink."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from e_jev.logic.decision.runner import DecisionRunner
from e_jev.logic.readout.decider import ReadoutDecider
from e_jev.models.calibration import Calibration, KindFit
from e_jev.models.systemone import QuestionKind
from tests import kit


@pytest.fixture
def runner(reader: kit.FakeReader) -> DecisionRunner:
    decider = ReadoutDecider(reader, backend="reading", permutations=1, concurrency=4)
    return DecisionRunner(kit.FakeFleet({"reading": decider}), model="m", specs=[kit.reading_spec()], extractor=decider)


@pytest.fixture
def runner_mirrored(reader: kit.FakeReader) -> DecisionRunner:
    return DecisionRunner(kit.fleet_of(reader, permutations=2), model="m", specs=[kit.reading_spec()])


@pytest.fixture
def runner_cooled(reader: kit.FakeReader) -> DecisionRunner:
    fitted = KindFit(
        model="m",
        temperatures=dict.fromkeys(QuestionKind, 1e6),
        ece_before={},
        ece_after={},
        accuracy={},
        fitted=50,
        held_out=50,
    )
    calibration = Calibration(permutations=1, backends={"reading": fitted})
    return DecisionRunner(kit.fleet_of(reader), model="m", specs=[kit.reading_spec()], calibration=calibration)


@pytest.fixture(scope="session")
def span_sink() -> InMemorySpanExporter:
    sink = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(sink))
    trace.set_tracer_provider(provider)
    return sink


@pytest.fixture
def spans(span_sink: InMemorySpanExporter) -> InMemorySpanExporter:
    span_sink.clear()
    return span_sink
