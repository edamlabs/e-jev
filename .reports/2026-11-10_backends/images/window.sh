#!/usr/bin/env bash
# GPU window, 2026-11-10: every candidate alone on the 4090 (vLLM stopped; TEI embed/reranker stay as they live).
# Each arm: start → cold start → watch peaks → calibration+Spanish bench → WorkflowEvals → stop and remove.
# vLLM restarts on every exit path (trap). Windows are logged to the report.
set -uo pipefail
REPO=/home/damien/workspaces/damien/e-jev
R=$REPO/.reports/2026-11-10_backends
W=$R/windows.md
BENCH=$HOME/.cache/ejev-bench
CLEF=$HOME/.config/compose/data/clef/models
ARMS="${ARMS:-C1 T1 H1 H2}"
cd "$REPO"; mkdir -p "$R"

stamp() { printf '%s %s\n' "$(date +%FT%T%z)" "$*" | tee -a "$W"; }
restore() { docker rm -f bench-clef bench-h2o bench-torchcast >/dev/null 2>&1; stamp "start vllm"; systemctl --user start vllm; }
trap restore EXIT

ready() {  # $1 url of a systemone endpoint, $2 model, $3 timeout seconds
  local t0=$SECONDS
  until curl -sf -m 60 "$1/v1/systemone" -H 'content-type: application/json' \
      -d "{\"model\":\"$2\",\"state\":\"warm-up\",\"questions\":{\"q\":{\"type\":\"noul\",\"instructions\":\"Is this a warm-up?\"}}}" >/dev/null; do
    (( SECONDS - t0 > $3 )) && return 1
    sleep 5
  done
}

arm() {  # $1 config, $2 container, $3 url, $4 model
  local cid; cid=$(docker inspect --format '{{.Id}}' "$2")
  stamp "cold-start begin $1"
  ready "$3" "$4" 1800 || { stamp "FAILED to start $1"; docker logs --tail 80 "$2" > "$R/$1_failed.log" 2>&1; docker rm -f "$2" >/dev/null; return 1; }
  stamp "cold-start end $1"
  uv run python scripts/backend_watch.py "$R/watch_$1.json" --gpu --cgroup "/sys/fs/cgroup/system.slice/docker-${cid}.scope/memory.peak" --seconds 7200 &
  local watch=$!
  uv run python scripts/backend_bench.py "$1" "$3" --file .cache/labeled.jsonl --file .cache/spanish.jsonl --out "$R/$1.json" --lat-per-kind 30 --model "$4" --timeout 300
  stamp "bench end $1"
  bash scripts/evals_bakeoff.sh "$1" "$3" 12
  stamp "evals end $1"
  kill "$watch" 2>/dev/null; wait "$watch" 2>/dev/null
  docker logs --tail 200 "$2" > "$R/$1_server.log" 2>&1
  docker rm -f "$2" >/dev/null
}

stamp "stop vllm (GPU window: $ARMS)"
systemctl --user stop vllm
until ! docker ps --format '{{.Names}}' | grep -qx vllm; do sleep 2; done

for a in $ARMS; do
  case $a in
    C1)  # Clef-Flash Q4_K_M, the deployed configuration (re-baseline, same day, same harness)
      docker run -d --name bench-clef --gpus all -p 45164:8080 -v "$CLEF:/models:ro" ghcr.io/ggml-org/llama.cpp:server-cuda \
        -m /models/Clef-Flash-Q4_K_M.gguf --host 0.0.0.0 --port 8080 -c 32768 -ngl 99 -b 32768 -ub 4096 >/dev/null
      arm C1_clef_q4 bench-clef http://localhost:45164 clef ;;
    H1|H2)  # H2O-Lightning-4B v1.4.2 on the fork engine: H1 two-way (default), H2 one-way on the same build
      t0=$SECONDS; until docker image inspect ejev-bench/h2o:v1.4.2 >/dev/null 2>&1; do (( SECONDS - t0 > 3600 )) && { stamp "h2o image never arrived"; continue 2; }; sleep 15; done
      mode=$([ "$a" = H1 ] && echo 1 || echo 0)
      docker run -d --name bench-h2o --gpus all --network host --ipc host -e TWO_WAY=$mode -e ONE_ENGINE=1 \
        -e PORT=45165 -e VLLM_PORT=45168 -e GPU_UTIL=0.78 -e MAX_LEN=32768 -e HOME=/cache \
        -v "$BENCH/h2o/h2o-lightning-4b:/model" -v "$BENCH/h2o/cache:/cache" ejev-bench/h2o:v1.4.2 >/dev/null
      arm "$([ "$a" = H1 ] && echo H1_h2o_twoway || echo H2_h2o_oneway)" bench-h2o http://localhost:45165 h2oai/h2o-lightning-4b ;;
    T1)  # Torchcast Decision 4B v1.3.1, its bundled server (serial)
      docker run -d --name bench-torchcast --gpus all -p 45166:8011 -v "$BENCH/torchcast/torchcast-decision-4b:/model" \
        ejev-bench/torchcast:v1.3.1 >/dev/null
      arm T1_torchcast bench-torchcast http://localhost:45166 torchcast-decision-4b-v1.3 ;;
  esac
done
stamp "GPU window done"
