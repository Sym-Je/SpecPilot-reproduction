#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:?absolute output directory required}
[[ "$OUT" == /* && ! -e "$OUT" && ! -e "$OUT.log" && ! -e "$OUT.exit-status" ]]
mkdir -p "$(dirname "$OUT")"
exec > "$OUT.log" 2>&1
trap 'exit_status=$?; printf "%s\n" "$exit_status" > "$OUT.exit-status"; echo "[p3-baseline] exit=$exit_status"' EXIT

cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
source "$ROOT/harness/sglang/env.sh"
git cat-file -e "${P3_EXPECTED_COMMIT:?expected code commit required}^{commit}"
git diff --exit-code "$P3_EXPECTED_COMMIT" -- exp harness controller
date -u
echo "[p3-baseline] expected_source_commit=$P3_EXPECTED_COMMIT"
git rev-parse HEAD
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
test -r "$SP_TARGET/config.json"
test -r "$SP_DRAFT/config.json"
test -x "$CC"
test -x "$CXX"

"$SP_PY" -B - <<'PY'
import importlib.metadata as metadata
import json
import sys
import torch

versions = {name: metadata.version(name) for name in ('sglang', 'torch', 'triton', 'transformers')}
if versions['sglang'] != '0.5.20' or versions['torch'] != '2.13.0':
    raise RuntimeError('unexpected engine dependency versions')
if torch.cuda.device_count() != 2:
    raise RuntimeError('expected exactly two visible GPUs')
devices = [torch.cuda.get_device_properties(index) for index in range(2)]
if any('H100' not in device.name or device.total_memory < 75 * 1024 ** 3 for device in devices):
    raise RuntimeError('expected two H100 80GB GPUs')
torch.cuda.init()
print(json.dumps({'python': sys.version, 'packages': versions, 'cuda': torch.version.cuda,
                  'gpus': [device.name for device in devices]}), flush=True)
PY

runner_status=0
timeout --signal=TERM --kill-after=120s 7200 "$SP_PY" -B "$ROOT/exp/p3_pair_run.py" ar stock \
    --gpus 0 1 --ports 30100 30110 --rounds 2 --per-suite 4 --max-new 2048 \
    --warmup 2 --startup-timeout 900 --out-dir "$OUT" --execute || runner_status=$?
echo "[p3-baseline] runner_exit=$runner_status"
[[ "$runner_status" == 0 || "$runner_status" == 1 ]] || exit "$runner_status"
test -s "$OUT/summary.json"
"$SP_PY" -B -c 'import json,sys; from harness.baseline_validation import validate_baseline; print(json.dumps(validate_baseline(sys.argv[1]), indent=2))' \
    "$OUT" > "$OUT/baseline_acceptance.json"
"$SP_PY" -B -c 'from exp.p3_pair_run import check_ports,inspect_gpus; check_ports([30100,30110]); print(inspect_gpus([0,1]))'
echo '[p3-baseline] measurement complete; reference result is separate from protocol completeness'
exit "$runner_status"
