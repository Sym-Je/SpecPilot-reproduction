#!/usr/bin/env bash
set -euo pipefail
ROLE=${1:?ar|stock|scorer}
GPU=${2:?GPU UUID}
PORT=${3:?port}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export SP_KIND=stock
source "$ROOT/harness/sglang/env.sh"
ARGS=(--model-path "$SP_TARGET" --dtype bfloat16 --kv-cache-dtype auto
      --mamba-ssm-dtype float32 --attention-backend fa3
      --max-running-requests 4 --cuda-graph-max-bs-decode 4
      --chunked-prefill-size 8192 --disable-radix-cache --random-seed 0
      --served-model-name "$(basename "$SP_TARGET")"
      --host 127.0.0.1 --port "$PORT" --nccl-port "$((PORT + 1))")
case "$ROLE" in
    ar) ARGS+=(--mem-fraction-static 0.90) ;;
    stock) ARGS+=(--mem-fraction-static 0.90 --speculative-algorithm DFLASH
                 --speculative-draft-model-path "$SP_DRAFT" --speculative-num-draft-tokens 8) ;;
    scorer) ARGS+=(--mem-fraction-static 0.75 --enable-fp32-lm-head
                  --enable-return-hidden-states --return-hidden-states-mode last) ;;
    *) echo "unsupported correctness server role: $ROLE" >&2; exit 2 ;;
esac
printf '[p5-serve] role=%s gpu=%s tree=%s\n' "$ROLE" "$GPU" "$SP_TREE_SHA"
printf '%q ' "$SP_PY" -m sglang.launch_server "${ARGS[@]}"
printf '\n'
export CUDA_VISIBLE_DEVICES=$GPU
exec "$SP_PY" -m sglang.launch_server "${ARGS[@]}" > "${P5_SERVER_LOG:?server log required}" 2>&1
