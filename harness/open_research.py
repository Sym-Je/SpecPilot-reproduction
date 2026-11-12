"""Broad stock research access inside existing immutable-data and execution boundaries."""

import hashlib
from pathlib import Path

from harness.experiment_executor import execute_python,local_path
from harness.master_research import MasterAccess
from harness.skill_diagnostics import write_json
from harness.source_candidate import file_sha


TEXT_SUFFIXES=frozenset(('.py','.cu','.cuh','.cpp','.cc','.c','.h','.hpp','.json','.toml','.yaml','.yml','.md','.txt','.cmake','.sh'))
PRIVATE_PARTS=frozenset(('.git','.ssh','.aws','.config','sealed'))
CPU_LIMITS=dict(wall_seconds=60,cpu_seconds=30,memory_bytes=2*1024**3)


def record_authored_text(action,answer,contents):
    name=action['path'];kind=action['kind']
    if kind=='write_file':content=action['content']
    elif kind=='append_file':
        if name not in contents or hashlib.sha256(contents[name].encode()).hexdigest()!=action['expected_sha256']:
            raise ValueError('native append has no matching prior authored content')
        content=contents[name]+action['content']
    else:raise ValueError('native source authorship requires a write or bound append')
    digest=hashlib.sha256(content.encode()).hexdigest()
    if answer.get('sha256')!=digest:raise ValueError('native source write content differs from its receipt')
    contents[name]=content
    return digest


class OpenAccess(MasterAccess):
    def stock_path(self,name):
        path=local_path(self.stock,name)
        if any(part in PRIVATE_PARTS or part.startswith('.') for part in Path(name).parts):
            raise ValueError('hidden or protected stock content is not exposed')
        return path

    def stock_files(self,prefix):
        directory=self.stock if prefix=='' else self.stock_path(prefix)
        if directory.is_file() and directory.suffix in TEXT_SUFFIXES:return [directory]
        if not directory.is_dir():raise ValueError('stock source directory or text file required')
        files=[]
        for path in sorted(directory.rglob('*')):
            name=path.relative_to(self.stock).as_posix()
            if (not path.is_file() or path.is_symlink() or path.suffix not in TEXT_SUFFIXES or
                    any(part in PRIVATE_PARTS or part.startswith('.') for part in Path(name).parts)):
                continue
            try:self.stock_path(name)
            except ValueError:continue
            files.append(path)
            if len(files)>100000:raise ValueError('source inventory too large; narrow the prefix')
        return files

    def dispatch(self,work,action,record):
        if not isinstance(action,dict):raise ValueError('structured research action required')
        kind=action.get('kind')
        if kind=='help':
            answer=super().dispatch(work,action,record)
            answer.update(research_access='broad-authorized-stock-v1',source_suffixes=sorted(TEXT_SUFFIXES),
                cpu_execution_limits=CPU_LIMITS,source_option_protocols=['source-option-v1','source-option-v2'],
                source_option_v2=dict(max_edits=128,new_runtime_and_kernel_sources=True,default_enabled=False,
                    compile_and_runtime_success_not_guaranteed=True))
            answer['actions']['append_file']=dict(kind='append_file',path='scratch/candidate.cu',
                expected_sha256='SHA of existing file',content='next source chunk')
            return answer
        if kind in ('read_stock','list_stock','search_stock'):
            answer=self.source_action(action)
        elif kind in ('write_file','append_file','run_python'):
            name=action.get('path');path=local_path(work,name)
            if Path(name).parts[0]!='scratch':raise ValueError('only private research scratch can be written or executed')
            if kind=='run_python':
                if set(action)!={'kind','path'}:raise ValueError('run_python accepts only its source path')
                answer=execute_python(work,name,record,limits=CPU_LIMITS)
                answer['workspace_file_sha256']={entry.relative_to(work).as_posix():file_sha(entry)
                    for entry in (Path(work)/'scratch').rglob('*') if entry.is_file() and not entry.is_symlink()}
                answer['workspace_code_sha256']={key:value for key,value in answer['workspace_file_sha256'].items() if key.endswith('.py')}
                return answer
            fields={'kind','path','content'}|({'expected_sha256'} if kind=='append_file' else set())
            content=action.get('content')
            if set(action)!=fields or not isinstance(content,str) or len(content.encode())>32768:
                raise ValueError('bounded research source text required')
            if kind=='append_file' and (not path.is_file() or file_sha(path)!=action['expected_sha256']):
                raise ValueError('append must bind the current source SHA; never replay an uncertain write')
            payload=(path.read_bytes() if kind=='append_file' else b'')+content.encode()
            if len(payload)>4194304:raise ValueError('single research source exceeds 4 MiB')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
            answer=dict(status='completed',sha256=file_sha(path),bytes=len(payload))
        else:
            return super().dispatch(work,action,record)
        target=Path(record);target.mkdir(parents=True,exist_ok=False)
        write_json(target/'result.json',answer)
        return answer

    def source_action(self,action):
        kind=action['kind']
        fields={'kind','path','offset'} if kind=='read_stock' else {'kind','prefix','offset'}
        if kind=='search_stock':fields.add('query')
        if set(action)!=fields or type(action['offset']) is not int or action['offset']<0:
            raise ValueError('source action needs exact fields and a nonnegative offset')
        offset=action['offset']
        if kind=='read_stock':
            path=self.stock_path(action['path'])
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES or path.stat().st_size>4194304:
                raise ValueError('bounded regular stock source text required')
            content=path.read_text();end=min(len(content),offset+16000)
            if offset>len(content):raise ValueError('source offset exceeds file length')
            return dict(status='completed',content=content[offset:end],sha256=file_sha(path),offset=offset,
                total_chars=len(content),next_offset=end if end<len(content) else None)
        files=self.stock_files(action['prefix'])
        if kind=='list_stock':
            rows=[path.relative_to(self.stock).as_posix() for path in files];page=64
        else:
            query=action['query']
            if not isinstance(query,str) or not 1<=len(query)<=240 or '\n' in query:raise ValueError('bounded literal source query required')
            rows=[];scanned=0;page=24
            for path in files:
                if path.stat().st_size>4194304:continue
                raw=path.read_bytes();scanned+=len(raw)
                if scanned>134217728:raise ValueError('source search too large; narrow the prefix')
                for number,line in enumerate(raw.decode().splitlines(),1):
                    if query in line:rows.append(dict(path=path.relative_to(self.stock).as_posix(),line=number,
                        text=line[:800],source_sha256=hashlib.sha256(raw).hexdigest()))
        if offset>len(rows):raise ValueError('source result offset exceeds inventory')
        end=min(len(rows),offset+page)
        return dict(status='completed',kind=kind,**({'files':rows[offset:end]} if kind=='list_stock' else
            {'matches':rows[offset:end],'total_matches':len(rows)}),total=len(rows),offset=offset,
            next_offset=end if end<len(rows) else None,scope='Authorized stock source, not loaded binary or runtime-path certification')
