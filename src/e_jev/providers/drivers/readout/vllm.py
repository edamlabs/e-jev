"""providers/drivers/readout/vllm: the readout port over any OpenAI-compatible server speaking vLLM's logprob dialect.

The chat template renders each prompt once through `/tokenize`; readouts then go to `/v1/completions` with the prompt as
token ids, so a trie node is the same prompt plus a few label tokens — computed once by the prefix cache.
`logprob_token_ids` returns the exact raw logprobs of the candidates; `allowed_token_ids` pins the single sampled token
to one of them. Extraction is vLLM's own structured output (`response_format: json_schema`). Every label the readout
may show and the end-of-turn token are read from the served tokenizer at open, never assumed."""

import asyncio
from collections.abc import Mapping, Sequence
from enum import StrEnum, auto
from typing import Any, ClassVar, Final, Self

import httpx
import msgspec
import numpy as np
from opentelemetry.instrumentation.utils import suppress_instrumentation

from e_jev.infra.logger import logger
from e_jev.models.error import OverloadedError, RateLimitedError, ReadoutError, RequestError
from e_jev.models.systemone import Json
from e_jev.ports.provider import Isolation, Locality, Opened, ProviderSpec, Workload
from e_jev.ports.readout import Scores

NO_THINK: Final = {"chat_template_kwargs": {"enable_thinking": False}}
PROBE: Final = "Z"
ID_PREFIX: Final = "token_id:"


##### TYPES #####
class VllmStage(StrEnum):
    TOKENIZE = auto()
    READOUT = auto()
    EXTRACT = auto()


class VllmReadoutDriver:
    """One pooled client per process; the label table and the stop token are read once, at open."""

    __slots__ = ("_client", "_extract_tokens", "_key", "_labels", "_model", "_priority", "_stop", "_timeout", "_universe", "_url")

    spec: ClassVar[ProviderSpec] = ProviderSpec("vllm", Locality.REMOTE, Workload.IO_BOUND, Isolation.LOOP, pooled=True)
    client = Opened[httpx.AsyncClient](RequestError)

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        model: str,
        universe: Sequence[str],
        extract_tokens: int = 1024,
        priority: int | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._url = url.removesuffix("/").removesuffix("/v1")
        self._key = api_key
        self._model = model
        self._universe = tuple(universe)
        self._extract_tokens = extract_tokens
        self._priority = {"priority": priority} if priority is not None else {}
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._labels: dict[str, tuple[int, ...]] = {}
        self._stop = -1

    ##### PRIVATE #####

    @staticmethod
    def _common_retry_after(headers: Mapping[str, str]) -> float | None:
        """The upstream `Retry-After`, honoured when it is a plain number of seconds."""
        match (headers.get("retry-after") or "").strip():
            case raw if raw.isdigit():
                return float(raw)
            case _:
                return None

    @staticmethod
    def _common_detail(response: httpx.Response) -> str:
        """The reason the server states in its body when it states one: a 404 naming a missing model is not an unreachable host."""
        try:
            body = response.json()
        except ValueError:
            body = None
        match body:
            case {"error": {"message": str() as message}} | {"message": str() as message} if message:
                return message
            case _:
                return response.reason_phrase or f"HTTP {response.status_code}"

    @classmethod
    def _common_classify(cls, stage: VllmStage, error: httpx.HTTPError) -> RequestError:
        """The typed upstream failure: capacity answers 429/529, everything else is a gateway error naming its cause."""
        match error:
            case httpx.HTTPStatusError(response=httpx.Response(status_code=429) as reply):
                return RateLimitedError(f"readout {stage}: rate limited", cls._common_retry_after(reply.headers))
            case httpx.HTTPStatusError(response=httpx.Response(status_code=503)):
                return OverloadedError(f"readout {stage}: server overloaded")
            case httpx.TimeoutException():
                return OverloadedError(f"readout {stage}: timed out")
            case httpx.HTTPStatusError(response=response):
                return ReadoutError(stage, f"HTTP {response.status_code}: {cls._common_detail(response)}")
            case _:
                return ReadoutError(stage, f"unreachable at {error.request.url if error.request else '?'}: {error}")

    async def _common_post(self, stage: VllmStage, path: str, body: Mapping[str, Any]) -> Any:
        try:
            reply = await self.client.post(path, json=body)
            return reply.raise_for_status().json()
        except httpx.HTTPError as error:
            raise self._common_classify(stage, error) from error

    async def _common_tokenize(self, body: Mapping[str, Any]) -> tuple[int, ...]:
        return tuple((await self._common_post(VllmStage.TOKENIZE, "/tokenize", {"model": self._model, **body}))["tokens"])

    async def _aenter_labels(self) -> dict[str, tuple[int, ...]]:
        """Every label the readout may show, tokenized once by the served tokenizer — untraced startup work."""
        with suppress_instrumentation():
            tokens = await asyncio.gather(
                *(self._common_tokenize({"prompt": label, "add_special_tokens": False}) for label in self._universe)
            )
        return dict(zip(self._universe, tokens, strict=True))

    async def _aenter_stop(self) -> int:
        """The token the chat template writes right after an answer — read from the template, never assumed."""
        probe = await self._common_tokenize({"prompt": PROBE, "add_special_tokens": False})
        turn = await self._common_tokenize(
            {"messages": [{"role": "user", "content": "?"}, {"role": "assistant", "content": PROBE}], **NO_THINK}
        )
        match [index for index in range(len(turn) - len(probe)) if turn[index : index + len(probe)] == probe]:
            case [*_, last]:
                return turn[last + len(probe)]
            case _:
                raise ReadoutError(VllmStage.TOKENIZE, "chat template never renders an assistant answer")

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(base_url=self._url, headers={"Authorization": f"Bearer {self._key}"}, timeout=self._timeout)
        try:
            self._labels, self._stop = await asyncio.gather(self._aenter_labels(), self._aenter_stop())
        except BaseException:
            await self.__aexit__()
            raise
        logger.info("readout opened", model=self._model, url=self._url, stop=self._stop)
        return self

    async def __aexit__(self, *exc: object) -> None:
        match self._client:
            case None:
                return
            case client:
                await client.aclose()
                self._client = None
                logger.info("readout closed", url=self._url)

    async def health(self) -> bool:
        try:
            (await self.client.get("/health")).raise_for_status()
        except httpx.HTTPError as error:
            raise self._common_classify(VllmStage.TOKENIZE, error) from error
        return True

    @property
    def model(self) -> str:
        return self._model

    @property
    def stop(self) -> int:
        return self._stop

    def label(self, text: str) -> tuple[int, ...]:
        return self._labels[text]

    async def encode(self, prompt: str) -> tuple[int, ...]:
        return await self._common_tokenize({"messages": [{"role": "user", "content": prompt}], "add_generation_prompt": True, **NO_THINK})

    async def logprobs(self, tokens: Sequence[int], candidates: Sequence[int]) -> Scores:
        ids = list(candidates)
        body = {
            "model": self._model,
            "prompt": list(tokens),
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": 1,
            "logprob_token_ids": ids,
            "allowed_token_ids": ids,
            "return_tokens_as_token_ids": True,
            **self._priority,
        }
        match await self._common_post(VllmStage.READOUT, "/v1/completions", body):
            case {"choices": [{"logprobs": {"top_logprobs": [dict() as top, *_]}}, *_]}:
                by_id = {int(token.removeprefix(ID_PREFIX)): value for token, value in top.items()}
            case _:
                raise ReadoutError(VllmStage.READOUT, "no logprobs returned")
        try:
            return np.array([by_id[token] for token in ids])
        except KeyError as error:
            raise ReadoutError(VllmStage.READOUT, f"candidate {error} missing: the server ignores logprob_token_ids") from error

    async def extract(self, prompt: str, schema: dict[str, Any]) -> Json:
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self._extract_tokens,
            "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "extract", "schema": schema}},
            **NO_THINK,
            **self._priority,
        }
        match await self._common_post(VllmStage.EXTRACT, "/v1/chat/completions", body):
            case {"choices": [{"message": {"content": str() as content}}, *_]}:
                try:
                    return msgspec.json.decode(content)
                except msgspec.DecodeError as error:
                    raise ReadoutError(VllmStage.EXTRACT, f"not JSON: {content[:120]!r}") from error
            case _:
                raise ReadoutError(VllmStage.EXTRACT, "no message returned")
