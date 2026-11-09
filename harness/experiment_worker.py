"""Trusted CPU bootstrap; untrusted experiment code runs only after both filters."""

import ctypes
import json
import os
from pathlib import Path
import resource
import sys
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller.landlock import Policy,READ,READ_FILE


def restrict(work):
    resource.setrlimit(resource.RLIMIT_CPU,(3,3))
    resource.setrlimit(resource.RLIMIT_AS,(768*1024**2,768*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
    resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    policy=Policy()
    for path in (sys.prefix,'/usr/lib','/lib','/lib64','/usr/share/zoneinfo',str(work)):
        policy.add(path,READ)
    for path in ('/dev/null','/dev/urandom','/etc/ld.so.cache'):
        policy.add(path,READ_FILE)
    policy.apply()
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
    context=library.seccomp_init(0x00050000|1)
    if not context:raise RuntimeError('seccomp unavailable; execution refused')
    allowed=('read write close fstat newfstatat stat lstat lseek mmap mprotect munmap brk rt_sigaction '
        'rt_sigprocmask rt_sigreturn ioctl pread64 readv writev access readlink readlinkat '
        'getdents64 getcwd clock_gettime clock_nanosleep nanosleep gettimeofday time futex '
        'sched_yield getpid getppid gettid getuid geteuid getgid getegid getrandom madvise '
        'sigaltstack exit exit_group dup dup2 dup3 fstatfs statfs').split()
    try:
        for name in allowed:
            number=library.seccomp_syscall_resolve_name(name.encode())
            if number>=0 and library.seccomp_rule_add(context,0x7fff0000,number,0)!=0:
                raise RuntimeError('seccomp syscall restriction failed')
        flags=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND
        comparison=Comparison(2,7,flags,0)
        number=library.seccomp_syscall_resolve_name(b'openat')
        if number<0 or library.seccomp_rule_add_array(context,0x7fff0000,number,1,ctypes.byref(comparison))!=0:
            raise RuntimeError('seccomp read-only file restriction failed')
        if library.seccomp_load(context)!=0:raise RuntimeError('seccomp load failed')
    finally:
        library.seccomp_release(context)


if __name__=='__main__':
    payload=json.load(sys.stdin)
    work=Path(payload['work']).resolve()
    program=Path(payload['program'])
    code=program.read_text()
    os.chdir(work)
    restrict(work)
    os.write(2,b'SP_ISOLATION_READY\n')
    sys.argv=[str(program)]
    namespace=dict(__name__='__main__',__file__=str(program))
    try:
        exec(compile(code,str(program),'exec'),namespace)
    except BaseException:
        traceback.print_exc()
        sys.exit(1)
