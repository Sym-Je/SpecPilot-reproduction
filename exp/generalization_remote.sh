#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PRIVATE=${1:?new private output directory}
DATASET=${2:?frozen blind dataset JSON}
PUBLIC=${3:?existing public status directory}
[[ "$PRIVATE" == /* && ! -e "$PRIVATE" && -s "$DATASET" && -d "$PUBLIC" ]]
[[ ! -e "$PUBLIC/exit-status" && ! -e "$PUBLIC/result.json" ]]
umask 077
exec > "$PUBLIC/remote.log" 2>&1
trap 'status=$?; printf "%s\n" "$status" > "$PUBLIC/exit-status"; echo "[generalization] lifecycle_exit=$status"' EXIT
cd "$ROOT"
source "$ROOT/harness/sglang/env.sh"
export PYTHONDONTWRITEBYTECODE=1
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
"$SP_PY" -B - <<'PY'
import importlib.metadata as metadata
import torch
assert metadata.version('sglang') == '0.5.20'
assert metadata.version('torch') == '2.13.0'
assert torch.cuda.device_count() == 2
assert all('H100' in torch.cuda.get_device_name(index) for index in (0,1))
PY
CUDA_VISIBLE_DEVICES='' "$SP_PY" -B -m unittest discover -s harness -p 'test_p7_*.py'
timeout --signal=TERM --kill-after=120s 28800 "$SP_PY" -B "$ROOT/exp/generalization_run.py" \
  --private "$PRIVATE" --dataset "$DATASET" --public "$PUBLIC"
