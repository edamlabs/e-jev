"""Driver fixtures: a fake vLLM server per test."""

import re
from collections.abc import Iterator

import pytest
from pytest_httpserver import HTTPServer

from tests import kit


@pytest.fixture
def fake_vllm() -> Iterator[kit.FakeVllm]:
    server = HTTPServer(host="127.0.0.1")
    fake = kit.FakeVllm(server)
    server.expect_request(re.compile(".*")).respond_with_handler(fake.respond)
    server.start()
    try:
        yield fake
    finally:
        server.stop()
