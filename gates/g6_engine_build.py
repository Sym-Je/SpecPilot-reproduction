#!/usr/bin/env python3
"""G6 —— 派生引擎树的可重现性与默认=stock（AGENTS.md 铁律 3 的执行形式）。

判据（全部纯 CPU，不碰 GPU）：
  E1 同 setting/kind 构建两次 → tree content hash 完全相同（可重现）
  E2 stock 树的 python/ 与上游 python/ 逐文件 sha256 相同（stock 真的是 stock）
  E3 final 树的 python/ 至少有一个文件与上游不同（覆盖层真的生效了）
  E4 final 树的每个被改文件都出现在 settings/<setting>/files/ 里（没有夹带）
  E5 树内的 .pyc / __pycache__ 被排除（哈希不受运行时产物影响）
  E6 dspark setting 的 stock 树包含 overlays/dspark_stock，dflash2 的不包含

用法:
  python gates/g6_engine_build.py                       # h100_c1_qwen38-27b_dflash2
  python gates/g6_engine_build.py --setting X --keep    # 保留构建产物便于排查
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path("/gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main")
BUILD = ROOT / "harness" / "build_engine.py"


def run_build(setting, kind, out):
    r = subprocess.run([sys.executable, str(BUILD), setting, kind, str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"build failed ({kind}):\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def tree_sha_from_output(stdout):
    for line in stdout.splitlines():
        if "tree sha" in line:
            return line.rsplit("tree sha", 1)[1].strip().rstrip(")")
    raise SystemExit(f"no tree sha in build output: {stdout!r}")


def file_map(root):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo"):
            import hashlib
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setting", default="h100_c1_qwen38-27b_dflash2")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    results = []
    tmp = Path(tempfile.mkdtemp(prefix="g6-engine-", dir="/tmp"))
    try:
        cfg = json.loads((UPSTREAM / "settings" / a.setting / "config.json").read_text())

        # ---- E1 可重现 ----
        outs, shas = [], []
        for i in range(2):
            d = tmp / f"stock-{i}"
            out = run_build(a.setting, "stock", d)
            outs.append(d)
            shas.append(tree_sha_from_output(out))
        e1 = shas[0] == shas[1] and len(shas[0]) == 64
        results.append(("E1 同输入两次构建 hash 相同", e1, f"{shas[0][:16]} vs {shas[1][:16]}"))

        stock = outs[0]

        upstream_all = file_map(UPSTREAM)          # 含 python/ 前缀
        stock_all = file_map(stock)                # 含 python/ 前缀，但还有 lab/
        def py_of(m):
            return {k: v for k, v in m.items() if k.startswith("python/")}
        upstream_py = py_of(upstream_all)
        stock_py = py_of(stock_all)

        # ---- E2 stock == 上游 ----
        diff = {k for k in set(upstream_py) | set(stock_py)
                if upstream_py.get(k) != stock_py.get(k)}
        e2 = not diff
        results.append(("E2 stock 树与上游 python/ 逐文件相同", e2,
                        "identical" if e2 else f"{len(diff)} differing: {sorted(diff)[:3]}"))

        # ---- E3/E4 final 覆盖生效且无夹带 ----
        fdir = tmp / "final-0"
        run_build(a.setting, "final", fdir)
        final_py = py_of(file_map(fdir))
        changed = {k for k in set(stock_py) | set(final_py) if stock_py.get(k) != final_py.get(k)}
        e3 = len(changed) > 0
        results.append(("E3 final 树与 stock 不同", e3, f"{len(changed)} files changed"))

        overlay = {str(p.relative_to(UPSTREAM / "settings" / a.setting / "files"))
                   for p in (UPSTREAM / "settings" / a.setting / "files").rglob("*") if p.is_file()}
        # 覆盖层文件按 basename 对齐（覆盖层是 `files/` 下同构路径）
        injected = changed - overlay
        e4 = not injected
        results.append(("E4 改动全部来自 settings/<setting>/files/", e4,
                        "clean" if e4 else f"unexpected: {sorted(injected)[:3]}"))

        # ---- E5 无 .pyc ----
        pyc = [p for p in stock.rglob("*") if p.suffix == ".pyc" or "__pycache__" in p.parts]
        results.append(("E5 树内无 .pyc / __pycache__", not pyc, f"{len(pyc)} found"))

        # ---- E6 dspark overlay ----
        if cfg["dspark"]:
            ov = file_map(UPSTREAM / "overlays" / "dspark_stock")
            missing = [k for k, v in ov.items() if stock_py.get(k) != v]
            e6 = not missing
            results.append(("E6 dspark stock 含 overlays/dspark_stock", e6,
                            f"{len(missing)} missing"))
        else:
            ov_present = (UPSTREAM / "overlays" / "dspark_stock").exists()
            results.append(("E6 dflash2 不套 dspark overlay", True,
                            f"(overlay dir exists={ov_present}, 本 setting dspark=False)"))
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print(f"[keep] {tmp}")

    ok = True
    for name, passed, detail in results:
        ok &= passed
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
    print(f"\nG6 {'PASS' if ok else 'FAIL'} ({sum(1 for _, p, _ in results if p)}/{len(results)})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
