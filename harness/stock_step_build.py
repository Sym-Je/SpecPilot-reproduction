"""Build a separate default-off stock observer; original stock stays immutable."""

import hashlib
import json
from pathlib import Path
import shutil

from harness.build_engine import SKIP_DIRS,tree_sha
from harness.candidate import check_tree


STOCK_SHA='e5472c4fbb6e6bf57e2736f898f5e0827b9448cdd34f332d8fb2df93f652e3ff'
WORKER='python/sglang/srt/speculative/dflash_worker_v2.py'
PROCESSOR='python/sglang/srt/managers/scheduler_components/batch_result_processor.py'
RUNTIME='python/sglang/srt/speculative/specpilot_step_observer.py'


def instrument_sources(worker,processor):
    target='        return GenerationBatchResult(\n            logits_output=logits_output,\n            next_token_ids=out_tokens.reshape(-1),'
    hook=('        if __import__("os").environ.get("SPECPILOT_STEP_TRACE_DIR"):\n'
          '            from sglang.srt.speculative.specpilot_step_observer import observe_verify\n'
          '            observe_verify(batch, candidates, target_predict, accept_len, commit_lens, bonus, out_tokens)\n\n')
    if worker.count(target)!=1:
        raise ValueError('stock verify observation anchor changed')
    worker=worker.replace(target,hook+target)
    for phase,target,indent in (
            ('prefill','                        req.update_finish_state()\n                    # A mixed spec tail',24),
            ('decode','            req.update_finish_state(new_accept_len)\n\n            if sampling_mask_finish_reason',12)):
        first,rest=target.split('\n',1)
        space=' '*indent
        hook=(f'{space}if __import__("os").environ.get("SPECPILOT_STEP_TRACE_DIR"):\n'
              f'{space}    from sglang.srt.speculative.specpilot_step_observer import observe_commit\n'
              f'{space}    observe_commit(req, "{phase}")\n')
        if processor.count(target)!=1:
            raise ValueError('stock scheduler observation anchor changed')
        processor=processor.replace(target,first+'\n'+hook+rest)
    compile(worker,WORKER,'exec')
    compile(processor,PROCESSOR,'exec')
    return worker,processor


def build(stock,directory):
    stock,directory=Path(stock).absolute(),Path(directory).absolute()
    check_tree(stock,STOCK_SHA)
    if directory.exists() or directory.is_relative_to(stock):
        raise ValueError('observer requires a new output outside stock')
    worker,processor=instrument_sources((stock/WORKER).read_text(),(stock/PROCESSOR).read_text())
    directory.mkdir(mode=0o700,parents=True)
    shutil.copytree(stock,directory/'engine',symlinks=True,
                    ignore=shutil.ignore_patterns(*SKIP_DIRS,'*.pyc','*.pyo'))
    engine=directory/'engine'
    (engine/WORKER).write_text(worker)
    (engine/PROCESSOR).write_text(processor)
    runtime=Path(__file__).with_name('stock_step_runtime.py')
    shutil.copyfile(runtime,engine/RUNTIME)
    checksum=tree_sha(engine)
    (engine/'TREE_SHA').write_text(checksum+'\n')
    check_tree(engine,checksum)
    check_tree(stock,STOCK_SHA)
    report=dict(schema='stock-observer-build-v1',stock=str(stock),stock_tree_sha=STOCK_SHA,
        observer_tree_sha=checksum,option='SPECPILOT_STEP_TRACE_DIR',stock_default=None,
        modified_files=[WORKER,PROCESSOR],added_files=[RUNTIME],
        runtime_sha256=hashlib.sha256(runtime.read_bytes()).hexdigest())
    (directory/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def check_bundle(directory):
    directory=Path(directory).absolute()
    report=json.loads((directory/'build.json').read_text())
    if report['schema']!='stock-observer-build-v1' or report['stock_tree_sha']!=STOCK_SHA:
        raise ValueError('unexpected stock observer provenance')
    check_tree(report['stock'],STOCK_SHA)
    check_tree(directory/'engine',report['observer_tree_sha'])
    worker,processor=instrument_sources((Path(report['stock'])/WORKER).read_text(),(Path(report['stock'])/PROCESSOR).read_text())
    runtime=Path(__file__).with_name('stock_step_runtime.py').read_bytes()
    if ((directory/'engine'/WORKER).read_text()!=worker or (directory/'engine'/PROCESSOR).read_text()!=processor or
            (directory/'engine'/RUNTIME).read_bytes()!=runtime or hashlib.sha256(runtime).hexdigest()!=report['runtime_sha256']):
        raise ValueError('observer artifact differs from the declared insertion-only hooks')
    return report
