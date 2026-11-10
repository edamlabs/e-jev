# Bench-only image: stock vLLM 0.30.0 + h2oai/vllm @b05cc29 (per-request two-way attention), verified file by file.
FROM vllm/vllm-openai:v0.30.0
ARG FORK=b05cc29ab813895947954c268c4ec41ca0da1306
ENV PIP_NO_CACHE_DIR=1
RUN pip install "transformers==5.20.2" "torchcodec==0.17.0"
COPY vllm_per_request_attention.SHA256SUMS /opt/sums
RUN apt-get update -qq && apt-get install -y -qq git >/dev/null && SRC=$(mktemp -d) \
 && git -C "$SRC" init -q && git -C "$SRC" fetch -q --depth 1 https://github.com/h2oai/vllm "$FORK" && git -C "$SRC" checkout -q FETCH_HEAD \
 && SITE=$(python3 -c 'import os, vllm; print(os.path.dirname(os.path.dirname(vllm.__file__)))') \
 && while read -r sha path; do mkdir -p "$SITE/$(dirname "$path")" && cp "$SRC/$path" "$SITE/$path"; done < /opt/sums \
 && (cd "$SITE" && sha256sum -c --quiet /opt/sums) && rm -rf "$SRC" && find "$SITE/vllm" -name __pycache__ -prune -exec rm -rf {} +
ENTRYPOINT ["bash", "/model/serve.sh"]
