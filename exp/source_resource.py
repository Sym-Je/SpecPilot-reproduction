"""Source-option adapter for the existing bounded NorthJob broker."""

import json
from pathlib import Path
import shlex

from exp.engine_resource import command as engine_command, execute as engine_execute
from exp.gpu_autonomy import ROOT
from harness.engine_research import Budget
from harness.source_candidate import file_sha

LIMITS = dict(gpu_seconds=57600, wall_seconds=43200, concurrent_gpus=2)


def stage_budget(path):
    return Budget(path, limits=LIMITS)


def command(request, source, output, name, deadline):
    bootstrap = ROOT / 'exp/source_remote.sh'
    cli = engine_command(request, source, output, name, deadline)
    cli[-1] = shlex.join(['env', 'SP_SOURCE_BOOTSTRAP_SHA=' + file_sha(bootstrap),
        'SP_SOURCE_ARCHIVE_SHA=' + file_sha(source), 'SP_SOURCE_REQUEST_SHA=' + file_sha(request),
        'bash', str(bootstrap), str(request), str(source), str(output), str(deadline)])
    return cli


def feedback(output, record):
    if record['mode'] == 'source-controller':
        from controller.dev_campaign import validate_campaign
        from harness.engine_research import json_record
        value = json.loads((output / 'result.json').read_text())
        verdict = json_record(validate_campaign(output))
        if value['controller_verdict'] != verdict or value['controller_accepted'] != verdict['joint_acceptance_passed']:
            raise ValueError('source gate independent controller replay differs')
        return value
    from exp.source_research import audit
    value = audit(output)
    if value != json.loads((output / 'result.json').read_text()):
        raise ValueError('source diagnostic independent replay differs')
    value['metric_definition'] = dict(measured_quantity='candidate_tokens_per_second / stock_tokens_per_second',
        improvement_direction='higher_is_better', not_a_latency_ratio=True,
        warning='public dev diagnostic only; natural EOS output lengths may differ')
    if record.get('comparison_base_sha256'):
        value['metric_definition'].update(measured_quantity='candidate_tokens_per_second / comparison_stack_tokens_per_second',
            comparison_base_sha256=record['comparison_base_sha256'], correctness_reference='canonical stock, not comparison stack')
    return value


def execute(directory, source, budget, *, resume_only=False):
    record = json.loads((Path(directory) / 'request.json').read_text())
    deadline = {'source-preflight': 1200, 'source-research': 3600, 'source-controller': 7200}[record['mode']]
    return engine_execute(directory, source, budget, resume_only=resume_only,
        command_factory=command, feedback_loader=feedback, deadline=deadline)
