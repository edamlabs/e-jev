# Bench-only image: Torchcast Decision 4B v1.3.1's bundled PyTorch server, the pins its README states.
FROM pytorch/pytorch:2.9.1-cuda12.8-cudnn9-devel
ENV TORCH_CUDA_ARCH_LIST="8.9" MAX_JOBS=8 PIP_NO_CACHE_DIR=1
RUN pip install "transformers==5.8.1" "flash-linear-attention==0.5.2" accelerate safetensors ninja packaging wheel setuptools \
 && pip install --no-build-isolation "causal-conv1d>=1.7"
WORKDIR /model
ENTRYPOINT ["python", "-m", "torchcast_decision.server", "--model", "/model", "--host", "0.0.0.0", "--port", "8011"]
