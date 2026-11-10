# Decisions

Hard to reverse, surprising without context, the result of a real trade-off. Newest first.

## 2026-11-10 · The default backend is the reader over the house LLM; H2O-Lightning-4B is the dedicated one

- **Decision.** `JEV_BACKENDS` defaults to `reading`. The house points it at its vLLM (Gemma 4 26B-A4B) alone;
  `make gpu-h2o` switches it to `h2o-lightning-4b` when the card is handed over. Installers pick from the catalog: `reading` with their own endpoint, or
  `h2o-lightning-4b` / `clef-flash` on their own GPU.
- **Evidence.** `.reports/2026-11-10_backends/`, `docs/evals.md` § round 2: WorkflowEvals 0.625 (reading, Gemma),
  0.549 (H2O two-way), 0.500 (Torchcast), 0.451 (Clef as deployed); the reader adds no VRAM, H2O needs ~10 GB that do
  not fit beside the house vLLM (21 GB of 24).
- **Rejected.** Clef as default: its round-1 0.639 needed `-ub` ≥ the prompt (17.7 GB); as deployed it answers no
  invoice state. Torchcast Decision 4B: English-only, 16 k-token cut, serial server, wide-choice ECE 0.112 > 0.10.
  H2O as the house default: it would take the card from everything else the vLLM serves.

## 2026-11-10 · Drivers own an httpx pool; the common `HTTPPort` (wreq) is not used yet

- **Decision.** The readout and systemone drivers each open their own `httpx.AsyncClient`. The OpenAI SDK and Outlines
  are gone: completions, tokenize and vLLM's native `response_format: json_schema` are plain HTTP.
- **Evidence.** The common `HTTPError` carries the status only. e-jev must answer a 429 with the upstream
  `Retry-After` (TypeSafe's SDKs retry on it) and name a refusal by the server's own message (c4532b0: a missing model
  is not an unreachable host). Both need the response headers and body, which the wreq driver drops at the border.
- **Rejected.** The wreq driver as is (loses both); wrapping it with a second classification (two pools, two error
  trees). **Lands next** in e-arkhetypo common: `HTTPError` carrying headers and a body excerpt — then e-jev moves.

## 2026-11-10 · A closed list of the common spine, tracked

- **Decision.** `scripts/materialize.py` copies six listed files of `projects/python/common` (config base, errors,
  logger, proxy, the provider protocol); they are tracked like e-organon's, gated by `make common-check`, and excluded
  from ruff (their source lints them). `infra/config/infra.py` and `infra/settings.py` are e-jev's own.
- **Evidence.** The common's own `materialize.py` replaces whole sections, which would erase e-jev's ports, drivers
  and engines living beside the copies; whole sections bring postgres, redis, auth and MCP drivers e-jev never opens
  (and their dependencies). Tracked copies keep the image build and CI free of an e-arkhetypo checkout.
- **Rejected.** Gitignored materialization (the api template's): the Dockerfile and CI would need the checkout.
  The common `State` tree: Litestar's state already is the app's tree; a second one is ceremony.

## 2026-11-10 · e-jev stops owning the house vLLM deployment

- **Decision.** `deploy/vllm/` and `vllm.service` leave the repo; `make deploy` installs `ejev` enabled and the GPU
  backends (`clef`, `h2o`) disabled — `gpu-*` hands the card over.
- **Evidence.** The live vLLM (Gemma, v0.31.0, priority scheduling, 131 k context) had drifted from the repo copy
  (Qwen 27B, `latest`); `make deploy` would have overwritten the house LLM slot that other services share. The reader
  treats its endpoint as the deployment's, so the service that owns the slot owns its compose.
- **Rejected.** Syncing the copy back: two sources of truth for one slot, drifting again.
