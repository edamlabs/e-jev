"""cli/runtime/lifespan: one run's scope — logs on stderr, traces when configured, every edge closed.

A cli process lives for one command, so the lifespan is one `async with`. stdout belongs to the command's
output (tables or JSON), so logging goes to stderr. With JEV_OTLP_ENDPOINT set, the run is traced: the
official OpenInference instrumentor spans each System One call, and the request carries the context, so
e-jev's and vLLM's spans nest under it in Phoenix."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from openinference.instrumentation.typesafe import TypeSafeAIInstrumentor
from opentelemetry import trace

from e_jev.cli.runtime.deps import Deps
from e_jev.infra.config.infra import Env
from e_jev.infra.logger import logger, setup
from e_jev.infra.settings import settings as st
from e_jev.models.session import Session
from e_jev.providers.drivers.telemetry.otlp import OtlpTelemetryDriver

tracer = trace.get_tracer("e_jev.cli")


@asynccontextmanager
async def lifespan(session: Session) -> AsyncIterator[Deps]:
    setup(env=Env.DEV, level=logging.DEBUG if session.verbose else logging.WARNING, stream=sys.stderr)
    async with AsyncExitStack() as stack:
        match st.JEV_OTLP_ENDPOINT:
            case None:
                pass
            case endpoint:
                telemetry = await stack.enter_async_context(
                    OtlpTelemetryDriver(endpoint=endpoint, project=st.JEV_OTLP_PROJECT, service="ejev")
                )
                TypeSafeAIInstrumentor().instrument(tracer_provider=telemetry.provider)
        with tracer.start_as_current_span(f"ejev {session.command}"):
            logger.debug("run start", command=session.command, url=session.url)
            yield Deps(stack, session)
