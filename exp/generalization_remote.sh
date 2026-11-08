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
chmod 0644 "$PUBLIC/remote.log"
trap 'status=$?; printf "%s\n" "$status" > "$PUBLIC/exit-status"; chmod 0644 "$PUBLIC/exit-status"; echo "[generalization] lifecycle_exit=$status"' EXIT
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
CUDA_VISIBLE_DEVICES='' "$SP_PY" -B - <<'PY' > "$PUBLIC/sandbox-capability.json"
import ctypes.util,json,os,platform
from controller.landlock import abi_version
print(json.dumps(dict(uid=os.getuid(),kernel=platform.release(),landlock_abi=abi_version(),seccomp_library=ctypes.util.find_library('seccomp'))))
PY
chmod 0644 "$PUBLIC/sandbox-capability.json"
status=0
printf '%s' '{"code":"assert 1+1==2","tests":""}' | CUDA_VISIBLE_DEVICES='' "$SP_PY" -I -B \
  "$ROOT/exp/generalization_quality.py" --worker > "$PUBLIC/synthetic-sandbox-probe.log" 2>&1 || status=$?
printf '%s\n' "$status" > "$PUBLIC/synthetic-sandbox-probe.exit"
chmod 0644 "$PUBLIC/synthetic-sandbox-probe.log" "$PUBLIC/synthetic-sandbox-probe.exit"
CUDA_VISIBLE_DEVICES='' "$SP_PY" -B - <<'PY'
import unittest
from harness.test_p7_generalization import GeneralizationTests
names=[name for name in unittest.defaultTestLoader.getTestCaseNames(GeneralizationTests) if 'quality_sandbox' not in name]
suite=unittest.TestSuite(GeneralizationTests(name) for name in names)
raise SystemExit(not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful())
PY
timeout --signal=TERM --kill-after=120s 28800 "$SP_PY" -B "$ROOT/exp/generalization_run.py" \
  --private "$PRIVATE" --dataset "$DATASET" --public "$PUBLIC" --defer-quality
