<p align="center">
  <a href="https://img.shields.io/badge/python-3.14-166b7e"><img src="https://img.shields.io/badge/python-3.14-166b7e" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/edamlabs/e-jev?color=166b7e" alt="License"></a>
</p>

<p align="center">
  <img src="assets/logo.svg" alt="e-jev" height="110" />
</p>

A self-hosted [Jev](https://docs.typesafe.ai): TypeSafe's System One API — typed, calibrated decisions
instead of text — over a **catalog of decision backends**, chosen with one variable:

| `JEV_BACKENDS` | What answers | You bring |
|---|---|---|
| `reading` (default) | option-letter logprobs read from any LLM that speaks vLLM's dialect (`/tokenize` + `/v1/completions` with `logprob_token_ids`) — also `/v1/extract` | the endpoint: `JEV_READING_URL`, `JEV_READING_MODEL` |
| `h2o-lightning-4b` | [H2O-Lightning-4B](https://huggingface.co/h2oai/h2o-lightning-4b) v1.4.2 (Apache-2.0), two-way attention, 32k states | an NVIDIA GPU (~9.3 GB of weights); the weights download themselves |
| `clef-flash` | [Clef-Flash](https://huggingface.co/ggml-org/Clef-Flash-GGUF) Q4_K_M (Apache-2.0) on llama.cpp, states up to ~4k tokens | an NVIDIA GPU (6.9 GB); the weights download themselves |
| `systemone` | any native `/v1/systemone` server — TypeSafe's Jev, Laya, Kev… | the endpoint: `JEV_SYSTEMONE_URL` |

Several, comma-separated, make a fleet: preferred first, a question falls down the row when a backend fails or
cannot serve its shape (language, option count, state length). A name outside the catalog stops the service at
start and lists the valid ones; a selected backend without its endpoint stops it naming the variable. The reader
needs logprobs: hosted APIs that hide them (Anthropic's, OpenAI's chat-only models) cannot be a `reading` backend.

Part of the **EDamLabs eager series**: EDamLabs' own e- products ([EDamLabs families](https://github.com/edamlabs/esteward#identity)).

Wire-compatible with the official `typesafe-sdk`, `@typesafe-ai/sdk`, the TypeSafe n8n node, jevgrep and
pg-jev: point their base URL here. No text is generated on the decision path; confidence follows
TypeSafe's reference definitions; every answer is calibrated per (backend, question kind).

## Install

    git clone https://github.com/edamlabs/e-jev && cd e-jev
    cp .env.example .env       # JEV_BACKENDS=h2o-lightning-4b — or reading + its endpoint
    docker compose up -d --build

`COMPOSE_PROFILES` follows `JEV_BACKENDS` (`.env.example`), so one name selects the backend in e-jev and starts its
server: `models` runs `ejev pull` (pinned Hub snapshots, verified, a no-op when complete), the backend's server
warms up (H2O: minutes — its `/health` answers 503 until every path is warmed), then e-jev answers on `:45160`.
`curl localhost:45160/ready` names every backend up or down. Requirements for a GPU backend: Docker with the
NVIDIA container toolkit, Compose ≥ 2.20; H2O's engine image is built locally (vLLM 0.30.0 + H2O's two-way fork,
checked file by file against the sums the model ships).

### H2O-Lightning-4B on your GPU

What it needs, measured on an RTX 4090 (24 GB) on 2026-11-10:

- **NVIDIA driver ≥ R580** (the engine image is vLLM 0.30.0 on CUDA 13.0), Docker with the NVIDIA container toolkit,
  Compose ≥ 2.20.
- **The card to itself.** Weights 9.3 GB; vLLM takes `H2O_GPU_UTIL` (0.85) of the whole card for weights and KV.
  On a 16 GB card lower `H2O_MAX_LEN` (16384) before lowering `H2O_GPU_UTIL`; vLLM refuses to start when the share
  it asks for is not free.
- **~40 GB of disk**: the engine image (~31 GB, built locally) and the snapshot (8.7 GB, in the `models` volume).
- **Time**: the build takes ~6 min, `ejev pull` ~4 min (no `HF_TOKEN` needed; set one for faster, unthrottled
  downloads). The first start compiles CUDA graphs and warms every path — several minutes; later starts reuse the
  `h2o-cache` volume (85 s measured).

```
cp .env.example .env                       # JEV_BACKENDS=h2o-lightning-4b, as shipped
docker compose up -d --build
docker compose logs -f h2o                 # wait for "H2O-Lightning-4B ready on …"
curl -s localhost:45160/ready              # {"status":"ready","backends":{"h2o-lightning-4b":"up"}}
curl -s localhost:45160/v1/systemone -H 'content-type: application/json' -d '{
  "state": "I was charged twice for my invoice, refund me",
  "questions": {"team": {"type": "choice", "instructions": "Which team?",
                         "criteria": {"billing": "payments, refunds", "tech": "bugs, outages"}}}}'
```

`H2O_TWO_WAY=0` serves one-way attention (stock behaviour, slightly faster, a little lower on Spanish in our bench).
Answers are H2O's own calibration until you fit e-jev's: `ejev calibrate FILE --backend h2o-lightning-4b`.

For this machine, `make deploy` installs e-jev as a systemd --user unit under `~/.config/compose`, reading the house
vLLM (Gemma 4 26B-A4B); the GPU backends are installed, never enabled, and `gpu-*` switches e-jev to them:

    make gpu-teach    # default: vLLM on the card, ejev reads it
    make gpu-h2o      # H2O-Lightning-4B on the card, vLLM stopped, e-jev answers through it
    make gpu-decide   # Clef-Flash on the card, vLLM stopped

A backend that is down degrades to a failing route: the fleet boots and serves what it can, and reopens a backend
once its server returns. `JEV_DECISION_LOG` records every answered question (state, scores, backend) as JSONL — the
corpus the distillation loop trains faster heads from.

## API

`POST /v1/systemone` (bare `/systemone` too — open clients join without the prefix) — the TypeSafe
contract: `state` (string, object or array), `model`, and a map of questions of type `noul`, `choice`
(≤255 options) or `score` (≤10 levels).

    curl -s localhost:45160/v1/systemone -H 'content-type: application/json' -d '{
      "state": "Help! My payouts have been failing for 3 days.",
      "model": "jev-latest",
      "questions": {
        "department": {"type": "choice", "instructions": "Which team should handle this?",
                       "criteria": {"billing": "Payments, invoicing, refunds", "technical": "Bugs, outages", "sales": "Pricing"}},
        "is_urgent":  {"type": "noul", "instructions": "Does this convey urgency?"},
        "frustration": {"type": "score", "instructions": "How frustrated is the customer?", "criteria": ["Calm", "Frustrated", "Very angry"]}
      }}'

`GET /v1/models` — the fleet's names. `POST /v1/extract` — beyond Jev: typed values through the teacher.
Capacity answers 429/529 (what the official SDKs retry), never 502.

    from typesafe_sdk import Choice, TypeSafeClient
    client = TypeSafeClient(api_key="local", base_url="http://localhost:45160")

`ejev-mcp` (`src/e_jev/mcp/server.py`) mounts the same decisions as MCP tools — noul, choice, score, models — for
Claude Code, OpenCode and OpenHuman over stdio, against `JEV_CLI_URL`.

## CLI

`ejev` asks any System One endpoint — this e-jev or TypeSafe's Jev — from the terminal:

    ejev noul "Is this urgent?" --state "Checkout is down, we lose orders"
    ejev choice "Which team?" "billing=Charges, refunds" "technical=Bugs" sales --state @ticket.txt
    ejev --json ask request.json
    ejev calibrate .cache/labeled.jsonl --backend h2o-lightning-4b   # per-backend fit, merged into the file
    ejev pull h2o-lightning-4b                                        # a catalog backend's weights into JEV_MODELS_DIR

## Consumers verified

`tests/integration/scenarios/triage/graph.py` (Pydantic AI + pydantic-graph) — `make integration` and `make graph`;
n8n's official TypeSafe node — `make ui`; **jevgrep**: `jg auth --provider custom --base-url
http://localhost:45160/v1 --model jev-latest`, semantic search in ~2 s at its own c32; **pg-jev**:
`SET jev.api_url='http://jev:45160/v1/systemone'` inside Postgres (the setting takes the full endpoint) (plpython3u).

## Calibrate

One temperature per **(backend, kind)** — thresholds do not transfer across backends. `make calibrate`
fits the reader, `ejev calibrate --backend h2o-lightning-4b` a decision model; the default set is BoolQ, AG News,
Banking77 (77-way), SST-5 plus a Spanish set (MASSIVE es-ES, XNLI es, tweet sentiment), each example in a
stable half: fit or held out. Every number reported comes from the held-out half. The bake-off table —
all measured candidates, quality and memory — lives in [docs/evals.md](docs/evals.md).

## Tuning

e-jev: `JEV_BACKENDS` (the catalog choice), `JEV_ROWS` (JSON: a preference row per question kind), the endpoints
(`JEV_READING_URL` / `_MODEL` / `_KEY` / `_PRIORITY` — vLLM priority scheduling, `JEV_SYSTEMONE_URL` / `_KEY`,
`JEV_H2O_URL`, `JEV_CLEF_URL`), `JEV_PERMUTATIONS` (1; 2 averages both option orders on the reader), `JEV_API_KEY`,
`JEV_CALIBRATION`, `JEV_DECISION_LOG`, `JEV_MODELS_DIR`, `JEV_OTLP_ENDPOINT`. H2O: `H2O_GPU_UTIL` (0.85 of the whole
card), `H2O_MAX_LEN` (32768), `H2O_TWO_WAY` (1). Clef: `CLEF_CTX` (32768), `CLEF_UBATCH` (4096 — the decision head
needs the whole prompt in one batch), `CLEF_BATCH`.

## Benchmark

Bake-off 2026-11-10, every backend alone on one RTX 4090, the same harness (`docs/evals.md`, raw runs in
`.reports/2026-11-10_backends/`):

| backend | WorkflowEvals (48 cases) | Banking77 | MASSIVE es-20 | p95 at c32 | decisions/s at c32 |
|---|---|---|---|---|---|
| `reading` on Gemma 4 26B-A4B | **0.625** | 0.78 | 0.86 | 0.66 s | 93 |
| `h2o-lightning-4b` two-way | 0.549 | 0.94 | 0.86 | 1.03 s | 58 |
| `clef-flash` as deployed (`-ub 4096`) | 0.451 (no invoice state fits) | **0.96** | **0.95** | 2.62 s | 22 |
| Torchcast Decision 4B (rejected) | 0.500 | 0.79 | 0.87 | 2.30 s | 36 |

Jev 1.13 on the same cases: 0.583. At 12 cases per workflow, ±0.05 is one or two cases: noise, not a ranking.

## Differences from Jev

- Long states route by budget: Clef ~4k tokens, H2O and the reader 32k by default; Jev's own budget is not published.
- `usage.output_tokens` counts forward passes on the reader, server-reported usage elsewhere.
- Probabilities come from the trained decision model or a general instruct model; calibrate per backend
  before trusting thresholds tuned on Jev's.
