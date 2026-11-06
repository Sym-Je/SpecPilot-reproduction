"""在 Landlock 策略下运行子进程 —— agent 侧唯一的执行入口。

角色 → 路径映射写死在 ROLE_GRANTS 里。命令行只能选角色名，不能传路径，
所以 agent 无法通过参数给自己扩权。

DENY 优先于 GRANT：deny 中的子树在任何角色下都不可读写（除了 controller 自己）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from . import landlock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 运行时必需的系统路径（python/node 自己要用）
SYSTEM_R = ["/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/opt", "/proc", "/sys", "/dev"]
SYSTEM_X = ["/usr", "/lib", "/lib64", "/bin", "/sbin", "/opt"]

# 任何角色都不得触碰的子树（相对 ROOT）
DENY_ALWAYS = ["ledger", "eval/sealed", "controller", "memory/entries"]

# 每个角色：可读的仓库子目录、可写的仓库子目录
ROLE_GRANTS: dict[str, dict[str, list[str]]] = {
    "direction":   {"read": ["."], "write": ["patches", "scratch"]},
    "kernel":      {"read": ["."], "write": ["patches", "scratch"]},
    "integration": {"read": ["."], "write": ["patches", "docs", "scratch"]},
    "auditor":     {"read": ["."], "write": []},
    "master":      {"read": ["."], "write": ["scratch"]},
}


def deny_set() -> set[str]:
    return {os.path.realpath(os.path.join(ROOT, d)) for d in DENY_ALWAYS}


def build_policy(role: str) -> landlock.Policy:
    spec = ROLE_GRANTS[role]
    deny = deny_set()
    pol = landlock.Policy()

    for p in SYSTEM_R:
        pol.add(p, landlock.READ)
    for p in SYSTEM_X:
        pol.add(p, landlock.EXECUTE)

    for rel in spec["read"]:
        base = ROOT if rel == "." else os.path.join(ROOT, rel)
        for path, access in landlock.grant_tree(base, landlock.READ, deny):
            pol.add(path, access)

    for rel in spec["write"]:
        base = os.path.join(ROOT, rel)
        os.makedirs(base, exist_ok=True)
        for path, access in landlock.grant_tree(base, landlock.READ | landlock.WRITE, deny):
            pol.add(path, access)

    pol.add("/tmp", landlock.READ | landlock.WRITE)
    return pol


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="controller.sandbox")
    ap.add_argument("--role", required=True, choices=sorted(ROLE_GRANTS))
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    ns = ap.parse_args(argv)
    cmd = [c for c in ns.cmd if c != "--"]
    if not cmd:
        ap.error("缺少要执行的命令")

    policy = build_policy(ns.role)
    env = dict(os.environ, SPECPILOT_ROLE=ns.role, PYTHONPATH=ROOT)
    proc = subprocess.run(cmd, preexec_fn=policy.apply, env=env)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
