#!/usr/bin/env bash
set -euo pipefail
REQUEST=${1:?frozen request}
SOURCE=${2:?frozen trusted archive}
OUTPUT=${3:?new output}
DEADLINE=${4:?seconds}
[[ "$REQUEST" == /* && "$SOURCE" == /* && "$OUTPUT" == /* && ! -e "$OUTPUT" ]]
test "$(sha256sum "$0" | cut -d ' ' -f1)" = "${SP_ENGINE_BOOTSTRAP_SHA:?}"
test "$(sha256sum "$SOURCE" | cut -d ' ' -f1)" = "${SP_ENGINE_SOURCE_SHA:?}"
test "$(sha256sum "$REQUEST" | cut -d ' ' -f1)" = "${SP_ENGINE_REQUEST_SHA:?}"
RUNTIME=$(mktemp -d /tmp/specpilot-engine-research-XXXXXXXX)
umask 077
OWNER=$(stat -c '%u:%g' "$(dirname "$OUTPUT")")
exec 3>&1
exec > "${OUTPUT}.log" 2>&1
chown "$OWNER" "${OUTPUT}.log"
cleanup() {
  status=$?
  printf '%s\n' "$status" > "${OUTPUT}.exit-status"
  chown "$OWNER" "${OUTPUT}.exit-status"
  tail -n 20 "${OUTPUT}.log" >&3
  [[ "$RUNTIME" == /tmp/specpilot-engine-research-* ]] && rm -rf "$RUNTIME"
}
trap cleanup EXIT
tar -xf "$SOURCE" -C "$RUNTIME"
export SP_ROOT="$RUNTIME" SP_KIND=stock PYTHONDONTWRITEBYTECODE=1
source "$RUNTIME/harness/sglang/env.sh"
"$SP_PY" -B - <<'PY'
import importlib.metadata as metadata
import torch
assert metadata.version('sglang') == '0.5.20'
assert torch.cuda.device_count() == 2
assert all('H100' in torch.cuda.get_device_name(index) for index in (0,1))
print('PASS: two H100 and SGLang 0.5.20', flush=True)
PY
timeout --signal=TERM --kill-after=60s "$((DEADLINE-120))" "$SP_PY" -B "$RUNTIME/exp/engine_research.py" run --request "$REQUEST" --directory "$OUTPUT"
