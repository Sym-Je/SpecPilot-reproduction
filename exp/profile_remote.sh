#!/usr/bin/env bash
set -euo pipefail
REQUEST=${1:?profile request}
SOURCE=${2:?trusted source archive}
OUTPUT=${3:?new evidence output}
DEADLINE=${4:?seconds}
[[ "$REQUEST" == /* && "$SOURCE" == /* && "$OUTPUT" == /* && ! -e "$OUTPUT" ]]
test "$(sha256sum "$0" | cut -d ' ' -f1)" = "${SP_PROFILE_BOOTSTRAP_SHA:?}"
test "$(sha256sum "$SOURCE" | cut -d ' ' -f1)" = "${SP_PROFILE_SOURCE_SHA:?}"
test "$(sha256sum "$REQUEST" | cut -d ' ' -f1)" = "${SP_PROFILE_REQUEST_SHA:?}"
RUNTIME="${OUTPUT}.runtime-source"
test ! -e "$RUNTIME"
mkdir -m 755 "$RUNTIME"
exec 3>&1
exec > "${OUTPUT}.log" 2>&1
cleanup() {
  status=$?
  printf '%s\n' "$status" > "${OUTPUT}.exit-status"
  tail -n 20 "${OUTPUT}.log" >&3
}
trap cleanup EXIT
tar -xf "$SOURCE" -C "$RUNTIME"
export SP_ROOT="$RUNTIME" SP_KIND=stock PYTHONDONTWRITEBYTECODE=1
source "$RUNTIME/harness/sglang/env.sh"
"$SP_PY" -B - <<'PY'
import importlib.metadata
import os
import torch
assert os.geteuid() == 0
assert importlib.metadata.version('sglang') == '0.5.20'
assert torch.cuda.device_count() == 1
assert 'H100' in torch.cuda.get_device_name(0)
print('PASS: root bootstrap, one H100 and SGLang 0.5.20', flush=True)
PY
timeout --signal=TERM --kill-after=60s "$((DEADLINE-120))" "$SP_PY" -B \
  "$RUNTIME/exp/profile_resource.py" remote --request "$REQUEST" --directory "$OUTPUT"
