"""Run agent code only after actual file, network and process denial probes."""

import ctypes
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.landlock import Policy, READ, READ_FILE, WRITE, WRITE_FILE
from harness.research_boundary import syscall_boundary


def deny_processes():
    library = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    class Comparison(ctypes.Structure):
        _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_uint), ('first', ctypes.c_uint64), ('second', ctypes.c_uint64)]
    library.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Comparison)]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x7fff0000)
    if not context:
        raise RuntimeError('process filter unavailable')
    try:
        for name in ('execve', 'execveat', 'fork', 'vfork', 'clone3', 'kill', 'tkill', 'tgkill', 'pidfd_send_signal'):
            number = library.seccomp_syscall_resolve_name(name.encode())
            error = 38 if name == 'clone3' else 1
            if number >= 0 and library.seccomp_rule_add(context, 0x00050000 | error, number, 0):
                raise RuntimeError('process denial failed')
        number = library.seccomp_syscall_resolve_name(b'clone')
        comparison = Comparison(0, 7, 0x10000, 0)
        if number >= 0 and library.seccomp_rule_add_array(context, 0x00050001, number, 1, ctypes.byref(comparison)):
            raise RuntimeError('non-thread clone denial failed')
        if library.seccomp_load(context):
            raise RuntimeError('process filter load failed')
    finally:
        library.seccomp_release(context)


def restrict(work, stock, models, gpu):
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    policy = Policy()
    directories = [sys.prefix, '/usr/lib', '/lib', '/lib64', '/usr/share/zoneinfo', str(work)]
    if stock:
        directories.append(stock)
    directories.extend(models)
    if gpu:
        directories.extend(['/proc/self', '/proc/driver/nvidia', '/sys/devices',
            '/gpfs/users/jixinpeng/specpilot_data/shared/cuda-compat/usr/local/cuda-13.0/compat'])
    for name in directories:
        if Path(name).exists():
            policy.add(name, READ)
    for name in ('/dev/null', '/dev/urandom', '/etc/ld.so.cache', '/etc/localtime', '/proc/cpuinfo', '/proc/meminfo'):
        if Path(name).exists():
            policy.add(name, READ_FILE)
    if gpu:
        for path in Path('/dev').glob('nvidia*'):
            if not path.is_dir():
                policy.add(str(path), READ_FILE | WRITE_FILE)
        policy.add(str(work / 'cache'), READ | WRITE)
    policy.apply()
    syscall_boundary(False)
    deny_processes()


def probes(work, canary):
    import socket
    tests = dict(host_read=lambda: open(canary).read(), host_write=lambda: open(canary, 'w').write('wrong'),
        rules_write=lambda: open(work / 'inputs/evidence.json', 'w').write('wrong'),
        truncate=lambda: os.truncate(canary, 0),
        symlink=lambda: os.symlink(canary, work / 'scratch/forbidden-link'),
        network=lambda: socket.socket(), subprocess=lambda: subprocess.run(['/bin/true']),
        process_signal=lambda: os.kill(os.getpid(), 0))
    results = {}
    for name, operation in tests.items():
        try:
            operation()
        except PermissionError:
            results[name] = True
        else:
            results[name] = False
    if not all(results.values()):
        raise RuntimeError('kernel boundary probe failed: ' + json.dumps(results))
    return results


def main(payload):
    work = Path(payload['work']).resolve()
    program = work / payload['program']
    code = program.read_bytes()
    gpu = not payload.get('cpu_probe', False)
    device = None
    if gpu:
        import torch
        torch.set_num_threads(1)
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1 or 'H100' not in torch.cuda.get_device_name(0):
            raise RuntimeError('one actual H100 required')
        warm = torch.ones((16, 16), device='cuda')
        torch.mm(warm, warm)
        torch.cuda.synchronize()
        device = dict(name=torch.cuda.get_device_name(0), torch_version=torch.__version__)
        del warm
    os.chdir(work)
    restrict(work, payload['stock'], payload['models'], gpu)
    checks = probes(work, payload['canary'])
    os.write(2, (json.dumps(dict(kernel_boundary_applied=True, boundary_checks=checks,
        gpu=gpu, device=device)) + '\n').encode())
    sys.argv = [str(program)]
    sys.path = [str(work / 'scratch'), *[entry for entry in sys.path if 'SpecPilot' not in entry]]
    if payload['stock']:
        sys.path.insert(0, str(Path(payload['stock']) / 'python'))
    exec(compile(code, str(program), 'exec'), dict(__name__='__main__', __file__=str(program)))


if __name__ == '__main__':
    try:
        main(json.load(sys.stdin))
    except BaseException:
        traceback.print_exc()
        sys.exit(1)
