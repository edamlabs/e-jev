##### BUILDER #####
FROM ghcr.io/astral-sh/uv:0.12.15-python3.14-trixie-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md ./
COPY src /app/src
RUN uv sync --frozen --no-dev --no-editable

##### DEPLOY #####
FROM python:3.14-slim-trixie AS deploy
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HF_HOME=/models/.hf
COPY --from=builder /app/.venv .venv
### a fresh named volume takes the ownership of the folder it mounts on: `ejev pull` writes /models as nobody.
RUN mkdir -p /data /models && chown -R nobody /data /models
USER nobody
EXPOSE 45160
CMD ["granian", "--interface", "asgi", "--factory", "--host", "0.0.0.0", "--port", "45160", "e_jev.main:create_app"]
