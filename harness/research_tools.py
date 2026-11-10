"""General research capabilities owned by a trusted broker, not by the model."""

from pathlib import Path

from agents.autonomy import validate_action
from agents.exploration import file_sha
from harness.experiment_executor import execute_python,local_path


def dispatch(work,action,record):
    validate_action(action)
    work=Path(work).resolve()
    kind=action['kind']
    if kind=='help':
        return dict(status='completed', actions=dict(
            read_file=dict(kind='read_file',path='inputs/evidence.json',offset=0),
            write_file=dict(kind='write_file',path='scratch/check.py',content='Python source text'),
            run_python=dict(kind='run_python',path='scratch/check.py'),
            list_stock=dict(kind='list_stock',prefix='python/sglang/',offset=0),
            read_stock=dict(kind='read_stock',path='python/sglang/srt/existing.py',offset=0)),
            note='Examples describe fields, not executable host paths; only authorized workspace and stock are accessible.')
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
            content=path.read_text()
            offset=action.get('offset',0)
            if offset>len(content):raise ValueError('offset exceeds workspace file length')
            end=min(len(content),offset+12000)
            return dict(status='completed',content=content[offset:end],sha256=file_sha(path),
                offset=offset,total_chars=len(content),next_offset=end if end<len(content) else None)
        result=execute_python(work,action['path'],record)
        result['workspace_code_sha256']={path.relative_to(work).as_posix():file_sha(local_path(work,path.relative_to(work).as_posix()))
            for path in (work/'scratch').rglob('*.py')}
        result['workspace_file_sha256']={path.relative_to(work).as_posix():file_sha(local_path(work,path.relative_to(work).as_posix()))
            for path in (work/'scratch').rglob('*') if path.is_file() and path.suffix in ('.py','.json')}
        return result
    if kind in ('read_stock','list_stock'):
        from exp.autonomy import STOCK,run_action
        if not local_path(STOCK,action.get('path',action.get('prefix'))).is_relative_to(STOCK):
            raise ValueError('stock scope required')
        return run_action(Path(record),'unused',action,0)
    return dict(status='returned',disposition=action['disposition'])
