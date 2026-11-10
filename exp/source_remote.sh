#!/usr/bin/env bash
set -euo pipefail
REQUEST=${1:?frozen request}
SOURCE=${2:?trusted source archive}
OUTPUT=${3:?new output}
DEADLINE=${4:?seconds}
[[ "$REQUEST" == /* && "$SOURCE" == /* && "$OUTPUT" == /* && ! -e "$OUTPUT" ]]
test "$(sha256sum "$0" | cut -d ' ' -f1)" = "${SP_SOURCE_BOOTSTRAP_SHA:?}"
test "$(sha256sum "$SOURCE" | cut -d ' ' -f1)" = "${SP_SOURCE_ARCHIVE_SHA:?}"
test "$(sha256sum "$REQUEST" | cut -d ' ' -f1)" = "${SP_SOURCE_REQUEST_SHA:?}"
RUNTIME=$(mktemp -d /tmp/specpilot-source-runtime-XXXXXXXX)
exec 3>&1
exec > "${OUTPUT}.log" 2>&1
cleanup() {
  status=$?
  printf '%s\n' "$status" > "${OUTPUT}.exit-status"
  tail -n 25 "${OUTPUT}.log" >&3
  [[ "$RUNTIME" == /tmp/specpilot-source-runtime-* ]] && rm -rf "$RUNTIME"
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
assert torch.cuda.device_count() == 2
assert all('H100' in torch.cuda.get_device_name(index) for index in (0, 1))
print('PASS: root bootstrap, two H100 and SGLang 0.5.20', flush=True)
PY
timeout --signal=TERM --kill-after=60s "$((DEADLINE-120))" "$SP_PY" -B "$RUNTIME/exp/source_research.py" run --request "$REQUEST" --directory "$OUTPUT"
