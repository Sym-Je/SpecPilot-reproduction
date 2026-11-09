"""Kernel boundary for a standalone research runtime, not the privileged chat."""

import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from controller.landlock import EXECUTE,READ,READ_FILE,WRITE,WRITE_FILE,Policy

READY=b'SP_ROLE_ISOLATION_READY\n'


def syscall_boundary(network):
    library=ctypes.CDLL('libseccomp.so.2',use_errno=True)
    library.seccomp_init.argtypes=[ctypes.c_uint32]
    library.seccomp_init.restype=ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype=ctypes.c_int
    library.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    class Comparison(ctypes.Structure):
        _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_uint),('first',ctypes.c_uint64),('second',ctypes.c_uint64)]
    library.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(Comparison)]
    library.seccomp_load.argtypes=[ctypes.c_void_p]
    library.seccomp_release.argtypes=[ctypes.c_void_p]
    context=library.seccomp_init(0x7fff0000)
    if not context:raise RuntimeError('seccomp unavailable; refuse role launch')
    denied=('truncate truncate64 symlink symlinkat link linkat openat2 io_uring_setup '
        'mount umount2 pivot_root unshare setns ptrace process_vm_readv process_vm_writev '
        'pidfd_getfd bpf perf_event_open open_by_handle_at name_to_handle_at '
        'chmod fchmod fchmodat fchmodat2 chown fchown lchown fchownat '
        'utime utimes futimesat utimensat mknod mknodat setxattr lsetxattr fsetxattr '
        'removexattr lremovexattr fremovexattr').split()
    if not network:denied+=['socket','socketpair','connect','bind','listen','accept','accept4']
    try:
        for name in denied:
            number=library.seccomp_syscall_resolve_name(name.encode())
            if number>=0 and library.seccomp_rule_add(context,0x00050001,number,0)!=0:
                raise RuntimeError('cannot install required syscall denial')
        for name,argument in (('open',1),('openat',2)):
            number=library.seccomp_syscall_resolve_name(name.encode())
            comparison=Comparison(argument,7,os.O_ACCMODE|os.O_TRUNC,os.O_TRUNC)
            if number>=0 and library.seccomp_rule_add_array(context,0x00050001,number,1,ctypes.byref(comparison))!=0:
                raise RuntimeError('cannot restrict read-only truncation')
        if library.seccomp_load(context)!=0:raise RuntimeError('seccomp load failed')
    finally:library.seccomp_release(context)


def payload_for(work,command,executables,readonly,writable,network,environment):
    work=Path(work).resolve(strict=True)
    permitted={str(Path(name).resolve(strict=True)) for name in executables}
    if not command or not Path(command[0]).is_absolute() or str(Path(command[0]).resolve()) not in permitted:
        raise ValueError('command must name an explicitly permitted executable')
    if not (work/'scratch').is_dir() or (work/'scratch').is_symlink():raise ValueError('regular scratch directory required')
    read_paths=[str(Path(name).resolve(strict=True)) for name in readonly]
    if any(work.is_relative_to(Path(name)) or Path(name) in (ROOT,*ROOT.parents) for name in read_paths):
        raise ValueError('broad ancestor read grant rejected')
    writes=[str((work/'scratch').resolve())]
    for name in writable:
        path=Path(name).resolve(strict=True)
        if path==work or work.is_relative_to(path):raise ValueError('broad ancestor write grant rejected')
        writes.append(str(path))
    env=dict(PATH='/usr/bin:/bin',HOME=str(work),TMPDIR=str(work/'scratch'),CUDA_VISIBLE_DEVICES='',
        PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',LANG='C.UTF-8')
    env.update(environment)
    return dict(work=str(work),command=[str(Path(command[0]).resolve()),*command[1:]],
        executables=sorted(permitted),readonly=read_paths,writable=writes,network=network,environment=env)


def start_command(work,command,*,executables,readonly=(),writable=(),network=False,environment=None,stderr=subprocess.PIPE):
    payload=payload_for(work,command,executables,readonly,writable,network,environment or {})
    worker=Path(__file__).resolve()
    process=subprocess.Popen([sys.executable,'-I','-B','-S',str(worker)],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=stderr,cwd=work,close_fds=True,start_new_session=True,bufsize=0)
    process.stdin.write((json.dumps(payload)+'\n').encode());process.stdin.flush()
    return process


def launch_command(work,command,*,executables,readonly=(),writable=(),network=False,environment=None,timeout=10):
    process=start_command(work,command,executables=executables,readonly=readonly,writable=writable,
        network=network,environment=environment)
    try:stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);process.communicate()
        raise
    if not stderr.startswith(READY):raise RuntimeError('role kernel bootstrap failed: '+stderr.decode(errors='replace')[:800])
    return subprocess.CompletedProcess(command,process.returncode,stdout.decode(errors='replace'),
        stderr.removeprefix(READY).decode(errors='replace'))


def enter(payload):
    work=Path(payload['work'])
    policy=Policy().add(str(work),READ)
    for path in ('/usr/lib','/lib','/lib64','/usr/share/zoneinfo',*payload['readonly']):
        policy.add(path,READ if Path(path).is_dir() else READ_FILE)
    for path in payload['executables']:policy.add(path,READ_FILE|EXECUTE)
    for path in ('/lib64/ld-linux-x86-64.so.2','/lib/ld-linux-aarch64.so.1'):policy.add(path,READ_FILE|EXECUTE)
    for path in payload['writable']:
        policy.add(path,READ|WRITE if Path(path).is_dir() else READ_FILE|WRITE_FILE)
    for path in ('/etc/ld.so.cache','/etc/localtime','/dev/urandom','/dev/random'):policy.add(path,READ_FILE)
    policy.add('/dev/null',READ_FILE|WRITE_FILE)
    policy.apply()
    syscall_boundary(payload['network'])
    os.chdir(work)
    os.write(2,READY)
    os.execve(payload['command'][0],payload['command'],payload['environment'])


if __name__=='__main__':
    line=bytearray()
    while True:
        value=os.read(0,1)
        if not value or value==b'\n':break
        line.extend(value)
        if len(line)>65536:raise ValueError('bounded trusted launch payload required')
    enter(json.loads(line))
