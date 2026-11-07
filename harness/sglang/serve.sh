#!/usr/bin/env bash
# 启动 SGLang v0.5.20 stock server（H100 ×1, Qwen3.8-27B + DFlash2）。
#
# 参数口径来自论文 settings/h100_c1_qwen38-27b_dflash2/config.json 的 stock 侧：
#   --dtype bfloat16 --kv-cache-dtype auto --mamba-ssm-dtype float32
#   --attention-backend fa3 --mem-fraction-static 0.90 --max-running-requests 4
#   --cuda-graph-max-bs-decode 4 --chunked-prefill-size 8192 --disable-radix-cache
#   --speculative-algorithm DFLASH --speculative-num-draft-tokens 8  (= stock block_size 8)
#   --random-seed 0 --served-model-name <target basename>
#   后两项来自上游 research/scripts/launch.sh，serve.sh 里若不传就会落到随机 seed / 全路径名。
#
# 用法: bash harness/sglang/serve.sh [额外参数...]
#   PORT=30000 bash harness/sglang/serve.sh
#   bash harness/sglang/serve.sh --speculative-dflash-block-size 32
set -euo pipefail
SP_ROOT=${SP_ROOT:-/gpfs/users/jixinpeng/SpecDec/SpecPilot}
source "$SP_ROOT/harness/sglang/env.sh"

HOST=${HOST:-127.0.0.1}
PORT=${PORT:-30000}
NCCL_PORT=${NCCL_PORT:-30001}
DRAFT_TOKENS=${DRAFT_TOKENS:-8}

exec "$SP_PY" -m sglang.launch_server \
  --model-path "$SP_TARGET" \
  --speculative-algorithm DFLASH \
  --speculative-draft-model-path "$SP_DRAFT" \
  --speculative-num-draft-tokens "$DRAFT_TOKENS" \
  --dtype bfloat16 \
  --kv-cache-dtype auto \
  --mamba-ssm-dtype float32 \
  --attention-backend fa3 \
  --mem-fraction-static 0.90 \
  --max-running-requests 4 \
  --cuda-graph-max-bs-decode 4 \
  --chunked-prefill-size 8192 \
  --disable-radix-cache \
  --random-seed 0 \
  --served-model-name "$(basename "$SP_TARGET")" \
  --host "$HOST" --port "$PORT" --nccl-port "$NCCL_PORT" \
  "$@"
