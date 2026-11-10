"""providers/drivers/decide/systemone: one forward to a native `/v1/systemone` server, its probabilities as log scores.

H2O-Lightning-4B, Clef-Flash, TypeSafe's own Jev, Laya: every server that speaks the contract is this driver at another
URL. Confidence is never taken from the answer — the runner rebuilds it from these scores with Jev's formula; a score
level that arrives null was refused at the boundary (422); a choice wider than the backend's budget never reaches it —
routing sent it elsewhere. Capacity answers as the typed leaves; anything out of contract is a gateway error."""

from collections.abc import Mapping
from typing import Any, ClassVar, Final, Self

import httpx
import msgspec
import numpy as np

from e_jev.infra.logger import logger
from e_jev.models.error import ContractError, OverloadedError, RateLimitedError, RequestError
from e_jev.models.systemone import Answer, Choice, ChoiceAnswer, NoulAnswer, Question, Score, ScoreAnswer, SystemOneResponse
from e_jev.ports.decide import Decision
from e_jev.ports.provider import Isolation, Locality, Opened, ProviderSpec, Workload
from e_jev.ports.readout import Scores

EPS: Final = 1e-12
ENCODER: Final = msgspec.json.Encoder()
RESPONSE: Final = msgspec.json.Decoder(SystemOneResponse)


##### TYPES #####
class SystemOneDecideDriver:
    """One pooled client per backend, bounded by the backend's own concurrency (a serial server gets one slot)."""

    __slots__ = ("_backend", "_client", "_concurrency", "_key", "_model", "_timeout", "_url")

    spec: ClassVar[ProviderSpec] = ProviderSpec("systemone", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True)
    client = Opened[httpx.AsyncClient](RequestError)

    def __init__(self, *, backend: str, url: str, api_key: str, model: str, concurrency: int, timeout: float) -> None:
        self._backend = backend
        self._url = url
        self._key = api_key
        self._model = model or backend
        self._concurrency = concurrency
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    ##### PRIVATE #####

    @staticmethod
    def _decide_scores(answer: Answer, question: Question) -> Scores:
        """The answer's probabilities aligned to the question's option order, in log space.

        Servers echo `probabilities` with their own key order — the vector is read BY KEY, never positionally, or a
        choice answered correctly would be scored as its permutation."""
        match answer:
            case NoulAnswer(noul=p):
                probs = np.array([p, 1.0 - p])
            case ChoiceAnswer(probabilities=published) if isinstance(question, Choice):
                probs = np.array([published.get(name, 0.0) for name in question.criteria])
            case ScoreAnswer(probabilities=published) if isinstance(question, Score):
                probs = np.array([published.get(str(level), 0.0) for level in range(len(question.criteria))])
            case ChoiceAnswer(probabilities=published) | ScoreAnswer(probabilities=published):
                probs = np.array(list(published.values()))
        return np.log(np.clip(probs, EPS, None))

    def _common_classify(self, error: Exception) -> RequestError:
        """The typed upstream failure: capacity answers 429/529, everything else is a gateway error."""
        match error:
            case httpx.HTTPStatusError(response=httpx.Response(status_code=429) as reply):
                hint = (reply.headers.get("retry-after") or "").strip()
                return RateLimitedError(
                    f"rate limited{f', retry in {hint}s' if hint.isdigit() else ''}", float(hint) if hint.isdigit() else None
                )
            case httpx.HTTPStatusError(response=httpx.Response(status_code=503)):
                return OverloadedError("server overloaded")
            case httpx.TimeoutException():
                return OverloadedError("timed out")
            case _:
                return RequestError(f"{self._backend} at {self._url}: {str(error) or type(error).__name__}")

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        limits = httpx.Limits(max_connections=self._concurrency, max_keepalive_connections=self._concurrency)
        self._client = httpx.AsyncClient(
            base_url=self._url, limits=limits, timeout=self._timeout, headers={"authorization": f"Bearer {self._key}"}
        )
        logger.info("decide opened", backend=self._backend, url=self._url, model=self._model)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._client:
            case None:
                return
            case client:
                await client.aclose()
                self._client = None
                logger.info("decide closed", backend=self._backend)

    async def health(self) -> bool:
        """The server answers `/health` with a 2xx — warming servers (H2O's shim) answer 503 until they can decide."""
        try:
            (await self.client.get("/health")).raise_for_status()
        except httpx.HTTPError as error:
            raise self._common_classify(error) from error
        return True

    @property
    def backend(self) -> str:
        return self._backend

    async def decide(self, state: str, questions: Mapping[str, Question]) -> Decision:
        """One request for the whole set: the server reads the state once, every question gets its scores."""
        body: dict[str, Any] = {"model": self._model, "state": state, "questions": questions}
        try:
            reply = await self.client.post("/v1/systemone", content=ENCODER.encode(body), headers={"content-type": "application/json"})
            reply.raise_for_status()
            response = RESPONSE.decode(reply.content)
        except (httpx.HTTPError, msgspec.DecodeError) as error:
            raise self._common_classify(error) from error
        match sorted(set(questions) - set(response.answers)):
            case [first, *_]:
                message = f"out of contract: no answer for {first}"
                raise ContractError(message)
            case _:
                scores = {name: self._decide_scores(response.answers[name], question) for name, question in questions.items()}
        return Decision(scores=scores, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens)
