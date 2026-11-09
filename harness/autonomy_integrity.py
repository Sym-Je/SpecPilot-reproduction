"""Independent, read-only integrity checks for consumed inputs and final workspaces."""

import argparse
import hashlib
import json
from pathlib import Path

from harness.experiment_executor import local_path


def check(directory):
    directory=Path(directory)
    evidence=(directory/'evidence.json').read_bytes()
    state=json.loads((directory/'state.json').read_text())
    files=0
    for direction,task in state['tasks'].items():
        work=local_path(directory/'work',direction)
        copied=local_path(work,'inputs/evidence.json')
        if copied.read_bytes()!=evidence:raise ValueError('consumed input snapshot differs from issued evidence')
        allowed=set(task['files'])|{'inputs/evidence.json'}
        actual=set()
        for path in work.rglob('*'):
            if path.is_symlink():raise ValueError('workspace symlink rejected')
            if path.is_file():actual.add(str(path.relative_to(work)))
        if actual!=allowed:raise ValueError('unaccounted workspace files')
        for name,expected in task['files'].items():
            if hashlib.sha256(local_path(work,name).read_bytes()).hexdigest()!=expected:
                raise ValueError('final authored file changed')
            files+=1
    runs=0
    for path in sorted((directory/'executions').iterdir()):
        if not (path/'stderr').read_bytes().startswith(b'SP_ISOLATION_READY\n'):
            raise ValueError('kernel isolation bootstrap evidence missing')
        runs+=1
    return dict(workspace_inputs_verified=len(state['tasks']),final_authored_files_verified=files,
        isolated_execution_bootstraps_verified=runs,evidence_sha256=hashlib.sha256(evidence).hexdigest(),
        scope='independent input/file integrity only; no scientific or performance verdict')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(check(args.directory)))
