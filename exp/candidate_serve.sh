#!/usr/bin/env bash
set -euo pipefail
BUNDLE=${1:?candidate bundle}
ENABLED=${2:?explicit mode}
RECEIPT=${3:?new runtime receipt}
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[[ "$BUNDLE" == /* && -s "$BUNDLE/engine/TREE_SHA" ]]
export SP_ROOT="$ROOT" SP_KIND=stock SP_ENGINE="$BUNDLE/engine"
source "$ROOT/harness/sglang/env.sh"
[[ "$SP_ENGINE" == "$BUNDLE/engine" ]]
ARGS=()
case "$ENABLED" in
  0) ;;
  1) ARGS+=(--enabled) ;;
  *) exit 2 ;;
esac
exec "$SP_PY" -B "$ROOT/exp/candidate_smoke.py" serve --bundle "$BUNDLE" --receipt "$RECEIPT" "${ARGS[@]}"
