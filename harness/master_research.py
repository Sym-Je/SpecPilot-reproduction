"""Broker-owned source, public-knowledge and measured-baseline tools."""

import hashlib
import json
from functools import partial
from pathlib import Path

from harness.research_protocol import ResearchBroker
from harness.skill_broker import SkillAccess
from harness.skill_diagnostics import write_json


class MasterAccess(SkillAccess):
    def __init__(self, *arguments, baseline_loader, stock, **options):
        super().__init__(*arguments, **options)
        self.baseline_loader = baseline_loader
        self.stock = Path(stock).resolve()

    def factory(self):
        return partial(ResearchBroker, dispatcher=self.dispatch, receipt_labels=True)

    def dispatch(self, work, action, record):
        if not isinstance(action, dict):
            raise ValueError('structured research action required')
        kind = action.get('kind')
        if kind in ('help', 'list_skills'):
            answer = super().dispatch(work, action, record)
            answer.update(master_actions=dict(
                search_stock=dict(kind='search_stock', query='literal text', prefix='python/sglang/', offset=0),
                search_public=dict(kind='search_public', query='public technical question'),
                read_public=dict(kind='read_public', url='https://allowed-public-domain/path'),
                get_baseline_stats=dict(kind='get_baseline_stats'),
                estimate_scenario=dict(kind='estimate_scenario', tau_ratio=1.0, step_cost_ratio=None,
                    extra_step_cost_ratio=None, assumptions=['Explicit conditional model, not a measured gain'])),
                arbitrary_network=False, gpu_submission_allowed=False,
                external_text_is_untrusted_data=True)
            return answer
        if kind in ('search_public', 'read_public'):
            from harness.research_knowledge import dispatch_public, trusted_proxy_transport
            field = 'query' if kind == 'search_public' else 'url'
            if set(action) != {'kind', field}:
                raise ValueError('public retrieval accepts only its query or URL')
            return dispatch_public(action, record, transport=trusted_proxy_transport())
        if kind == 'get_baseline_stats':
            if set(action) != {'kind'}:
                raise ValueError('baseline tool accepts no paths or configuration')
            answer = dict(status='completed', kind=kind, statistics=self.baseline_loader(), formal_ceiling=None,
                scope='SHA-bound public stock counters; profiled timings are not normal serving performance')
        elif kind == 'estimate_scenario':
            from harness.acceptance_evidence import estimate_conditional
            fields = {'kind', 'tau_ratio', 'step_cost_ratio', 'extra_step_cost_ratio', 'assumptions'}
            if set(action) != fields:
                raise ValueError('explicit tau, full step cost, extra cost and assumptions are required')
            scenario = estimate_conditional(**{key:value for key,value in action.items() if key != 'kind'})
            answer = dict(status='completed', kind=kind, scenario=scenario, formal_ceiling=None)
        elif kind == 'search_stock':
            answer = self.search_stock(action)
        else:
            return super().dispatch(work, action, record)
        target = Path(record)
        target.mkdir(parents=True, exist_ok=False)
        write_json(target / 'result.json', answer)
        return answer

    def search_stock(self, action):
        if set(action) != {'kind', 'query', 'prefix', 'offset'}:
            raise ValueError('literal stock query, prefix and offset required')
        query, prefix, offset = action['query'], action['prefix'], action['offset']
        if (not isinstance(query, str) or not 1 <= len(query) <= 240 or '\n' in query or
                not isinstance(prefix, str) or not prefix.startswith('python/sglang/') or
                any(part in ('', '.', '..') for part in prefix.rstrip('/').split('/')) or
                type(offset) is not int or offset < 0):
            raise ValueError('bounded stock search required')
        selected = self.stock / prefix
        if selected.is_symlink() or not selected.resolve().is_relative_to(self.stock) or not selected.is_dir():
            raise ValueError('authorized nonsymlink stock directory required')
        matches = []
        files = sorted(selected.rglob('*.py'))
        if len(files) > 5000:
            raise ValueError('source query directory too broad')
        scanned = 0
        for path in files:
            if path.is_symlink() or not path.resolve().is_relative_to(self.stock):
                continue
            raw = path.read_bytes()
            scanned += len(raw)
            if len(raw) > 2097152 or scanned > 33554432:
                raise ValueError('source search byte budget exceeded; narrow prefix')
            digest = hashlib.sha256(raw).hexdigest()
            for number, line in enumerate(raw.decode().splitlines(), 1):
                if query in line:
                    matches.append(dict(path=path.relative_to(self.stock).as_posix(), line=number,
                        text=line[:800], source_sha256=digest))
        if offset > len(matches):
            raise ValueError('search offset beyond result count')
        end = min(len(matches), offset + 24)
        return dict(status='completed', kind='search_stock', query=query, prefix=prefix,
            matches=matches[offset:end], total_matches=len(matches), offset=offset,
            next_offset=end if end < len(matches) else None,
            scope='Static authorized source matches, not runtime-path certification')
