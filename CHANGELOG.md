# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- README: what H2O-Lightning-4B needs on a GPU (driver ≥ R580 for the CUDA 13 engine, VRAM, ~40 GB of disk, build,
  pull and first-start times measured on the 4090) and the commands to bring it up and ask it.

## [0.3.0] - 2026-11-10

### Added

- Backend catalog (`models/catalog.py`): `JEV_BACKENDS` takes catalog names — `reading` (default), `systemone`,
  `h2o-lightning-4b`, `clef-flash` — comma-separated, preferred first; a name outside it fails the load listing the
  valid ones, a selected backend without its endpoint stops the start naming the variable (`MissingEndpointError`).
- H2O-Lightning-4B v1.4.2 as a catalog backend: its engine image (`deploy/h2o`: vLLM 0.30.0 + H2O's two-way fork,
  verified file by file), the installer's compose profile, and the house unit with `make gpu-h2o`.
- `ops/hub` + `ejev pull`: pinned Hugging Face snapshots (hf_xet), verified against `SHA256SUMS` when shipped,
  idempotent; the root `compose.yml` runs it as a one-shot `models` service before the backend servers.
- Root `compose.yml` + `.env.example` for installers: `COMPOSE_PROFILES` follows `JEV_BACKENDS`, so one name selects
  the backend and starts its server. Verified end to end on the 4090: images built in 6 min, `ejev pull` fetched
  H2O in 3 m 44 s (a second run a no-op), H2O healthy in 85 s with a warm compile cache, three questions in 55 ms
  through e-jev; the integration tier 7/8 on H2O uncalibrated (the triage scenario's outage ticket routes differently
  than on the reader), 8/8 on the Gemma reader.
- Settings: an empty variable is an unset one (`JEV_DECISION_LOG=` no longer opens `Path(".")` and kills the start).
- `/ready` names every backend up or down; `JEV_READING_PRIORITY` for vLLM priority scheduling (the house: 10).
- `docs/decisions.md`: the decisions of this release, with evidence and rejected alternatives.

### Changed

- **Breaking config.** `JEV_BACKENDS` is catalog names, no longer JSON specs; the reader is `JEV_READING_URL` /
  `_KEY` / `_MODEL` (was `JEV_VLLM_URL` / `_API_KEY`, `JEV_MODEL`); `ejev-mcp` reads `JEV_CLI_URL` / `_KEY` / `_MODEL`
  (was `EJEV_URL`…).
- The EAGER tree on the e-arkhetypo common spine (TODO_fleet): `ports/` (decide, readout, sink), `providers/drivers/`
  (readout/vllm, decide/systemone, sink/jsonl, telemetry/otlp), `engines/fleet`, `logic/{readout,decision,calibration}`
  with the `DecisionRunner`, `api/lifespan/{providers,engines,logic}` as the composition root, settings as UPPERCASE
  clusters in `infra/config`; `tach` layers follow the taxonomy. Six common files materialized and drift-gated
  (`make common`, `make common-check`).
- Python 3.14. The OpenAI SDK and Outlines leave: extraction is vLLM's `response_format: json_schema`.
- `examples/triage` → `tests/integration/scenarios/triage` (`make graph`, `make integration`).
- House deploy: e-jev reads the house vLLM (Gemma) — no Clef to load; `make gpu-h2o` / `gpu-decide` switch it to a
  decision model through the compose dir's `.env`, `gpu-teach` back; Clef reads its GGUF from
  the shared `data/models` (`make pull`). `deploy/vllm` leaves the repo: the LLM slot is owned elsewhere.

### Measured

- Backend bake-off 2026-11-10 (`.reports/2026-11-10_backends/`: per-arm JSON, watch peaks, `windows.md`, the
  bench-only Dockerfiles and window script), same harness for every arm, each alone on the 4090. WorkflowEvals mean
  (48 cases): Gemma 4 26B-A4B through the `reading` route 0.625 · H2O-Lightning-4B v1.4.2 two-way 0.549 / one-way
  0.521 · Torchcast Decision 4B v1.3.1 0.500 · Clef-Flash Q4 as deployed (`-ub 4096`) 0.451 — it answers no invoice
  state (24–37 k tokens); October's 0.639 needed `-ub` ≥ prompt (17.7 GB). Held-out Banking77: Clef 0.96, H2O 0.94,
  Torchcast 0.79, Gemma 0.78; MASSIVE es-20: Clef 0.95, Torchcast 0.87, Gemma/H2O 0.86. Bench images and weights
  removed after the window; Torchcast Decision 4B not added (English-only, 16 k cut, serial, wide-choice ECE 0.112); vLLM stopped 15:46:54–16:25:37 and restored healthy.

### Fixed

- Fleet stability: a backend that failed to open (the vLLM reader caught mid-model-load is the case)
  reopens itself once the server returns — retried at most once per `REOPEN_DELAY` with its freshest
  diagnosis — instead of parking `/ready` at 503 for the container's whole life; the reader's open
  classifies HTTP refusals instead of collapsing them into `unreachable`.
- Deploy: systemd is the sole owner of the ejev container (`restart: "no"`) and the unit gates on vLLM
  health — it waits while the vLLM container is `starting` and passes when it is absent, so the
  daemon's restart manager can no longer revive ejev beside a still-loading model (the 503 poisoning
  after a dockerd crash) and `gpu-decide` still serves without vLLM.

### Changed

- Identity: the multi-backend purpose is stated in the description and README — the decision backend is a
  routable fleet (Clef, the vLLM reader, Laya, any `/v1/systemone` server), not a single model.
- `pyproject.toml`: `[tool.edamlabs]` declares `kind = "service"` and `family = "eager"`; authors move to
  EDamLabs; description no longer anchored on vLLM.
- README: header standardized on the EDamLabs template (badge row, banner wordmark without an `<h1>`,
  identity line).
- `CHANGELOG.md` added: the fleet's release and drift modules read it.

## [0.2.0] - 2026-10-14

### Added

- Backend fleet: `JEV_BACKENDS` / `JEV_ROWS` route per question kind, language and state size, falling
  down the row on failure (`BackendKind`: reading, systemone, laya).
- Clef-Flash as a trained decision backend; the reader as the logprob teacher and sole extractor.
- `ejev` CLI (ask, calibrate) and `ejev-mcp` (the same decisions as MCP tools).
- TypeSafe wire compatibility: `POST /v1/systemone`, `POST /v1/extract`, `GET /v1/models`; capacity
  answers 429/529.
- Per-(backend, kind) calibration with a stable fit/held-out split over BoolQ, AG News, Banking77, SST-5
  and a Spanish set.
- systemd --user and Docker deployment (`make deploy`, `gpu-decide`, `gpu-teach`).

[Unreleased]: https://github.com/edamlabs/e-jev/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/edamlabs/e-jev/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/edamlabs/e-jev/releases/tag/v0.2.0
