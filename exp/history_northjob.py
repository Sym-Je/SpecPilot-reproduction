import copy
import importlib
import os
import sys


def with_model_mount(template, deadline=1560):
    if type(deadline) is not int or deadline not in (600,1200,1560):
        raise ValueError('unsupported bounded pod deadline')
    result=copy.deepcopy(template)
    tasks=result['spec']['tasks']
    if len(tasks)!=1 or tasks[0]['replicas']!=1:
        raise ValueError('history collection requires one node')
    pod=tasks[0]['template']['spec']
    containers=pod['containers']
    if len(containers)!=1 or str(containers[0]['resources']['limits'].get('nvidia.com/gpu'))!='1':
        raise ValueError('history collection requires exactly one H100')
    mounts=containers[0].setdefault('volumeMounts',[])
    volumes=pod.setdefault('volumes',[])
    if any(row['mountPath']=='/gpfs/models' for row in mounts) or any(row['name']=='specpilot-models' for row in volumes):
        raise ValueError('model mount already exists')
    volumes.append(dict(name='specpilot-models',persistentVolumeClaim=dict(claimName='share-readonly',readOnly=True)))
    mounts.append(dict(name='specpilot-models',mountPath='/gpfs/models',subPath='models',readOnly=True))
    pod['activeDeadlineSeconds']=deadline
    result['spec']['maxRetry']=0
    result['spec']['policies']=[dict(events=['PodEvicted','PodFailed'],action='AbortJob')]
    return result


def main():
    if sys.argv[1:2]!=['create']:
        raise SystemExit('use only for an explicitly authorized history collection create')
    launcher=importlib.import_module('northmirror.launcher.create_job')
    cli=importlib.import_module('northmirror.launcher.northjob')
    original=launcher.build_job_yaml
    deadline=int(os.environ.get('SP_NORTHJOB_DEADLINE_SECONDS','1560'))
    def build(*arguments,**options):
        return with_model_mount(original(*arguments,**options),deadline)
    launcher.build_job_yaml=build
    try:
        return cli.main()
    finally:
        launcher.build_job_yaml=original


if __name__=='__main__':
    main()
