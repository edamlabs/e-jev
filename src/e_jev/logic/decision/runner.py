"""logic/decision/runner: System One over the fleet — routing, calibration, answers.

One request fans out per question along its fallback chain (the row for its kind, `logic.dispatch`): the
questions each backend may answer go to it in one call; a backend that fails hands its questions to the
next in the row, marked in the trace — never silently. Calibration is e-jev's alone: one temperature per
(backend, kind); confidence and expectations are rebuilt from the raw scores, whatever the backend
published beside them.
"""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Final

import msgspec
from beartype import beartype
from openinference.semconv.trace import OpenInferenceMimeTypeValues, OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace

from e_jev.infra.logger import logger
from e_jev.logic.calibration.fit import scale_temperature
from e_jev.logic.decision.answers import build_answer
from e_jev.logic.decision.ports import ExtractView, FleetView
from e_jev.logic.decision.routing import chains
from e_jev.models.calibration import Calibration
from e_jev.models.catalog import Backend
from e_jev.models.error import CapabilityError, EvaluateError, JevError, RetryableError
from e_jev.models.extract import ExtractRequest
from e_jev.models.systemone import Answer, Json, Question, QuestionKind, SystemOneRequest, SystemOneResponse, Usage, render_json
from e_jev.ports.decide import Decision
from e_jev.ports.readout import Scores
from e_jev.ports.sink import SinkPort

tracer = trace.get_tracer("e_jev")
KIND: Final = SpanAttributes.OPENINFERENCE_SPAN_KIND
JSON: Final = OpenInferenceMimeTypeValues.JSON.value

EXTRACT = "{instructions}\n\nState:\n{state}\n\nReply only with JSON matching the schema."


@beartype
class DecisionRunner:
    __slots__ = ("_calibration", "_extractor", "_fleet", "_log", "_model", "_rows", "_specs", "calibrated")

    def __init__(
        self,
        fleet: FleetView,
        *,
        model: str,
        specs: Sequence[Backend],
        rows: Mapping[QuestionKind, Sequence[str]] | None = None,
        calibration: Calibration | None = None,
        extractor: ExtractView | None = None,
        sink: SinkPort | None = None,
    ) -> None:
        self._fleet = fleet
        self._model = model
        self._rows = rows or {}
        self._specs = {spec.id: spec for spec in specs}
        self._calibration = calibration
        self._extractor = extractor
        self._log = sink
        self.calibrated = calibration is not None

    ##### PRIVATE #####

    @staticmethod
    def _common_leaves(error: BaseException) -> list[JevError]:
        """The JevError leaves of a possibly nested exception group: a wave's failures, flattened."""
        match error:
            case BaseExceptionGroup(exceptions=inner):
                return [leaf for nested in inner for leaf in DecisionRunner._common_leaves(nested)]
            case JevError() as leaf:
                return [leaf]
            case _:
                return []

    @staticmethod
    def _evaluate_failure(errors: list[Exception]) -> Exception:
        """A whole fleet that ran out of capacity is answered as capacity, so the SDK retries; otherwise it is 502."""
        return (
            RetryableError.from_group(ExceptionGroup("fleet at capacity", errors))
            if all(isinstance(error, RetryableError) for error in errors)
            else EvaluateError(errors)
        )

    async def _decide(self, backend: str, state: str, subset: Mapping[str, Question], step: int) -> tuple[Decision | None, list[JevError]]:
        """One route call, traced; its failures return as data so siblings keep answering and the row can fall back."""
        with tracer.start_as_current_span(f"decide {backend}") as span:
            span.set_attributes(
                {
                    KIND: OpenInferenceSpanKindValues.LLM.value,
                    "jev.backend": backend,
                    "jev.route_step": step,
                    "jev.questions": len(subset),
                    SpanAttributes.INPUT_VALUE: msgspec.json.encode(dict(subset)).decode(),
                    SpanAttributes.INPUT_MIME_TYPE: JSON,
                }
            )
            decision, failures = await self._attempt(backend, state, subset)
            match decision:
                case None:
                    span.set_attribute("jev.failed", "; ".join(map(EvaluateError.describe, failures)))
                case ok:
                    span.set_attributes(
                        {
                            SpanAttributes.OUTPUT_VALUE: msgspec.json.encode(
                                {name: scores.tolist() for name, scores in ok.scores.items()}
                            ).decode(),
                            SpanAttributes.OUTPUT_MIME_TYPE: JSON,
                            "jev.input_tokens": ok.input_tokens,
                        }
                    )
            return decision, failures

    async def _attempt(self, backend: str, state: str, subset: Mapping[str, Question]) -> tuple[Decision | None, list[JevError]]:
        """One decider call: its JevError leaves, bare or wrapped by an inner TaskGroup, come back as data."""
        decision: Decision | None = None
        failures: list[JevError] = []
        try:
            decision = await self._fleet.members[backend].decide(state, subset)
        except* JevError as group:
            failures = self._common_leaves(group)
            logger.warning("route failed", backend=backend, error="; ".join(map(EvaluateError.describe, failures)))
        return decision, failures

    async def _route_wave(
        self,
        state: str,
        questions: Mapping[str, Question],
        *,
        pending: Mapping[str, Sequence[Backend]],
        results: dict[str, tuple[str, Scores]],
        errors: list[Exception],
        decisions: list[Decision],
        step: int,
    ) -> None:
        """Ask every pending question of the backend at the head of its chain; what fails descends to the next."""
        match len(pending):
            case 0:
                return
        heads = {chain[0].id: chain[0] for chain in pending.values()}
        groups = {
            backend_id: {name: question for name, question in questions.items() if pending[name][0].id == backend_id}
            for backend_id in heads
        }
        async with asyncio.TaskGroup() as group:
            tasks = {backend_id: group.create_task(self._decide(backend_id, state, subset, step)) for backend_id, subset in groups.items()}
        for backend_id, task in tasks.items():
            decision, failures = task.result()
            errors.extend(failures)
            match decision:
                case None:
                    continue
                case ok:
                    decisions.append(ok)
                    results.update({name: (backend_id, scores) for name, scores in ok.scores.items()})
        await self._route_wave(
            state,
            questions,
            pending={name: chain[1:] for name, chain in pending.items() if name not in results and len(chain) > 1},
            results=results,
            errors=errors,
            decisions=decisions,
            step=step + 1,
        )

    def _answer(self, name: str, state: str, question: Question, backend: str, scores: Scores) -> Answer:
        """One routed score vector: calibrated with its own backend's temperature, logged raw, answered, traced."""
        match self._log:
            case None:
                pass
            case sink:
                sink.record(state, question, scores.tolist(), backend)
        with tracer.start_as_current_span(f"question {name}") as span:
            span.set_attributes(
                {
                    KIND: OpenInferenceSpanKindValues.CHAIN.value,
                    "jev.backend": backend,
                    SpanAttributes.INPUT_VALUE: msgspec.json.encode(question).decode(),
                    SpanAttributes.INPUT_MIME_TYPE: JSON,
                }
            )
            served_model = (spec.model if (spec := self._specs.get(backend)) else None) or self._model
            temperature = self._calibration.temperature(backend, served_model, QuestionKind.of(question)) if self._calibration else 1.0
            span.set_attribute("jev.temperature", temperature)
            answer = build_answer(question, scale_temperature(scores, temperature))
            span.set_attributes({SpanAttributes.OUTPUT_VALUE: msgspec.json.encode(answer).decode(), SpanAttributes.OUTPUT_MIME_TYPE: JSON})
        return answer

    ############################################################

    ##### PUBLIC #####

    async def evaluate(self, request: SystemOneRequest) -> SystemOneResponse:
        with tracer.start_as_current_span("systemone") as span:
            span.set_attributes(
                {
                    KIND: OpenInferenceSpanKindValues.CHAIN.value,
                    SpanAttributes.INPUT_VALUE: msgspec.json.encode(request).decode(),
                    SpanAttributes.INPUT_MIME_TYPE: JSON,
                }
            )
            state = render_json(request.state)
            route = chains(self._rows, self._specs, request.questions, state)
            results: dict[str, tuple[str, Scores]] = {}
            errors: list[Exception] = []
            decisions: list[Decision] = []
            await self._route_wave(state, request.questions, pending=route, results=results, errors=errors, decisions=decisions, step=0)
            match len(results) == len(request.questions):
                case False:
                    raise self._evaluate_failure(errors)
            response = SystemOneResponse(
                model=self._model,
                answers={name: self._answer(name, state, question, *results[name]) for name, question in request.questions.items()},
                usage=Usage(
                    input_tokens=sum(decision.input_tokens for decision in decisions),
                    output_tokens=sum(decision.output_tokens for decision in decisions),
                ),
            )
            span.set_attributes(
                {SpanAttributes.OUTPUT_VALUE: msgspec.json.encode(response).decode(), SpanAttributes.OUTPUT_MIME_TYPE: JSON}
            )
        return response

    async def extract(self, request: ExtractRequest) -> Json:
        """Extraction belongs to the generative teacher: the one decider that kept a reader behind it."""
        match self._extractor:
            case None:
                message = "no reading backend in the fleet to extract with: add `reading` to JEV_BACKENDS"
                raise CapabilityError(message)
            case reader:
                prompt = EXTRACT.format(instructions=render_json(request.instructions), state=render_json(request.state))
                return await reader.extract(prompt, request.schema)

    async def health(self) -> bool:
        """Ready while any backend answers: the fleet degrades, it does not all have to stand."""
        return await self._fleet.health()

    async def report(self) -> dict[str, bool]:
        """Each backend's own answer, by id: what `/ready` shows."""
        return await self._fleet.report()
