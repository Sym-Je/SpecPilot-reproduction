#!/usr/bin/env bash
set -euo pipefail
REQUEST=${1:?frozen agent request}
SOURCE=${2:?frozen trusted source archive}
OUTPUT=${3:?new persistent output}
[[ "$REQUEST" == /* && "$SOURCE" == /* && "$OUTPUT" == /* && ! -e "$OUTPUT" ]]
test "$(sha256sum "$0" | cut -d ' ' -f1)" = "${SP_GPU_BOOTSTRAP_SHA:?}"
test "$(sha256sum "$SOURCE" | cut -d ' ' -f1)" = "${SP_GPU_SOURCE_SHA:?}"
RUNTIME=$(mktemp -d /tmp/specpilot-gpu-autonomy-XXXXXXXX)
umask 077
exec > "${OUTPUT}.log" 2>&1
cleanup() {
  status=$?
  printf '%s\n' "$status" > "${OUTPUT}.exit-status"
  [[ "$RUNTIME" == /tmp/specpilot-gpu-autonomy-* ]] && rm -rf "$RUNTIME"
}
trap cleanup EXIT
tar -xf "$SOURCE" -C "$RUNTIME"
export SP_ROOT="$RUNTIME" SP_KIND=stock
source "$RUNTIME/harness/sglang/env.sh"
timeout --signal=TERM --kill-after=30s 900 "$SP_PY" -B "$RUNTIME/exp/gpu_autonomy_remote.py" --request "$REQUEST" --output "$OUTPUT"
