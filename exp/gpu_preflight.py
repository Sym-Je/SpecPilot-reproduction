"""Record offline GPU request checks, always blocked until a separate execution stage."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True

from harness.gpu_preflight import inspect_request


def source_pin():
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def main(arguments=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(arguments)
    with args.request.open('rb') as stream:payload=stream.read(65537)
    if len(payload)>65536:raise ValueError('request exceeds 64KiB')
    result=inspect_request(args.work,json.loads(payload),source_pin())
    with args.output.open('x') as stream:
        stream.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
    args.output.chmod(0o600)
    print(json.dumps(dict(status=result['status'],blockers=result['blockers'],
        submission_allowed=False,gpu_submissions=0)))
    return 75


if __name__=='__main__':
    sys.exit(main())
