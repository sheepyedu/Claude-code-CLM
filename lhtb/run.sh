#!/bin/bash
set -eu
repo="$(cd "$(dirname "$0")/.." && pwd)"
work=/mount-data/Claude-code-CLM/experiments/workbuddy-20261118
data=/mount-data/Datasets/LHTB-2.0/LHTB-7ca0cacea9bf6a0694eaad7306bed794eaaaabce
export PYTHONPATH="$repo:$data/harbor/src:$data/harbor/packages/rewardkit/src:$work/serial-cache-prefix"
export LITELLM_LOCAL_MODEL_COST_MAP=True
export PATH="/mount-data/yangyang-h20-2gpu-train-20261107/env/skill100-20261110/runtime/usr/bin:$PATH"
export DOCKER_HOST=unix:///var/docker/proxy/docker-proxy.sock
export DOCKER_CONFIG="$work/docker-config"
export DOCKER_BUILDKIT=0
exec "$work/.venv/bin/python" -m lhtb.run "$@"
