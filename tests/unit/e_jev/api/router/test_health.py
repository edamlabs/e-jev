from litestar.testing import AsyncTestClient


async def test_health_live(client: AsyncTestClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_health_ready_names_every_backend(client: AsyncTestClient) -> None:
    reply = await client.get("/ready")
    assert (reply.status_code, reply.json()) == (200, {"status": "ready", "backends": {"reading": "up"}})


async def test_health_ready_down(client_down: AsyncTestClient) -> None:
    reply = await client_down.get("/ready")
    assert (reply.status_code, reply.json()) == (503, {"status": "down", "backends": {"reading": "down"}})
