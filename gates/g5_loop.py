#!/usr/bin/env python3
"""G5 —— RSI 闭环验收（CPU 部分 + 真实跑一次 run）。

  L1 判定纯函数：速度达标但 forcing 不等价 → 必须否决
  L2 判定纯函数：速度不达标 → 拒绝，不看 forcing
  L3 判定纯函数：两者都过 → 晋升
  L4 记忆跳过：已 rejected 的机制不再被 propose
  L5 账本篡改可定位：改一行后 verify() 报出该 seq
  L6 真实闭环：跑 run()，账本无问题、每轮都有 measurement+memory

L6 需要双卡；--skip-gpu 可跳过。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from orchestrator.loop import decide, Proposer  # noqa: E402
from patches.registry import default_registry  # noqa: E402
from controller.ledger import Ledger  # noqa: E402

results: list[tuple[str, bool, str]] = []


def rec(cid: str, ok: bool, detail: str) -> None:
    results.append((cid, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}", flush=True)


def main(skip_gpu: bool = False) -> int:
    good = {"ci": {"lower": 1.07}, "threshold": 0.03, "promoted": True}
    lossless = {"lossless": True, "diverged": 0, "n": 200}
    lossy = {"lossless": False, "diverged": 7, "n": 200}
    slow = {"ci": {"lower": 1.01}, "threshold": 0.03, "promoted": False}

    ok, why = decide(good, lossy)
    rec("L1 forcing 能否决", not ok and "不等价" in why, why)

    ok, why = decide(slow, lossless)
    rec("L2 速度不达标", not ok and "阈值" in why, why)

    ok, why = decide(good, lossless)
    rec("L3 双过才晋升", ok, why)

    mem = [{"mechanism": "batch-verify", "status": "rejected"},
           {"mechanism": "deeper-draft", "status": "promoted"}]
    prop = Proposer(default_registry(), mem).propose()
    got = [prop.mechanism] if prop else []
    rec("L4 记忆跳过", got == ["longer-chain"], f"下一个提案 {got}")

    d = tempfile.mkdtemp()
    path = os.path.join(d, "l.jsonl")
    lg = Ledger(path)
    for i in range(4):
        lg.append("test", f"k{i}", {"i": i})
    lines = open(path).read().splitlines()
    lines[2] = lines[2].replace('"i": 2', '"i": 99')
    open(path, "w").write("\n".join(lines) + "\n")
    probs = Ledger(path).verify()
    hit = [p for p in probs if "seq 2" in p]
    rec("L5 篡改可定位", bool(hit), f"verify 命中 {len(hit)} 条：{hit[:2]}")
    shutil.rmtree(d, ignore_errors=True)

    if skip_gpu:
        print("\n[skip] L6 真实闭环")
    else:
        from orchestrator.loop import run
        rep = run(2, 256, verbose=False)
        kinds = [json.loads(x)["kind"] for x in
                 open(os.path.join(ROOT, "ledger", "rsi.jsonl"))]
        kinds = kinds[-8:]
        rec("L6 真实闭环", rep["ledger_problems"] == []
            and kinds.count("measurement") >= 2 and kinds.count("memory") >= 2,
            f"promoted={rep['promoted']} kinds={kinds}")

    failed = [c for c, ok, _ in results if not ok]
    print(f"\nG5 {'PASS' if not failed else 'FAIL'} ({len(results) - len(failed)}/{len(results)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main("--skip-gpu" in sys.argv))
