"""Container-compatible CPU sandbox: chroot, dropped UID/GID, seccomp allowlist.

The container lacks Landlock. This worker uses independently checked kernel
boundaries and an isolated copy of scratch; it never executes unsandboxed code.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time


def execute_python(work, name, record):
    work, record = Path(work).resolve(), Path(record)
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts: raise ValueError('Invalid program path')
    program = work / relative
    if not program.is_file() or program.is_symlink() or program.suffix != '.py': raise ValueError('Python file required')
    record.mkdir(parents=True, exist_ok=False)
    sandbox = record / 'sandbox-root'; sandbox.mkdir(mode=0o755)
    total = 0
    for source in work.rglob('*'):
        if source.is_symlink(): raise ValueError('No scratch symlinks permitted')
        if not source.is_file(): continue
        total += source.stat().st_size
        if total > 4 * 1024 * 1024: raise ValueError('Scratch copy exceeds 4 MiB')
        destination = sandbox / source.relative_to(work)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination); destination.chmod(0o444)
    for p in sorted(sandbox.rglob('*'), reverse=True):
        if p.is_dir(): p.chmod(0o555)
    sandbox.chmod(0o555)
    started = time.monotonic()
    payload = {'sandbox': str(sandbox.resolve()), 'program': str(relative)}
    with (record / 'stdout').open('xb') as stdout, (record / 'stderr').open('xb') as stderr:
        p = subprocess.Popen([sys.executable, '-I', '-S', str(Path(__file__).resolve()), '--worker'],
            stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'},
            close_fds=True, start_new_session=True)
        timeout = False
        try: p.communicate(json.dumps(payload).encode(), timeout=8)
        except subprocess.TimeoutExpired:
            timeout = True; os.killpg(p.pid, signal.SIGKILL); p.communicate()
    output = {k: (record / k).read_bytes() for k in ('stdout', 'stderr')}
    ready = output['stderr'].startswith(b'SP_CHROOT_SECCOMP_READY\n')
    result = {'status': 'timeout' if timeout else 'completed' if ready and p.returncode == 0 else 'failed',
              'exit_code': p.returncode, 'wall_seconds': time.monotonic() - started,
              'chroot_applied': ready, 'dropped_uid': 65534 if ready else None, 'seccomp_applied': ready,
              'landlock_applied': False, 'code_sha256': hashlib.sha256(program.read_bytes()).hexdigest(),
              'stdout': output['stdout'][:12000].decode(errors='replace'),
              'stderr': output['stderr'].removeprefix(b'SP_CHROOT_SECCOMP_READY\n')[:12000].decode(errors='replace'),
              'output_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in output.items()},
              'scope': 'CPU-only isolated analysis; no NPU or performance promotion'}
    (record / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def worker():
    # Preload useful standard-library analysis modules before closing the filesystem.
    import collections, csv, decimal, difflib, fractions, functools, heapq, io, itertools
    import math, random, re, socket, statistics, textwrap, traceback
    payload = json.load(sys.stdin)
    sandbox = Path(payload['sandbox']).resolve(strict=True)
    program = sandbox / payload['program']
    assert program.resolve().is_relative_to(sandbox)
    code = program.read_text()
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    library = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]; library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]; library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    class Comparison(ctypes.Structure):
        _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_uint), ('first', ctypes.c_uint64), ('second', ctypes.c_uint64)]
    library.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(Comparison)]
    library.seccomp_load.argtypes = [ctypes.c_void_p]; library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x00050001)
    if not context: raise RuntimeError('seccomp unavailable')
    allow = ('read write close fstat newfstatat stat lstat lseek mmap mprotect munmap brk rt_sigaction '
             'rt_sigprocmask rt_sigreturn ioctl pread64 readv writev access readlink readlinkat '
             'getdents64 getcwd clock_gettime clock_nanosleep nanosleep gettimeofday time futex '
             'sched_yield getpid getppid gettid getuid geteuid getgid getegid getrandom madvise '
             'sigaltstack exit exit_group fstatfs statfs').split()
    for name in allow:
        n = library.seccomp_syscall_resolve_name(name.encode())
        if n >= 0 and library.seccomp_rule_add(context, 0x7fff0000, n, 0) != 0: raise RuntimeError('seccomp rule failed')
    comparison = Comparison(2, 7, os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND, 0)
    n = library.seccomp_syscall_resolve_name(b'openat')
    if n < 0 or library.seccomp_rule_add_array(context, 0x7fff0000, n, 1, ctypes.byref(comparison)) != 0:
        raise RuntimeError('read-only openat rule failed')
    os.chdir(sandbox); os.chroot('.'); os.chdir('/')
    os.setgroups([]); os.setgid(65534); os.setuid(65534)
    os.closerange(3, 65536)
    os.environ.clear()
    if library.seccomp_load(context) != 0: raise RuntimeError('seccomp activation failed')
    library.seccomp_release(context)
    os.write(2, b'SP_CHROOT_SECCOMP_READY\n')
    sys.argv = [payload['program']]
    try:
        exec(compile(code, '/' + payload['program'], 'exec'), {'__name__': '__main__', '__file__': '/' + payload['program']})
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc(); sys.exit(1)


if __name__ == '__main__':
    assert sys.argv[1:] == ['--worker']
    worker()
