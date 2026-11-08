"""Conservative task proxies and fail-closed, CPU-only code-test isolation."""

import argparse
from collections import Counter
import ctypes
import ctypes.util
from fractions import Fraction
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def final_text(text):
    text = re.sub(r'(?:<\|im_end\|>|<\|endoftext\|>|<\|eot_id\|>)\s*$', '', text)
    if '</think>' in text:
        return text.rsplit('</think>', 1)[1].strip()
    if '<think>' in text:
        return ''
    return text.strip()


def normalized(text):
    return ''.join(character for character in unicodedata.normalize('NFKC', text).lower()
                   if character.isalnum())


def boxed(text):
    start = text.rfind('\\boxed{')
    if start < 0:
        return text.strip().strip('$')
    depth, contents = 1, []
    for character in text[start + 7:]:
        depth += (character == '{') - (character == '}')
        if depth == 0:
            return ''.join(contents)
        contents.append(character)
    return ''


def numeric(text):
    text = boxed(text).replace(',', '').replace('$', '').strip()
    if '####' in text:
        text = text.rsplit('####', 1)[1].strip()
    fraction = re.fullmatch(r'\\(?:d?frac)\{(-?[0-9.]+)\}\{(-?[0-9.]+)\}', text)
    try:
        return str(Fraction(fraction[1]) / Fraction(fraction[2])) if fraction else str(Fraction(text))
    except (ValueError, ZeroDivisionError):
        return text.replace(' ', '').replace('\\left', '').replace('\\right', '')


def tokens(text):
    return re.findall(r'[\u3400-\u9fff]|[a-z0-9]+', unicodedata.normalize('NFKC', text).lower())


def token_f1(prediction, reference):
    predicted, expected = tokens(prediction), tokens(reference)
    if not predicted or not expected:
        return float(predicted == expected)
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    return 2 * overlap / (len(predicted) + len(expected))


def rouge_l(prediction, reference):
    predicted, expected = tokens(prediction), tokens(reference)
    if not predicted or not expected:
        return float(predicted == expected)
    previous = [0] * (len(expected) + 1)
    for token in predicted:
        current = [0]
        for index, other in enumerate(expected):
            current.append(previous[index] + 1 if token == other else max(previous[index + 1], current[-1]))
        previous = current
    return 2 * previous[-1] / (len(predicted) + len(expected))


def secure_worker():
    from controller.landlock import Policy, READ

    payload = json.load(sys.stdin)
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    policy = Policy()
    for path in (sys.prefix, '/usr/lib', '/lib', '/lib64', '/usr/share/zoneinfo'):
        policy.add(path, READ)
    for path in ('/dev/null', '/dev/urandom', '/etc/ld.so.cache'):
        policy.add(path, 1 << 2)
    policy.apply()
    library = ctypes.CDLL(ctypes.util.find_library('seccomp') or 'libseccomp.so.2', use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    class Comparison(ctypes.Structure):
        _fields_ = [('arg',ctypes.c_uint),('op',ctypes.c_uint),('datum_a',ctypes.c_uint64),('datum_b',ctypes.c_uint64)]
    library.seccomp_rule_add_array.argtypes = [ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(Comparison)]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x00050000 | 1)
    if not context:
        raise RuntimeError('seccomp initialization failed')
    allowed = ('read write close fstat newfstatat stat lstat lseek mmap mprotect munmap brk rt_sigaction '
               'rt_sigprocmask rt_sigreturn ioctl pread64 readv writev access readlink readlinkat '
               'getdents64 getcwd clock_gettime clock_nanosleep nanosleep gettimeofday time futex '
               'sched_yield getpid getppid gettid getuid geteuid getgid getegid getrandom madvise '
               'sigaltstack exit exit_group dup dup2 dup3 fstatfs statfs').split()
    try:
        for name in allowed:
            number = library.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and library.seccomp_rule_add(context, 0x7fff0000, number, 0) != 0:
                raise RuntimeError('seccomp allowlist failed')
        write_flags=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|getattr(os,'O_TMPFILE',0)
        comparison=Comparison(2,7,write_flags,0)
        number=library.seccomp_syscall_resolve_name(b'openat')
        if number < 0 or library.seccomp_rule_add_array(context,0x7fff0000,number,1,ctypes.byref(comparison)) != 0:
            raise RuntimeError('read-only openat constraint failed')
        if library.seccomp_load(context) != 0:
            raise RuntimeError('seccomp load failed')
    finally:
        library.seccomp_release(context)
    namespace = {}
    try:
        exec(compile(payload['code'], '<candidate>', 'exec'), namespace)
        exec(compile(payload['tests'], '<tests>', 'exec'), namespace)
    except BaseException:
        os._exit(1)
    os.write(1, b'\nspecpilot-tests-completed\n')
    os._exit(0)


def run_code(code, tests, timeout=6):
    with tempfile.TemporaryDirectory(prefix='specpilot-quality-') as temporary:
        environment = dict(PATH='/usr/bin:/bin', HOME=temporary, TMPDIR=temporary,
                           CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1')
        try:
            path = Path(temporary) / 'result'
            with path.open('wb') as output:
                result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--worker'],
                    input=json.dumps(dict(code=code, tests=tests)), text=True,
                    stdout=output, stderr=subprocess.DEVNULL, cwd=temporary,
                    env=environment, timeout=timeout, close_fds=True)
            passed = result.returncode == 0 and path.read_bytes().endswith(b'\nspecpilot-tests-completed\n')
            return dict(status='pass' if passed else 'fail', exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            return dict(status='timeout')


def grade(item, text):
    final = '' if item.get('thinking_required') and '</think>' not in text else final_text(text)
    metric = item['metric']
    if metric == 'ungraded':
        return dict(score=None, metric='not_semantically_evaluated', answered=bool(final))
    if not final:
        return dict(score=0., metric=metric, answered=False)
    if metric == 'numeric':
        score = float(numeric(final) == numeric(item['answer']))
    elif metric in ('qa', 'json'):
        if metric == 'json':
            try:
                candidate = re.sub(r'^```(?:json)?\s*|\s*```$', '', final).strip()
                candidate = json.loads(candidate)
                if set(candidate) != {'answer'} or not isinstance(candidate['answer'], str):
                    raise ValueError('invalid answer schema')
                final = candidate['answer']
            except (ValueError, TypeError):
                return dict(score=0., exact=0., metric=metric, answered=True)
        score = max(token_f1(final, answer) for answer in item['answers'])
        return dict(score=score, exact=float(any(normalized(final) == normalized(answer) for answer in item['answers'])),
                    metric=metric, answered=True)
    elif metric == 'rouge_l':
        score = rouge_l(final, item['answer'])
    elif metric == 'code':
        blocks = re.findall(r'```(?:python|py)?\s*\n(.*?)```', final, re.S)
        code = blocks[-1] if blocks else final
        if item.get('entry_point') and not re.search(r'\bdef\s+' + re.escape(item['entry_point']) + r'\s*\(', code):
            code = item['code_prompt'] + code
        execution = run_code(code, item['tests'])
        return dict(score=float(execution['status'] == 'pass'), metric=metric, answered=True, execution=execution)
    else:
        raise ValueError('unregistered quality metric')
    return dict(score=score, metric=metric, answered=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true', required=True)
    parser.parse_args()
    secure_worker()
