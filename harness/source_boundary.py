"""Inherited filesystem/process boundary for source-option engine processes."""

import ctypes
import json
import os
from pathlib import Path
import resource
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controller.landlock import EXECUTE, READ, READ_FILE, WRITE, WRITE_FILE, Policy, abi_version


class SourcePolicy(Policy):
    def apply(self):
        version = abi_version()
        if version < 1:
            raise RuntimeError('source execution requires Landlock')
        library = ctypes.CDLL('libc.so.6', use_errno=True)
        library.syscall.restype = ctypes.c_long
        handled = (1 << 13) - 1
        if version >= 2:
            handled |= 1 << 13
        if version >= 3:
            handled |= 1 << 14
        attribute = ctypes.create_string_buffer(struct.pack('<Q', handled), 8)
        descriptor = library.syscall(444, ctypes.cast(attribute, ctypes.c_void_p), ctypes.c_size_t(8), ctypes.c_uint32(0))
        if descriptor < 0:
            raise OSError(ctypes.get_errno(), 'source Landlock ruleset creation failed')
        try:
            for name, access in self.rules:
                if not Path(name).exists():
                    continue
                parent = os.open(str(Path(name).resolve()), os.O_PATH | os.O_CLOEXEC)
                try:
                    rule = ctypes.create_string_buffer(struct.pack('<Qi', access & handled, parent), 12)
                    if library.syscall(445, ctypes.c_int(descriptor), ctypes.c_int(1),
                            ctypes.cast(rule, ctypes.c_void_p), ctypes.c_uint32(0)) < 0:
                        raise OSError(ctypes.get_errno(), 'source Landlock path rule failed: ' + name)
                finally:
                    os.close(parent)
            if library.prctl(38, 1, 0, 0, 0):
                raise OSError(ctypes.get_errno(), 'source no-new-privileges failed')
            if library.syscall(446, ctypes.c_int(descriptor), ctypes.c_uint32(0)) < 0:
                raise OSError(ctypes.get_errno(), 'source Landlock enforcement failed')
        finally:
            os.close(descriptor)


def process_filter():
    library = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    class Comparison(ctypes.Structure):
        _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_uint), ('first', ctypes.c_uint64), ('second', ctypes.c_uint64)]
    library.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
        ctypes.c_uint, ctypes.POINTER(Comparison)]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x7fff0000)
    if not context:
        raise RuntimeError('source seccomp initialization failed')
    denied = ('mount umount2 pivot_root unshare setns ptrace process_vm_readv process_vm_writev '
        'pidfd_getfd bpf perf_event_open open_by_handle_at name_to_handle_at io_uring_setup '
        'setuid setgid setreuid setregid setresuid setresgid setfsuid setfsgid setgroups capset '
        'setsid reboot kexec_load init_module finit_module '
        'delete_module swapon swapoff userfaultfd').split()
    try:
        for name in denied:
            number = library.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and library.seccomp_rule_add(context, 0x00050001, number, 0):
                raise RuntimeError('required source syscall denial failed: ' + name)
        number = library.seccomp_syscall_resolve_name(b'setpgid')
        for argument in (0, 1):
            comparison = Comparison(argument, 1, 0, 0)
            if number < 0 or library.seccomp_rule_add_array(context, 0x00050001, number, 1, ctypes.byref(comparison)):
                raise RuntimeError('source process-group restriction failed')
        if library.seccomp_load(context):
            raise RuntimeError('source seccomp installation failed')
    finally:
        library.seccomp_release(context)


def restrict(payload):
    diagnostic = payload.get('trusted_diagnostic')
    if diagnostic and not payload.get('trusted_gpu_probe'):
        raise ValueError('diagnostic variants cannot execute source code')
    original_scratch = Path(payload['scratch'])
    scratch = original_scratch.resolve(strict=True)
    if original_scratch.is_symlink() or not scratch.is_dir():
        raise ValueError('concrete source cache directory required')
    if not payload.get('cpu_probe'):
        if os.geteuid() != 0 or type(payload['uid']) is not int or not 60000 <= payload['uid'] <= 60100:
            raise RuntimeError('production source execution requires a dedicated unprivileged UID')
        os.chown(scratch, payload['uid'], payload['uid'])
        os.setgroups([])
        os.setresgid(payload['uid'], payload['uid'], payload['uid'])
        os.setresuid(payload['uid'], payload['uid'], payload['uid'])
        if os.geteuid() == 0 or os.getuid() != payload['uid']:
            raise RuntimeError('source UID isolation failed')
    if diagnostic in ('uid_only', 'seccomp_only'):
        if diagnostic == 'seccomp_only':
            process_filter()
        os.chdir(scratch)
        return
    policy = SourcePolicy()
    for name in payload['readonly']:
        path = Path(name).resolve(strict=True)
        if path == Path('/') or scratch.is_relative_to(path):
            raise ValueError('broad read grant overlaps private writable cache')
        policy.add(str(path), READ if path.is_dir() else READ_FILE)
    for name in ('/usr/lib', '/lib', '/lib64', '/usr/share/zoneinfo'):
        if Path(name).exists():
            policy.add(name, READ)
    for name in ('/etc/ld.so.cache', '/etc/localtime', '/etc/hosts', '/etc/resolv.conf',
                 '/etc/nsswitch.conf', '/etc/mime.types', '/etc/hostname', '/etc/os-release',
                 '/etc/gai.conf', '/etc/host.conf', '/dev/urandom', '/dev/random', '/proc/cpuinfo', '/proc/meminfo'):
        if Path(name).exists():
            policy.add(name, READ_FILE)
    for name in payload['executables']:
        path = Path(name).resolve(strict=True)
        policy.add(str(path), READ_FILE | EXECUTE)
    for name in payload.get('executable_trees', []):
        policy.add(str(Path(name).resolve(strict=True)), READ | EXECUTE)
    if not payload.get('cpu_probe'):
        policy.add('/proc', READ | WRITE_FILE)
    for name in ('/lib64/ld-linux-x86-64.so.2', '/lib/ld-linux-aarch64.so.1'):
        if Path(name).exists():
            policy.add(name, READ_FILE | EXECUTE)
    for name in payload.get('devices', []):
        if not str(name).startswith('/dev/nvidia') or not Path(name).exists():
            raise ValueError('only explicit assigned NVIDIA devices can be granted')
        policy.add(str(name), READ_FILE | WRITE_FILE)
    policy.add('/dev/null', READ_FILE | WRITE_FILE)
    writable = READ | WRITE | (1 << 9) | (1 << 10) | (1 << 12)
    if abi_version() >= 2:
        writable |= 1 << 13
    if abi_version() >= 3:
        writable |= 1 << 14
    if Path('/dev/shm').is_dir():
        policy.add('/dev/shm', writable)
    policy.add(str(scratch), writable)
    policy.apply()
    if diagnostic != 'filesystem_only':
        process_filter()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (536870912, 536870912))
    resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))
    os.chdir(scratch)


def probes(payload):
    scratch = Path(payload['scratch'])
    output = scratch / 'allowed-write.txt'
    output.write_text('cache writable\n')
    if Path(payload['allowed_read']).read_text() != payload['allowed_content']:
        raise RuntimeError('authorized source read failed')
    checks = {}
    tests = dict(protected_read=lambda: Path(payload['canary']).read_bytes(),
        protected_write=lambda: Path(payload['canary']).write_text('wrong'),
        source_write=lambda: Path(payload['allowed_read']).write_text('wrong'),
        escape_session=lambda: os.setsid(),
        root_filesystem=lambda: Path('/etc/passwd').read_bytes())
    if payload.get('forbidden_device'):
        tests['unassigned_device'] = lambda: os.open(payload['forbidden_device'], os.O_RDWR)
    if payload.get('protected_proc'):
        tests['trusted_parent_environment'] = lambda: Path(payload['protected_proc']).read_bytes()
    if payload.get('protected_pid'):
        tests['trusted_parent_signal'] = lambda: os.kill(payload['protected_pid'], 0)
    for name, operation in tests.items():
        try:
            value = operation()
            if type(value) is int and name == 'unassigned_device':
                os.close(value)
        except PermissionError:
            checks[name] = True
        else:
            checks[name] = False
    if not all(checks.values()):
        raise RuntimeError('source boundary probe failed: ' + json.dumps(checks))
    os.kill(os.getpid(), 0)
    return dict(allowed_read=True, cache_write=output.read_text() == 'cache writable\n', own_process_signals_allowed=True,
        denied=checks, uid=os.geteuid(), landlock_applied=True, seccomp_applied=True,
        network_isolated=False, scope='file/process/device grants; engine IPC and network remain available')


def main(payload):
    restrict(payload)
    receipt = (dict(trusted_diagnostic=payload['trusted_diagnostic'], isolation_accepted=False)
        if payload.get('trusted_diagnostic') else probes(payload))
    ready_fd = payload.get('ready_fd')
    if ready_fd is not None:
        if type(ready_fd) is not int or ready_fd < 3:
            raise ValueError('dedicated trusted boundary pipe required')
        os.write(ready_fd, (json.dumps(dict(event='SOURCE_BOUNDARY_READY', **receipt)) + '\n').encode())
        os.close(ready_fd)
    os.write(1, (json.dumps(dict(event='SOURCE_BOUNDARY_READY', **receipt)) + '\n').encode())
    if payload.get('trusted_gpu_probe'):
        import torch
        torch.set_num_threads(1)
        if torch.cuda.device_count() != 1 or 'H100' not in torch.cuda.get_device_name(0):
            raise RuntimeError('source boundary requires one assigned H100')
        tensor = torch.ones((16, 16), device='cuda')
        torch.mm(tensor, tensor)
        torch.cuda.synchronize()
        print(json.dumps(dict(event='SOURCE_GPU_READY', device=torch.cuda.get_device_name(0),
            torch_version=torch.__version__)), flush=True)
        return
    if payload.get('cpu_probe') or payload.get('probe_only'):
        return
    command = payload['command']
    if str(Path(command[0]).resolve(strict=True)) not in {
            str(Path(name).resolve(strict=True)) for name in payload['executables']}:
        raise ValueError('source executable outside the fixed runtime')
    os.execve(command[0], command, payload['environment'])


if __name__ == '__main__':
    main(json.load(sys.stdin))
