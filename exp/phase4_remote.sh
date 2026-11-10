#!/usr/bin/env bash
set -euo pipefail
REQUEST=${1:?controller request}
SOURCE=${2:?trusted source archive}
OUTPUT=${3:?new output}
DEADLINE=${4:?seconds}
[[ "$REQUEST" == /* && "$SOURCE" == /* && "$OUTPUT" == /* && ! -e "$OUTPUT" ]]
test "$(sha256sum "$0" | cut -d ' ' -f1)" = "${SP_PHASE4_BOOTSTRAP_SHA:?}"
test "$(sha256sum "$SOURCE" | cut -d ' ' -f1)" = "${SP_PHASE4_SOURCE_SHA:?}"
test "$(sha256sum "$REQUEST" | cut -d ' ' -f1)" = "${SP_PHASE4_REQUEST_SHA:?}"
umask 077
mkdir -m 755 "$OUTPUT"
mkdir -m 700 "$OUTPUT/private"
RUNTIME="$OUTPUT/private/runtime-source"
mkdir -m 700 "$RUNTIME"
exec 3>&1
exec > "$OUTPUT/private/bootstrap.log" 2>&1
cleanup() {
  status=$?
  printf '%s\n' "$status" > "$OUTPUT/private/remote-exit-status"
  if [[ "$status" == 0 ]]; then
    printf '{"status":"controller_evidence_complete","t3_passed":false,"raw_logs_private":true}\n' >&3
  else
    printf '{"status":"blocked","t3_passed":false,"raw_logs_private":true}\n' >&3
  fi
}
trap cleanup EXIT
tar -xf "$SOURCE" -C "$RUNTIME"
export SP_ROOT="$RUNTIME" SP_KIND=stock PYTHONDONTWRITEBYTECODE=1
source "$RUNTIME/harness/sglang/env.sh"
timeout --signal=TERM --kill-after=60s "$((DEADLINE-120))" "$SP_PY" -B \
  "$RUNTIME/exp/phase4_resource.py" remote --request "$REQUEST" --output "$OUTPUT"
