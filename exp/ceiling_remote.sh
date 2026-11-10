#!/usr/bin/env bash
set -euo pipefail
REQUEST=${1:?frozen request}
SOURCE=${2:?frozen archive}
OUTPUT=${3:?new private output}
DEADLINE=${4:?seconds}
[[ "$REQUEST" == /* && "$SOURCE" == /* && "$OUTPUT" == /* && ! -e "$OUTPUT" ]]
test "$(sha256sum "$0" | cut -d ' ' -f1)" = "${SP_CEILING_BOOTSTRAP_SHA:?}"
test "$(sha256sum "$SOURCE" | cut -d ' ' -f1)" = "${SP_CEILING_SOURCE_SHA:?}"
test "$(sha256sum "$REQUEST" | cut -d ' ' -f1)" = "${SP_CEILING_REQUEST_SHA:?}"
RUNTIME=$(mktemp -d /tmp/specpilot-ceiling-XXXXXXXX)
umask 077
OWNER=$(stat -c '%u:%g' "$(dirname "$OUTPUT")")
exec 3>&1
exec > "${OUTPUT}.log" 2>&1
cleanup() {
  status=$?
  printf '%s\n' "$status" > "${OUTPUT}.exit-status"
  chown "$OWNER" "${OUTPUT}.log" "${OUTPUT}.exit-status"
  if [[ -d "$OUTPUT" ]]; then chown -R "$OWNER" "$OUTPUT"; fi
  tail -n 12 "${OUTPUT}.log" | cut -c1-800 >&3
  [[ "$RUNTIME" == /tmp/specpilot-ceiling-* ]] && rm -rf "$RUNTIME"
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
timeout --signal=TERM --kill-after=60s "$((DEADLINE-120))" "$SP_PY" -B "$RUNTIME/exp/ceiling_run.py" run --request "$REQUEST" --directory "$OUTPUT"
