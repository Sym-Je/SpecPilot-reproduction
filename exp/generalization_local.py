"""CPU-only blind quality completion after the remote GPU process has exited."""

import argparse
from contextlib import redirect_stderr,redirect_stdout
import json
import hashlib
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from exp.generalization_run import finish


def finalize(private,public):
    os.umask(0o077)
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '':
        raise ValueError('local quality/replay must explicitly disable CUDA visibility')
    if (public/'exit-status').read_text().strip() != '0' or not (public/'gpu-complete.json').exists():
        raise ValueError('remote GPU stage must complete successfully before local quality')
    root=json.loads((private/'manifest.json').read_text())
    for name,checksum in root['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=checksum:
            raise ValueError('local evaluator differs from the frozen GPU campaign source')
    if root['quality_location']!='local-cpu-sandbox':
        raise ValueError('quality location differs from the frozen protocol')
    dataset=json.loads(Path(root['dataset_path']).read_text())
    campaigns=[json.loads((private/f'cap-{cap}'/'manifest.json').read_text()) for cap in (2048,256,4096)]
    with (private/'local-quality.log').open('x') as log,redirect_stdout(log),redirect_stderr(log):
        finish(private,dataset,campaigns,public)
    print(json.dumps(dict(local_quality_complete=True,public_report=str(public/'result.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private',type=Path,required=True);parser.add_argument('--public',type=Path,required=True)
    args=parser.parse_args()
    finalize(args.private.resolve(),args.public.resolve())
