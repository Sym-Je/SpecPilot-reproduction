#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PRIVATE=${1:?new private output}
PUBLIC=${2:?existing public output}
BUNDLE=${3:?observer bundle}
ORIGINAL=${4:?original stock timing}
[[ "$PRIVATE" == /* && ! -e "$PRIVATE" && -d "$PUBLIC" && ! -e "$PUBLIC/exit-status" ]]
umask 077
exec > "$PUBLIC/remote.log" 2>&1
chmod 0644 "$PUBLIC/remote.log"
trap 'status=$?; printf "%s\n" "$status" > "$PUBLIC/exit-status"; chmod 0644 "$PUBLIC/exit-status"; echo "[step-replay] lifecycle_exit=$status"' EXIT
cd "$ROOT"
source "$ROOT/harness/sglang/env.sh"
export PYTHONDONTWRITEBYTECODE=1
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
"$SP_PY" -B - <<'PY'
import importlib.metadata as metadata
import torch
assert metadata.version('sglang')=='0.5.20' and metadata.version('torch')=='2.13.0'
assert torch.cuda.device_count()==2
assert all('H100' in torch.cuda.get_device_name(index) for index in (0,1))
print('PASS: pinned runtime and two H100')
PY
CUDA_VISIBLE_DEVICES='' "$SP_PY" -B -m unittest harness.test_p12_step_replay
timeout --signal=TERM --kill-after=120s 3600 "$SP_PY" -B "$ROOT/exp/step_replay.py" run \
  --directory "$PRIVATE" --public "$PUBLIC" --bundle "$BUNDLE" --original "$ORIGINAL"
