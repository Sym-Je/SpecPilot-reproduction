"""Existing public CLI template adapter, bounded to this two-H100 research unit."""

import importlib
import os
import sys

from exp.history_northjob import with_model_mount


def bounded_template(template, deadline):
    if type(deadline) is not int or not 600 <= deadline <= 7200:
        raise ValueError('research deadline outside the verified range')
    tasks = template['spec']['tasks']
    if len(tasks) != 1 or tasks[0]['replicas'] != 1:
        raise ValueError('one research pod required')
    container = tasks[0]['template']['spec']['containers'][0]
    if str(container['resources']['limits'].get('nvidia.com/gpu')) != '2':
        raise ValueError('this execution unit requires exactly two H100')
    import copy
    result = copy.deepcopy(template)
    result['spec']['tasks'][0]['template']['spec']['containers'][0]['resources']['limits']['nvidia.com/gpu'] = '1'
    result = with_model_mount(result, 600)
    result['spec']['tasks'][0]['template']['spec']['containers'][0]['resources']['limits']['nvidia.com/gpu'] = container['resources']['limits']['nvidia.com/gpu']
    result['spec']['tasks'][0]['template']['spec']['activeDeadlineSeconds'] = deadline
    return result


def main():
    if sys.argv[1:2] != ['create']:
        raise SystemExit('only authorized research create is supported')
    launcher = importlib.import_module('northmirror.launcher.create_job')
    cli = importlib.import_module('northmirror.launcher.northjob')
    original = launcher.build_job_yaml
    def build(*arguments, **options):
        return bounded_template(original(*arguments, **options), int(os.environ['SP_ENGINE_DEADLINE']))
    launcher.build_job_yaml = build
    try:
        return cli.main()
    finally:
        launcher.build_job_yaml = original


if __name__ == '__main__':
    main()
