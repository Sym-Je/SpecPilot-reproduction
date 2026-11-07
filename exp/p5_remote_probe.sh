#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:?new absolute output directory}
REFERENCE=${2:?frozen A1 directory}
[[ "$OUT" == /* && "$REFERENCE" == /* && ! -e "$OUT" && ! -e "$OUT.log" && ! -e "$OUT.exit-status" ]]
exec > "$OUT.log" 2>&1
trap 'status=$?; printf "%s\n" "$status" > "$OUT.exit-status"; echo "[p5-probe] lifecycle_exit=$status"' EXIT
cd "$ROOT"
source "$ROOT/harness/sglang/env.sh"
export PYTHONDONTWRITEBYTECODE=1
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
"$SP_PY" -B - <<'PY'
import importlib.metadata as metadata
import json
import torch
versions = {name: metadata.version(name) for name in ('sglang', 'torch', 'transformers')}
if versions['sglang'] != '0.5.20' or versions['torch'] != '2.13.0' or torch.cuda.device_count() != 2:
    raise RuntimeError('unexpected engine packages or GPU count')
if any('H100' not in torch.cuda.get_device_name(index) for index in (0, 1)):
    raise RuntimeError('expected two H100 GPUs')
print(json.dumps(versions), flush=True)
PY
timeout --signal=TERM --kill-after=120s 2400 "$SP_PY" -B "$ROOT/exp/p5_api_probe.py" \
    --out-dir "$OUT" --reference "$REFERENCE"
