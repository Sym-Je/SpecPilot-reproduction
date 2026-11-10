#!/usr/bin/env bash
set -euo pipefail
REQUEST=${1:?request}
SOURCE=${2:?source archive}
OUTPUT=${3:?new private output}
DEADLINE=${4:?seconds}
[[ "$REQUEST" == /* && "$SOURCE" == /* && "$OUTPUT" == /* && ! -e "$OUTPUT" ]]
test "$(sha256sum "$0" | cut -d ' ' -f1)" = "${SP_SAMPLING_BOOTSTRAP_SHA:?}"
test "$(sha256sum "$SOURCE" | cut -d ' ' -f1)" = "${SP_SAMPLING_SOURCE_SHA:?}"
test "$(sha256sum "$REQUEST" | cut -d ' ' -f1)" = "${SP_SAMPLING_REQUEST_SHA:?}"
RUNTIME=$(mktemp -d /tmp/specpilot-sampling-XXXXXXXX)
umask 077
OWNER=$(stat -c '%u:%g' "$(dirname "$OUTPUT")")
exec 3>&1
exec > "${OUTPUT}.log" 2>&1
chown "$OWNER" "${OUTPUT}.log"
cleanup() {
  status=$?
  printf '%s\n' "$status" > "${OUTPUT}.exit-status"
  chown "$OWNER" "${OUTPUT}.exit-status"
  if [[ -d "$OUTPUT" ]]; then chown -R "$OWNER" "$OUTPUT"; fi
  tail -n 15 "${OUTPUT}.log" | cut -c1-1000 >&3
  [[ "$RUNTIME" == /tmp/specpilot-sampling-* ]] && rm -rf "$RUNTIME"
}
trap cleanup EXIT
tar -xf "$SOURCE" -C "$RUNTIME"
export SP_ROOT="$RUNTIME" SP_KIND=stock PYTHONDONTWRITEBYTECODE=1
source "$RUNTIME/harness/sglang/env.sh"
cd "$RUNTIME"
timeout --signal=TERM --kill-after=60s "$((DEADLINE-120))" "$SP_PY" -B "$RUNTIME/exp/sampling_run.py" run --request "$REQUEST" --directory "$OUTPUT"
