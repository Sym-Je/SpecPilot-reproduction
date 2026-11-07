#!/usr/bin/env bash
# P3 —— 三臂配对测量的**单卡单臂**执行单元（由 NorthJob / 本机调度器调用）。
#
# 一次调用只跑一根臂：起 server → 预热 → 跑固定请求集 → 落 JSONL → 停 server。
# 为什么不让这个脚本自己配对：27B 一条臂占 78/80 GB，两臂必须两张卡；
# 配对逻辑在 controller/http_transport.py，由上层（开两个 pod 或两张卡）驱动。
#
# 用法（在一张 H100 上）：
#   bash exp/p3_pair.sh <arm> <gpu> <port> <out.jsonl>
#     arm = ar | stock | final
#
# 输出每行：{"id","arm","block","tree_sha","prompt_tokens","completion_tokens",
#           "latency_s","spec_verify_ct","tau","output_sha256","finish_reason"}
set -euo pipefail
ARM=${1:?arm: ar|stock|final}; GPU=${2:-0}; PORT=${3:-30000}; OUT=${4:?out.jsonl}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

case $ARM in
  ar)    KIND=stock; SPEC=();                          BLOCK=0  ;;
  stock) KIND=stock; SPEC=(--speculative-algorithm DFLASH) ; BLOCK=8  ;;
  final) KIND=final; SPEC=(--speculative-algorithm DFLASH) ; BLOCK=32 ;;
  *) echo "unknown arm $ARM"; exit 2 ;;
esac
export SP_KIND=$KIND
source "$ROOT/harness/sglang/env.sh"
if [[ "$ARM" == final ]]; then
  # 46 个 SPECPILOT_* 由 config.json 派生（gen_final_env.py），缺失就硬失败：
  # 悄悄退回 stock 会让 final 臂测出的其实是 stock，而账本上看不出来。
  FIN_ENV=${SP_FINAL_ENV:-$SP_DATA/work/env/${SP_SETTING}-final.env}
  [[ -f "$FIN_ENV" ]] || "$SP_PY" "$ROOT/harness/sglang/gen_final_env.py" --out "$FIN_ENV"
  "$SP_PY" "$ROOT/harness/sglang/gen_final_env.py" --out "$FIN_ENV" --check
  source "$FIN_ENV"
  # block 以 config 为准（32），不信脚本里写死的数
  BLOCK=$SPECPILOT_BLOCK_SIZE
fi

SERVER_LOG=${P3_SERVER_LOG:-$ROOT/logs/p3-${ARM}-${PORT}.log}
mkdir -p "$(dirname "$OUT")" "$ROOT/logs" "$(dirname "$SERVER_LOG")"
echo "[p3] arm=$ARM gpu=$GPU port=$PORT block=$BLOCK tree=$SP_TREE_SHA" >&2

ARGS=(--model-path "$SP_TARGET"
      --dtype bfloat16 --kv-cache-dtype auto --mamba-ssm-dtype float32
      --attention-backend fa3 --mem-fraction-static 0.90
      --max-running-requests 4 --cuda-graph-max-bs-decode 4
      --chunked-prefill-size 8192 --disable-radix-cache
      --random-seed 0 --served-model-name "$(basename "$SP_TARGET")"
      --host 127.0.0.1 --port "$PORT" --nccl-port "$((PORT + 1))")
if [[ "$ARM" != ar ]]; then
  ARGS+=(--speculative-draft-model-path "$SP_DRAFT"
         "${SPEC[@]}" --speculative-num-draft-tokens "$BLOCK")
fi

CUDA_VISIBLE_DEVICES=$GPU "$SP_PY" -m sglang.launch_server "${ARGS[@]}" \
  > "$SERVER_LOG" 2>&1 &
SRV=$!
trap 'kill -TERM $SRV 2>/dev/null || true; wait $SRV 2>/dev/null || true' EXIT

# 等就绪（27B 冷启动 ~220-400 s，派生树首启更久）
READY_POLLS=${P3_READY_POLLS:-300}
for i in $(seq 1 "$READY_POLLS"); do
  if python3 -c "import urllib.request,sys;urllib.request.urlopen('http://127.0.0.1:$PORT/model_info',timeout=3)" 2>/dev/null; then
    echo "[p3] ready after $((i*2))s" >&2; break; fi
  sleep 2
  kill -0 $SRV 2>/dev/null || { echo "[p3] server died"; tail -40 "$SERVER_LOG"; exit 1; }
  [[ $i == "$READY_POLLS" ]] && { echo "[p3] timeout"; exit 1; }
done

if [[ ${P3_SERVER_ONLY:-0} == 1 ]]; then
  wait "$SRV"
  exit $?
fi

export P3_URL="http://127.0.0.1:$PORT" P3_ARM="$ARM" P3_BLOCK="$BLOCK" \
       P3_TREE_SHA="$SP_TREE_SHA" P3_OUT="$OUT"
"$SP_PY" "$ROOT/harness/sglang/run_arm.py"
