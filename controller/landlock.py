"""Landlock (Linux 5.13+) 的 Python 绑定 —— 无 namespace 的文件系统沙箱。

本机 bwrap 不可用（无 user namespace 权限），Landlock 是唯一可用的内核级强制隔离。
ABI v1（内核 5.15）支持的访问位与后续 ABI 不同，构造 ruleset 时必须按 ABI 裁剪，
否则 landlock_create_ruleset 返回 EINVAL —— 这是实测踩过的坑。
"""
from __future__ import annotations

import ctypes
import os
import struct
from dataclasses import dataclass, field

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.syscall.restype = ctypes.c_long

_SYS_CREATE, _SYS_ADD_RULE, _SYS_RESTRICT = 444, 445, 446
_PR_SET_NO_NEW_PRIVS = 38

# fs access bits, ABI v1
EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
REMOVE_DIR = 1 << 4
REMOVE_FILE = 1 << 5
MAKE_CHAR = 1 << 6
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
MAKE_SOCK = 1 << 9
MAKE_FIFO = 1 << 10
MAKE_BLOCK = 1 << 11
# ABI v2+ (5.19+)
REFER = 1 << 13
TRUNCATE = 1 << 14

_V1_ALL = (1 << 12) - 1
_ABI_EXTRA = {2: REFER, 3: TRUNCATE}

READ = READ_FILE | READ_DIR
WRITE = WRITE_FILE | REMOVE_FILE | REMOVE_DIR | MAKE_DIR | MAKE_REG
FULL = READ | WRITE | EXECUTE


def abi_version() -> int:
    """返回内核支持的 Landlock ABI 版本；0 表示不支持。"""
    ctypes.set_errno(0)
    r = _libc.syscall(_SYS_CREATE, None, ctypes.c_size_t(0), ctypes.c_uint32(1))
    return r if r > 0 else 0


def supported_mask() -> int:
    v = abi_version()
    if v == 0:
        return 0
    mask = _V1_ALL
    for lvl in range(2, v + 1):
        mask |= _ABI_EXTRA.get(lvl, 0)
    return mask


class LandlockError(RuntimeError):
    pass


def _err(what: str) -> LandlockError:
    e = ctypes.get_errno()
    return LandlockError(f"{what} failed: {os.strerror(e)} (errno={e})")


@dataclass
class Policy:
    """按路径授予访问。未被授予的访问即被拒绝。

    Landlock 是白名单：授予某个目录会覆盖其整棵子树，且**无法**再在子树上收回。
    因此"拒绝某子目录"只能靠不给父目录授权、改为逐个授权兄弟项来实现。
    调用方应使用 scanner 生成 rules，而不是直接塞父目录。
    """

    rules: list[tuple[str, int]] = field(default_factory=list)

    def add(self, path: str, access: int) -> "Policy":
        self.rules.append((path, access))
        return self

    def apply(self) -> None:
        """在当前进程内不可逆地收紧权限。用 preexec_fn 传给 subprocess。"""
        abi = abi_version()
        if abi == 0:
            raise LandlockError("Landlock 不可用（内核 < 5.13 或未启用）")
        mask = supported_mask()
        handled = (READ | WRITE | EXECUTE) & mask

        buf = ctypes.create_string_buffer(struct.pack("<Q", handled), 8)
        ctypes.set_errno(0)
        rs = _libc.syscall(_SYS_CREATE, ctypes.cast(buf, ctypes.c_void_p),
                           ctypes.c_size_t(8), ctypes.c_uint32(0))
        if rs < 0:
            raise _err("landlock_create_ruleset")

        granted = 0
        try:
            for path, access in self.rules:
                access &= mask
                if not access:
                    continue
                rp = os.path.realpath(path)
                if not os.path.exists(rp):
                    continue
                fd = os.open(rp, os.O_PATH | os.O_CLOEXEC)
                try:
                    rule = ctypes.create_string_buffer(struct.pack("<Qi", access, fd), 12)
                    r = _libc.syscall(_SYS_ADD_RULE, ctypes.c_int(rs), ctypes.c_int(1),
                                      ctypes.cast(rule, ctypes.c_void_p), ctypes.c_uint32(0))
                    if r < 0:
                        raise _err(f"landlock_add_rule({rp})")
                    granted += 1
                finally:
                    os.close(fd)

            if granted == 0:
                raise LandlockError("policy 为空，拒绝应用")

            if _libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
                raise _err("prctl(NO_NEW_PRIVS)")

            ctypes.set_errno(0)
            if _libc.syscall(_SYS_RESTRICT, ctypes.c_int(rs), ctypes.c_uint32(0)) < 0:
                raise _err("landlock_restrict_self")
        finally:
            os.close(rs)


def grant_tree(path: str, access: int, deny: set[str]) -> list[tuple[str, int]]:
    """展开 path 为可授权项。

    关键约束：Landlock 授予目录会覆盖整棵子树，无法在子树上收回。所以
    - 子树里不含 deny → 整个目录一次授权；
    - 子树里含 deny → 该目录只授 READ_DIR（能列不能读），再逐个子项递归。
    """
    deny = {os.path.realpath(d) for d in deny}
    out: list[tuple[str, int]] = []

    def has_deny(p: str) -> bool:
        return any(d == p or d.startswith(p + os.sep) for d in deny)

    def walk(p: str, acc: int) -> None:
        rp = os.path.realpath(p)
        if not os.path.exists(rp):
            return
        if rp in deny:
            return
        if os.path.isdir(rp):
            if not has_deny(rp):
                out.append((rp, acc))
                return
            out.append((rp, acc & READ_DIR))
            for entry in sorted(os.listdir(rp)):
                walk(os.path.join(rp, entry), acc)
        else:
            out.append((rp, acc & (READ_FILE | WRITE_FILE | EXECUTE)))

    walk(path, access)
    return out
