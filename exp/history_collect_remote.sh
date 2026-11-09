#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PRIVATE=${1:?prepared private directory}
PUBLIC=${2:?existing public directory}
[[ "$PRIVATE" == /* && -f "$PRIVATE/manifest.json" && -d "$PUBLIC" && ! -e "$PUBLIC/exit-status" ]]
umask 077
exec > "$PUBLIC/remote.log" 2>&1
chmod 0644 "$PUBLIC/remote.log"
trap 'status=$?; printf "%s\n" "$status" > "$PUBLIC/exit-status"; chmod 0644 "$PUBLIC/exit-status"; echo "[history-collection] lifecycle_exit=$status"' EXIT
cd "$ROOT"
source "$ROOT/harness/sglang/env.sh"
export PYTHONDONTWRITEBYTECODE=1
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
"$SP_PY" -B - <<'PY'
import importlib.metadata as metadata
import torch
assert metadata.version('sglang')=='0.5.20' and metadata.version('torch')=='2.13.0'
assert torch.cuda.device_count()==1 and 'H100' in torch.cuda.get_device_name(0)
print('PASS: pinned runtime and exactly one H100')
PY
timeout --signal=TERM --kill-after=60s 1440 "$SP_PY" -B "$ROOT/exp/history_collect.py" run \
  --directory "$PRIVATE" --public "$PUBLIC"
