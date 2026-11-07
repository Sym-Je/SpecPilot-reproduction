#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:?absolute new output directory required}
[[ "$OUT" == /* && ! -e "$OUT" && ! -e "$OUT.log" && ! -e "$OUT.exit-status" ]]
mkdir -p "$OUT"
exec > "$OUT.log" 2>&1
trap 'status=$?; printf "%s\n" "$status" > "$OUT.exit-status"; echo "[p5-null] lifecycle_exit=$status"' EXIT
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
source "$ROOT/harness/sglang/env.sh"
git cat-file -e "${P5_EXPECTED_COMMIT:?expected source commit required}^{commit}"
git diff --exit-code "$P5_EXPECTED_COMMIT" -- exp harness controller
echo "[p5-null] source=$P5_EXPECTED_COMMIT"
git rev-parse HEAD
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
test -r "$SP_TARGET/config.json"
test -r "$SP_DRAFT/config.json"
test -x "$CC"
test -x "$CXX"
"$SP_PY" -B - <<'PY'
import importlib.metadata as metadata
import json
import torch

versions = {name: metadata.version(name) for name in ('sglang', 'torch', 'transformers')}
if versions['sglang'] != '0.5.20' or versions['torch'] != '2.13.0':
    raise RuntimeError('unexpected engine dependency versions')
if torch.cuda.device_count() != 2:
    raise RuntimeError('expected two visible GPUs')
devices = [torch.cuda.get_device_properties(index) for index in range(2)]
if any('H100' not in device.name or device.total_memory < 75 * 1024 ** 3 for device in devices):
    raise RuntimeError('expected two H100 80GB GPUs')
print(json.dumps({'packages': versions, 'cuda': torch.version.cuda,
                  'gpus': [device.name for device in devices]}), flush=True)
PY
"$SP_PY" -m sglang.launch_server --help > "$OUT/launch-help.txt" 2>&1
for SESSION in 01 02; do
    timeout --signal=TERM --kill-after=120s 5400 "$SP_PY" -B "$ROOT/exp/p3_pair_run.py" stock stock \
        --gpus 0 1 --ports 30100 30110 --rounds 2 --per-suite 4 --max-new 2048 \
        --warmup 2 --startup-timeout 900 --out-dir "$OUT/session-$SESSION" --execute
    "$SP_PY" -B - "$OUT/session-$SESSION" <<'PY'
import json
from pathlib import Path
import sys
from controller.null_validation import validate_null
from exp.p3_pair_run import check_ports, inspect_gpus

directory = Path(sys.argv[1])
result = validate_null(directory)
with (directory / 'null_acceptance.json').open('x') as destination:
    json.dump(result, destination, indent=2)
    destination.write('\n')
check_ports([30100, 30110])
idle = inspect_gpus([0, 1])
with (directory / 'cleanup.json').open('x') as destination:
    json.dump(idle, destination, indent=2)
print(json.dumps(result), flush=True)
PY
done
"$SP_PY" -B - "$OUT" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
sessions = [json.loads((root / f'session-{number:02d}/null_acceptance.json').read_text())
            for number in (1, 2)]
result = {'sessions': sessions, 'precision_passed': all(item['precision_passed'] for item in sessions),
          'scope': 'two real null sessions; no correctness, promotion or sealed claim',
          'ledger_eligible': False}
with (root / 'null_acceptance.json').open('x') as destination:
    json.dump(result, destination, indent=2)
    destination.write('\n')
print('[p5-null] lifecycle complete; precision_passed=' + str(result['precision_passed']), flush=True)
PY
