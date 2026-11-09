"""Prepare dependency-only checks, not a direction's scientific experiment."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from exp.gpu_autonomy import frozen_source, prepare_submission
from harness.gpu_autonomy import freeze_request

DEPENDENCY_CHECK = '''import json
import importlib
import torch
module = importlib.import_module("sglang.kernels.ops.attention.flash_attention")
assert callable(module.flash_attn_with_kvcache)
assert torch.cuda.is_available() and "H100" in torch.cuda.get_device_name(0)
torch.cuda.synchronize()
print(json.dumps({"dependencies_imported": True, "device": torch.cuda.get_device_name(0), "scope": "dependency preflight only; no scientific measurement"}))
'''


def prepare(root):
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    work = root / 'operator-work'
    (work / 'scratch').mkdir(parents=True)
    (work / 'inputs').mkdir()
    (work / 'inputs/evidence.json').write_text(json.dumps(dict(scope='trusted dependency-only preflight, not an agent experiment')))
    for name in ('dependency.py', 'verify.py'):
        (work / 'scratch' / name).write_text(DEPENDENCY_CHECK)
    request = root / 'gpu-01'
    manifest = freeze_request(work, dict(kind='run_gpu_python', path='scratch/dependency.py', acceptance='scratch/verify.py'),
        request, attempts=0, contract='stage2-preflight')
    source = frozen_source(request)
    return prepare_submission(request, source, root / 'remote-01', 'specpilot-stage2-dependencies-20261109-b01', manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output.resolve()), sort_keys=True))
