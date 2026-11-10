"""providers/drivers/readout/vllm: the upstream failure tree — capacity as 429/529 kinds, everything else as 502 naming its
cause — and the readout dialect itself, against a fake vLLM."""

import httpx
import numpy as np
import pytest

from e_jev.models.error import OverloadedError, RateLimitedError, ReadoutError, RequestError
from e_jev.providers.drivers.readout.vllm import VllmReadoutDriver, VllmStage
from tests import kit

REQUEST = httpx.Request("POST", "http://vllm/tokenize")
DEAD = "http://127.0.0.1:45999/v1"


def _status(status: int, headers: dict[str, str] | None = None, content: bytes = b"") -> httpx.HTTPStatusError:
    response = httpx.Response(status, headers=headers or {}, request=REQUEST, content=content)
    return httpx.HTTPStatusError("upstream", request=REQUEST, response=response)


def _driver(url: str) -> VllmReadoutDriver:
    return VllmReadoutDriver(url=url, api_key="k", model="m", universe=("A", "B"), timeout=5.0)


@pytest.mark.parametrize(
    ("error", "expected", "retry_after"),
    [
        (_status(429, {"retry-after": "3"}), RateLimitedError, 3.0),
        (_status(429), RateLimitedError, None),
        (_status(503), OverloadedError, None),
        (httpx.ReadTimeout("slow", request=REQUEST), OverloadedError, None),
        (_status(500), ReadoutError, None),
        (httpx.ConnectError("refused", request=REQUEST), ReadoutError, None),
    ],
    ids=["rate-hinted", "rate", "overloaded", "timeout", "gateway", "unreachable"],
)
def test_vllm_classify_capacity(error: httpx.HTTPError, expected: type, retry_after: float | None) -> None:
    failure = VllmReadoutDriver._common_classify(VllmStage.READOUT, error)
    assert (type(failure), getattr(failure, "retry_after", None)) == (expected, retry_after)


@pytest.mark.parametrize(
    ("status", "content", "expected"),
    [
        (404, b'{"error": {"message": "The model `clef` does not exist."}}', "HTTP 404: The model `clef` does not exist."),
        (500, b"boom", "HTTP 500: Internal Server Error"),
        (400, b'{"detail": "no"}', "HTTP 400: Bad Request"),
    ],
    ids=["model-missing", "not-json", "no-error-field"],
)
def test_vllm_classify_status_names_the_server_reason(status: int, content: bytes, expected: str) -> None:
    failure = VllmReadoutDriver._common_classify(VllmStage.TOKENIZE, _status(status, content=content))
    assert failure.message == f"readout tokenize: {expected}"


async def test_vllm_open_reports_unreachable_without_a_server() -> None:
    with pytest.raises(ReadoutError, match="unreachable at"):
        async with _driver(DEAD):
            pass


async def test_vllm_open_names_the_refusal_of_a_live_server(fake_vllm: kit.FakeVllm) -> None:
    with pytest.raises(ReadoutError, match=r"HTTP 404: The model `m` does not exist") as raised:
        async with _driver(fake_vllm.url_for("/v1")):
            pass
    assert "unreachable" not in raised.value.message


async def test_vllm_open_reads_labels_and_stop_from_the_template(fake_vllm: kit.FakeVllm) -> None:
    fake_vllm.up = True
    async with _driver(fake_vllm.url_for("/v1")) as driver:
        assert (driver.stop, driver.label("A"), driver.model, await driver.health()) == (4, (1, 2, 3), "m", True)


async def test_vllm_logprobs_in_candidate_order(fake_vllm: kit.FakeVllm) -> None:
    fake_vllm.up = True
    async with _driver(fake_vllm.url_for("/v1")) as driver:
        scores = await driver.logprobs((1, 2), (9, 8, 7))
    np.testing.assert_array_equal(scores, [0.0, -1.0, -2.0])


async def test_vllm_extract_asks_for_a_json_schema(fake_vllm: kit.FakeVllm) -> None:
    fake_vllm.up = True
    async with _driver(fake_vllm.url_for("/v1")) as driver:
        assert await driver.extract("p", {"type": "object"}) == {"schema": "json_schema"}


async def test_vllm_closed_driver_refuses_reads() -> None:
    with pytest.raises(RequestError, match="is not open"):
        await _driver(DEAD).encode("p")
