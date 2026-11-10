"""Insertion-only stock diagnostic bundle; no final or optimization code."""

import hashlib
import json
from pathlib import Path
import shutil

from harness.build_engine import SKIP_DIRS,tree_sha
from harness.candidate import check_tree
from harness.stock_step_build import STOCK_SHA,WORKER,PROCESSOR,RUNTIME,instrument_sources


CEILING_RUNTIME='python/sglang/srt/speculative/specpilot_ceiling_observer.py'


def instrument_worker(worker):
    option='SPECPILOT_CEILING_TRACE_DIR'
    if option in worker:
        raise ValueError('worker already instrumented')
    anchor='        tokens, q_rows = self.selector.sample_path(\n'
    if worker.count(anchor)!=2:
        raise ValueError('sampler anchors changed')
    capture=(f'        if __import__("os").environ.get("{option}"):\n'
             '            if not hasattr(self, "_phase0_lattices"):\n'
             '                self._phase0_lattices = {}\n'
             '            self._phase0_lattices[bs] = (candidate_ids.clone(), scores.clone())\n')
    worker=worker.replace(anchor,capture+anchor,1)
    eager='        return tokens.view(bs, num_pred)\n'
    if worker.count(eager)!=1:
        raise ValueError('eager selector anchor changed')
    worker=worker.replace(eager,f'        if __import__("os").environ.get("{option}"):\n'
        '            self._phase0_lattice = (candidate_ids, scores)\n'+eager)
    anchor='        draft_tokens = self._draft_block_tokens_buf[:bs]\n'
    if worker.count(anchor)!=1:
        raise ValueError('draft completion anchor changed')
    worker=worker.replace(anchor,f'        if __import__("os").environ.get("{option}") and self._draft_sampler is not None and draft_out.can_run_graph:\n'
        '            self._phase0_lattice = self._draft_sampler._phase0_lattices[bs]\n'+anchor)
    anchor='        return GenerationBatchResult(\n            logits_output=logits_output,\n            next_token_ids=out_tokens.reshape(-1),'
    if worker.count(anchor)!=1:
        raise ValueError('verify completion anchor changed')
    worker=worker.replace(anchor,f'        if __import__("os").environ.get("{option}"):\n'
        '            from sglang.srt.speculative.specpilot_ceiling_observer import observe_lattice\n'
        '            observe_lattice(batch, candidates, target_predict, accept_len, commit_lens, bonus, out_tokens, *self._phase0_lattice)\n\n'+anchor)
    compile(worker,WORKER,'exec')
    return worker


def build(stock,directory):
    stock,directory=Path(stock).resolve(),Path(directory).absolute()
    check_tree(stock,STOCK_SHA)
    if directory.exists() or directory.is_relative_to(stock):
        raise ValueError('new independent bundle required')
    original=(stock/WORKER).read_text()
    worker=instrument_worker(original)
    _,processor=instrument_sources(original,(stock/PROCESSOR).read_text())
    directory.mkdir(mode=0o700,parents=True)
    engine=directory/'engine'
    shutil.copytree(stock,engine,symlinks=True,ignore=shutil.ignore_patterns(*SKIP_DIRS,'*.pyc','*.pyo'))
    (engine/WORKER).write_text(worker)
    (engine/PROCESSOR).write_text(processor)
    for source,target in (('stock_step_runtime.py',RUNTIME),('ceiling_runtime.py',CEILING_RUNTIME)):
        shutil.copyfile(Path(__file__).with_name(source),engine/target)
    checksum=tree_sha(engine)
    (engine/'TREE_SHA').write_text(checksum+'\n')
    report=dict(schema='ceiling-observer-build-v1',stock=str(stock),stock_tree_sha=STOCK_SHA,
        observer_tree_sha=checksum,option='SPECPILOT_CEILING_TRACE_DIR',default_enabled=False,
        files={name:hashlib.sha256((engine/name).read_bytes()).hexdigest() for name in (WORKER,PROCESSOR,RUNTIME,CEILING_RUNTIME)})
    (directory/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    check_bundle(directory)
    return report


def check_bundle(directory):
    directory=Path(directory)
    report=json.loads((directory/'build.json').read_text())
    stock=Path(report['stock'])
    check_tree(stock,STOCK_SHA)
    check_tree(directory/'engine',report['observer_tree_sha'])
    _,processor=instrument_sources((stock/WORKER).read_text(),(stock/PROCESSOR).read_text())
    expected={WORKER:instrument_worker((stock/WORKER).read_text()).encode(),PROCESSOR:processor.encode(),
        RUNTIME:Path(__file__).with_name('stock_step_runtime.py').read_bytes(),
        CEILING_RUNTIME:Path(__file__).with_name('ceiling_runtime.py').read_bytes()}
    if (report['stock_tree_sha']!=STOCK_SHA or report['default_enabled'] is not False or
            any((directory/'engine'/name).read_bytes()!=content or
                hashlib.sha256(content).hexdigest()!=report['files'][name] for name,content in expected.items())):
        raise ValueError('bundle differs from trusted insertion-only observer')
    return report
