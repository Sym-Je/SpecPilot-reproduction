"""General research capabilities owned by a trusted broker, not by the model."""

from pathlib import Path

from agents.autonomy import validate_action
from agents.exploration import file_sha
from harness.experiment_executor import execute_python,local_path


def dispatch(work,action,record):
    validate_action(action)
    work=Path(work).resolve()
    kind=action['kind']
    if kind in ('read_file','write_file','run_python'):
        path=local_path(work,action['path'])
        if kind!='read_file' and Path(action['path']).parts[0]!='scratch':
            raise ValueError('only scratch files may be changed or executed')
        if kind=='write_file':
            if path.suffix not in ('.py','.json','.txt'):raise ValueError('experiment file type required')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(action['content'])
            return dict(status='completed',sha256=file_sha(path),bytes=path.stat().st_size)
        if kind=='read_file':
            if not path.is_file():raise ValueError('regular workspace file required')
            return dict(status='completed',content=path.read_text()[:12000],sha256=file_sha(path))
        return execute_python(work,action['path'],record)
    if kind in ('read_stock','list_stock'):
        from exp.autonomy import STOCK,run_action
        if not local_path(STOCK,action.get('path',action.get('prefix'))).is_relative_to(STOCK):
            raise ValueError('stock scope required')
        return run_action(Path(record),'unused',action,0)
    return dict(status='returned',disposition=action['disposition'])
