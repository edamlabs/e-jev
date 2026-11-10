set -uo pipefail
cd /home/damien/workspaces/damien/e-jev
R=.reports/2026-11-10_backends
uv run python scripts/backend_bench.py A2_gemma_reading http://localhost:45177 --file .cache/labeled.jsonl --file .cache/spanish.jsonl --out $R/A2_gemma_reading.json --lat-per-kind 30 --model gemma4-26b-a4b
bash scripts/evals_bakeoff.sh A2_gemma_reading http://localhost:45177 12
echo ARM_DONE
