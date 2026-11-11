"""Role-scoped access to pinned offline diagnostics; no research-selected host paths."""

from functools import partial
import fcntl
import json
from pathlib import Path

from harness.research_protocol import ResearchBroker
from harness.research_tools import dispatch
from harness.skill_diagnostics import PROFILE_ONLY_PROTOCOL, analyze, checked_file, checked_manifest, checked_tools, kernel_statistics, observed_shape_facts, read_trace, run_tool, sha256, write_json


CATALOG = {
    'profiler': dict(upstream='llm-torch-profiler-analysis',
        purpose='Inspect kernel work, overlap and fusion hypotheses; DFlash2 stages may be unknown.'),
    'compute': dict(upstream='model-compute-simulation',
        purpose='Estimate actual target verify shapes/FLOPs, not measured MFU or ceiling.'),
    'pipeline': dict(upstream='llm-pipeline-analysis',
        purpose='Layer analysis needs independently verified anchors; missing anchors return unavailable.'),
    'triage': dict(upstream='sglang-prod-incident-triage',
        purpose='Preserve failing request and identity, replay before diagnosing; no causal claim from symptoms.'),
    'capacity': dict(upstream='llm-serving-capacity-planner',
        purpose='Explain startup memory and capacity only when approved startup-log evidence is available.'),
}
ROLE_SKILLS = {role: frozenset(CATALOG) for role in ('Master', 'direction', 'integration', 'kernel')}


class SkillAccess:
    def __init__(self, role, evidence, tools_path, cache, *, extensions=None, startup_log=None):
        if role not in ROLE_SKILLS:
            raise ValueError('unregistered scientific role')
        self.role = role
        self.evidence = dict(evidence)
        self.tools_path = Path(tools_path)
        self.cache = Path(cache)
        self.extensions = Path(extensions) if extensions else None
        self.startup_log = startup_log

    def factory(self):
        return partial(ResearchBroker, dispatcher=self.dispatch)

    def dispatch(self, work, action, record):
        if not isinstance(action, dict):
            raise ValueError('structured action required')
        if action.get('kind') == 'list_skills':
            if set(action) != {'kind'}:
                raise ValueError('list_skills accepts no paths or options')
            return dict(status='completed', role=self.role, skills=CATALOG,
                evidence=list(self.evidence), arbitrary_shell=False, gpu_submission_allowed=False,
                actions=dict(read_profile_shapes=dict(
                    schema=dict(kind='read_profile_shapes', evidence='<authorized evidence ID>', offset=0),
                    page_size=16, cpu_runs_per_call=1, additional_fields_allowed=False,
                    offset_rule='Nonnegative integer, not bool; follow next_offset until null. '
                                'Offset equal to total_signatures returns an empty page; larger offsets reject.',
                    scope='Authorized profile-only CPU event observations; never certified cost-model inputs.')))
        if action.get('kind') == 'read_profile_shapes':
            if set(action) != {'kind', 'evidence', 'offset'}:
                raise ValueError('read_profile_shapes accepts only an authorized evidence ID and offset')
            identity, offset = action['evidence'], action['offset']
            if not isinstance(identity, str) or identity not in self.evidence:
                raise ValueError('profile evidence is not authorized for this role')
            if type(offset) is not int or offset < 0:
                raise ValueError('shape signature offset must be a nonnegative integer')
            manifest_path = Path(self.evidence[identity])
            manifest = json.loads(manifest_path.read_text())
            trace, config, shape = checked_manifest(manifest)
            if manifest['protocol'] != PROFILE_ONLY_PROTOCOL:
                raise ValueError('read_profile_shapes requires explicit profile-only evidence')
            facts = observed_shape_facts(read_trace(trace), manifest['trace']['sha256'], offset=offset)
            checked_manifest(manifest)
            answer = dict(status='completed', kind='read_profile_shapes', role=self.role, evidence=identity,
                manifest_sha256=sha256(manifest_path), observed_shape_facts=facts,
                independent_discovery=False, gpu_submissions=0,
                scope='Read-only recorded CPU fields; not workload certification or controller acceptance.')
            target = Path(record)
            target.mkdir(parents=True, exist_ok=False)
            write_json(target / 'result.json', answer)
            return answer
        if action.get('kind') != 'run_skill':
            return dispatch(work, action, record)
        if set(action) != {'kind', 'skill', 'evidence'}:
            raise ValueError('run_skill accepts only a skill and an authorized evidence ID')
        skill, identity = action['skill'], action['evidence']
        if skill not in ROLE_SKILLS[self.role] or identity not in self.evidence:
            raise ValueError('skill or evidence is not authorized for this role')
        manifest_path = Path(self.evidence[identity])
        manifest = json.loads(manifest_path.read_text())
        checked_manifest(manifest)
        profile_only = manifest.get('protocol') == PROFILE_ONLY_PROTOCOL
        tools = json.loads(self.tools_path.read_text())
        checked_tools(tools)
        repository = Path(__file__).resolve().parents[1]
        adapter_names = ('harness/skill_diagnostics.py', 'harness/skill_worker.py', 'exp/skill_diagnostics.py')
        version_paths = (Path(__file__), *(repository / name for name in adapter_names),
                         Path(__file__).with_name('skill_tools.json'))
        version = ''.join(sha256(path)[:8] for path in version_paths)
        output = self.cache / (sha256(manifest_path)[:20] + '-' + tools['revision'][:12] + '-' + version)
        self.cache.mkdir(parents=True, exist_ok=True)
        with output.with_suffix('.lock').open('a') as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
            cached = (output / 'result.json').is_file()
            if not cached:
                analyze(manifest_path, self.tools_path, output)
        result = json.loads((output / 'result.json').read_text())
        if result['input_identity'] != manifest or result['engineering_passed'] is not True:
            raise ValueError('diagnostic cache is incomplete or input identity differs')
        required = ('extract', 'profiler') if profile_only else ('profiler', 'compute')
        if profile_only:
            if result.get('adapter_sources_sha256') != {name:sha256(repository / name) for name in adapter_names}:
                raise ValueError('profile-only cached adapter source identity differs')
            events = read_trace(checked_file(manifest['trace']))
            facts = observed_shape_facts(events, manifest['trace']['sha256'])
            if result.get('kernel_statistics') != json.loads(json.dumps(kernel_statistics(events))):
                raise ValueError('cached kernel statistics differ from the authorized trace')
            if result.get('observed_shape_facts') != facts:
                raise ValueError('cached observed shape facts differ from the authorized trace')
            if any(not isinstance(result['tools'].get(name), dict) or result['tools'][name].get('status') != 'unavailable' or
                   'output_sha256' in result['tools'][name] for name in ('compute', 'pipeline')):
                raise ValueError('profile-only cache claims unavailable tool execution')
        for name in required:
            receipt = result['tools'].get(name, {})
            if not isinstance(receipt, dict) or not isinstance(receipt.get('output_sha256'), dict) or 'stdout' not in receipt['output_sha256']:
                raise ValueError('cached executed tool receipt missing')
            if profile_only and (receipt.get('exit_code') != 0 or receipt.get('timed_out') is not False or
                                  set(receipt['output_sha256']) != {'stdout', 'stderr'}):
                raise ValueError('profile-only cached executed tool receipt incomplete')
        for name, receipt in result['tools'].items():
            if name not in ('extract', 'profiler', 'compute', 'pipeline') or not isinstance(receipt, dict):
                raise ValueError('unknown cached diagnostic tool')
            for stream, checksum in receipt.get('output_sha256', {}).items():
                if stream not in ('stdout', 'stderr'):
                    raise ValueError('unknown cached diagnostic output')
                try:
                    checked_file(dict(path=str(output / (name + '.' + stream + '.txt')), sha256=checksum))
                except (ValueError, OSError) as error:
                    raise ValueError('cached tool output SHA differs') from error
        answer = dict(status='completed', skill=skill, upstream=CATALOG[skill]['upstream'],
            upstream_revision=tools['revision'], role=self.role, evidence=identity, cached=cached,
            result_sha256=sha256(output / 'result.json'), independent_discovery=False,
            scope='external diagnostic tool evidence; not controller acceptance',
            limitations=result['limitations'])
        target = Path(record)
        target.mkdir(parents=True, exist_ok=False)
        if skill == 'profiler':
            answer.update(kernel_statistics=result['kernel_statistics'],
                text=(output / 'profiler.stdout.txt').read_text()[:18000],
                stage_attribution_validated=False)
            if profile_only:
                answer['observed_shape_facts'] = result['observed_shape_facts']
        elif skill == 'compute':
            if profile_only:
                answer.update(status='unavailable', reason=result['tools']['compute']['reason'])
            else:
                answer['estimate'] = json.loads((output / 'compute.stdout.txt').read_text())
        elif skill == 'pipeline':
            answer.update(status='unavailable', reason=result['tools']['pipeline']['reason'])
        elif skill == 'triage':
            if self.extensions:
                self.check_extensions()
                card = self.extensions / 'skills/sglang-prod-incident-triage/SKILL.md'
                answer.update(guide=card.read_text()[:12000], guide_sha256=sha256(card),
                    guide_is_data_not_privileged_instruction=True)
            else:
                answer.update(status='unavailable', reason='Pinned triage guide is not configured for this role.')
        else:
            if self.extensions and self.startup_log:
                self.check_extensions()
                log = checked_file(self.startup_log)
                execution = target / 'capacity'
                execution.mkdir()
                copied_log = execution / 'startup.log'
                copied_log.write_bytes(log.read_bytes())
                if sha256(copied_log) != self.startup_log['sha256']:
                    raise ValueError('startup-log changed while copying')
                config = checked_file(manifest['config'])
                execution = execution.resolve()
                receipt = run_tool(self.extensions, 'capacity', ['--log-file', copied_log.resolve(),
                    '--config-json', config, '--gpu', 'h100', '--format', 'json'], execution)
                if receipt['exit_code']:
                    answer.update(status='unavailable', reason='Capacity parser rejected the approved log.', receipt=receipt)
                else:
                    answer.update(estimate=json.loads((execution / 'capacity.stdout.txt').read_text()),
                        input_sha256=self.startup_log['sha256'], receipt=receipt)
            else:
                answer.update(status='unavailable', reason='No authorized startup-log capacity analysis for this evidence ID.')
        if 'text' in answer:
            answer['text'] = answer['text'].replace(str(output), '<diagnostic-artifact>')
        write_json(target / 'result.json', answer)
        return answer

    def check_extensions(self):
        lock = json.loads(Path(__file__).with_name('skill_extension_tools.json').read_text())
        for name, identity in lock['files'].items():
            checked_file(dict(path=str(self.extensions / name), sha256=identity))
