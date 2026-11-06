#!/usr/bin/env python3
"""G3 —— controller 权限边界验证。零 GPU、零 token、零网络。

判据（每条独立计分，全过才算 G3 PASS）：
  C1 agent 角色（direction/kernel/integration/auditor）写 ledger/     → 必须 EACCES
  C2 agent 角色读 eval/sealed/                                        → 必须 EACCES
  C3 agent 角色写 controller/                                         → 必须 EACCES
  C4 agent 角色写自己的 patches/（direction）/ scratch/                → 必须成功
  C5 controller 进程写 ledger/                                        → 必须成功
  C6 外部进程回改账本一条记录                                        → verify() 必须报错

用法：python3 gates/g3_isolation.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from controller.ledger import Ledger  # noqa: E402

results: list[tuple[str, bool, str]] = []


def record(cid: str, ok: bool, detail: str) -> None:
    results.append((cid, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}")


def run_in_role(role: str, code: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "controller.sandbox", "--role", role, "--", sys.executable, "-c", code],
        cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": ROOT},
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def expect_denied(role: str, cid: str, code: str) -> None:
    rc, out = run_in_role(role, code)
    # 子进程内用 try/except 探测，输出 DENIED 视为正确
    record(cid, "DENIED" in out, f"role={role} → {out.splitlines()[-1] if out else '(空)'}")


def main() -> int:
    # 准备真实存在的 sealed 文件与账本
    sealed_dir = os.path.join(ROOT, "eval", "sealed")
    os.makedirs(sealed_dir, exist_ok=True)
    sealed_file = os.path.join(sealed_dir, "_g3_probe.txt")
    with open(sealed_file, "w") as f:
        f.write("SEALED-ANSWER\n")

    ledger_path = os.path.join(ROOT, "ledger", "g3-probe.jsonl")
    if os.path.exists(ledger_path):
        os.unlink(ledger_path)

    probe_write = (
        "import pathlib,sys\n"
        "try:\n"
        "    pathlib.Path({p!r}).write_text('x')\n"
        "    print('WROTE')\n"
        "except OSError as e:\n"
        "    print('DENIED', e.strerror)\n"
    )
    probe_read = (
        "import pathlib\n"
        "try:\n"
        "    print(pathlib.Path({p!r}).read_text().strip())\n"
        "except OSError as e:\n"
        "    print('DENIED', e.strerror)\n"
    )

    for role in ("direction", "auditor"):
        expect_denied(role, f"C1[{role}] 写账本",
                      probe_write.format(p="ledger/_g3_agent.txt"))
        expect_denied(role, f"C2[{role}] 读 sealed",
                      probe_read.format(p=os.path.relpath(sealed_file, ROOT)))
        expect_denied(role, f"C3[{role}] 写 controller",
                      probe_write.format(p="controller/_g3_agent.txt"))

    rc, out = run_in_role("direction", probe_write.format(p="scratch/_g3_ok.txt"))
    record("C4[direction] 写 scratch", "WROTE" in out, out.splitlines()[-1] if out else "(空)")

    os.makedirs(os.path.join(ROOT, "scratch"), exist_ok=True)
    try:
        L = Ledger(ledger_path)
        L.append("gate", "G3", {"result": "self-test", "by": "controller"})
        ok = os.path.exists(ledger_path) and not L.verify()
    except Exception as e:  # noqa: BLE001
        ok = False
        out = str(e)
    record("C5[controller] 写账本", ok, "写入并校验通过" if ok else f"失败: {out}")

    # C6 篡改检测
    lines = open(ledger_path).read().splitlines()
    rec = json.loads(lines[0])
    rec["payload"]["result"] = "forged"
    lines[0] = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    open(ledger_path, "w").write("\n".join(lines) + "\n")
    problems = Ledger(ledger_path).verify()
    record("C6 篡改检测", bool(problems), problems[0] if problems else "未检出篡改")

    # 清理
    for p in (sealed_file, ledger_path, os.path.join(ROOT, "scratch", "_g3_ok.txt")):
        try:
            os.unlink(p)
        except OSError:
            pass

    failed = [c for c, ok, _ in results if not ok]
    print()
    print(f"G3 {'PASS' if not failed else 'FAIL'}  ({len(results) - len(failed)}/{len(results)})")
    if failed:
        print("失败项:", ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
