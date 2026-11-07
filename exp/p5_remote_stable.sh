#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:?absolute new output directory required}
REFERENCE=${2:?frozen A1 directory required}
[[ "$OUT" == /* && "$REFERENCE" == /* && ! -e "$OUT" && ! -e "$OUT.log" && ! -e "$OUT.exit-status" ]]
mkdir -p "$OUT"
exec > "$OUT.log" 2>&1
trap 'status=$?; printf "%s\n" "$status" > "$OUT.exit-status"; echo "[p5-stable] lifecycle_exit=$status"' EXIT
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
source "$ROOT/harness/sglang/env.sh"
EXTRA=()
if [[ "${P5_PIN_CPUS:-0}" == 1 ]]; then
    EXTRA+=(--pin-cpus)
fi
git cat-file -e "${P5_EXPECTED_COMMIT:?expected source commit required}^{commit}"
git diff --exit-code "$P5_EXPECTED_COMMIT" -- exp harness controller
echo "[p5-stable] source=$P5_EXPECTED_COMMIT reference=$REFERENCE"
git rev-parse HEAD
nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv
"$SP_PY" -B - "$REFERENCE" <<'PY'
import importlib.metadata as metadata
import json
import sys
import torch
from harness.baseline_validation import validate_baseline

if not validate_baseline(sys.argv[1])['diagnostic_passed']:
    raise RuntimeError('frozen A1 did not pass')
versions = {name: metadata.version(name) for name in ('sglang', 'torch', 'transformers')}
if versions['sglang'] != '0.5.20' or versions['torch'] != '2.13.0':
    raise RuntimeError('unexpected engine versions')
if torch.cuda.device_count() != 2:
    raise RuntimeError('expected exactly two GPUs')
devices = [torch.cuda.get_device_properties(index) for index in (0, 1)]
if any('H100' not in device.name or device.total_memory < 75 * 1024 ** 3 for device in devices):
    raise RuntimeError('expected two H100 80GB GPUs')
print(json.dumps({'packages': versions, 'cuda': torch.version.cuda, 'gpus': [device.name for device in devices]}), flush=True)
PY
"$SP_PY" -B - "$OUT" <<'PY'
import json
from pathlib import Path
import sys
from exp.p3_pair_run import wait_for_idle
from harness.telemetry import Telemetry

root = Path(sys.argv[1])
gpus = wait_for_idle([0, 1])
sample = Telemetry([], gpus, root / 'unused.jsonl').sample()
with (root / 'telemetry-preflight.json').open('x') as destination:
    json.dump(sample, destination, indent=2)
if 'error' in sample or len(sample.get('gpus', [])) != 2:
    raise RuntimeError('GPU telemetry preflight failed')
PY
for SESSION in 01 02; do
    timeout --signal=TERM --kill-after=120s 5400 "$SP_PY" -B "$ROOT/exp/p3_pair_run.py" stock stock \
        --stable-null "${EXTRA[@]}" --gpus 0 1 --ports 30100 30110 --rounds 4 --per-suite 4 --max-new 2048 \
        --warmup 2 --startup-timeout 900 --out-dir "$OUT/session-$SESSION" --execute
    "$SP_PY" -B - "$OUT/session-$SESSION" "$REFERENCE" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
from controller.stability_validation import validate_stable
from exp.p3_pair_run import check_ports, inspect_gpus

directory, reference = map(Path, sys.argv[1:])
frozen = json.loads((reference / 'manifest.json').read_text())
manifest = json.loads((directory / 'manifest.json').read_text())
if any(manifest[key] != frozen[key] for key in ('model_path', 'declared_models', 'sampling')):
    raise RuntimeError('model or sampling drift from frozen A1')
result = validate_stable(directory, frozen['requests'])
if manifest.get('cpu_pinning'):
    from harness.cpu_affinity import validate_cpu_bound
    cpu_result = validate_cpu_bound(directory, frozen['requests'])
    with (directory / 'cpu_acceptance.json').open('x') as destination:
        json.dump(cpu_result, destination, indent=2)
result['reference_manifest_sha256'] = hashlib.sha256((reference / 'manifest.json').read_bytes()).hexdigest()
with (directory / 'stable_acceptance.json').open('x') as destination:
    json.dump(result, destination, indent=2)
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
sessions = [json.loads((root / f'session-{number:02d}/stable_acceptance.json').read_text()) for number in (1, 2)]
result = {'sessions': sessions, 'stable_passed': all(item['stable_passed'] for item in sessions),
          'precision_passed': all(item['precision_passed'] for item in sessions),
          'scope': 'two predeclared stable-null sessions; no correctness or promotion claim', 'ledger_eligible': False}
with (root / 'stable_acceptance.json').open('x') as destination:
    json.dump(result, destination, indent=2)
print('[p5-stable] lifecycle complete; stable_passed=' + str(result['stable_passed']), flush=True)
PY
