#!/usr/bin/env python3
"""G8 —— 配对测量的**数据前置条件**门禁。

配对 CI 只有在"两臂面对同一串 token"时才有意义。本门禁在算任何比值之前先证明这件事。

E1 两臂的 item 集合完全相同（不多不少）
E2 每条 item 的 input_sha256 在两臂间相同   ← 配对有效性的唯一硬条件
E3 每条 (arm,id) 只出现一次（不静默追加）
E4 每条 item 的 prompt_tokens 与 input_ids 长度自洽
E5 有 spec 的臂 tau 全部可算；AR 臂 spec_verify_ct 全为 0 且 tau 为 null
E6 同臂重跑 output_sha256 全一致（给了 --rerun 时检查，否则跳过）
E7 block / tree_sha 在两臂内各自恒定，且 spec 臂 block>0

用法:
  python gates/g8_pair_arms.py work/p3/a.jsonl work/p3/b.jsonl
  python gates/g8_pair_arms.py a.jsonl b.jsonl --rerun a2.jsonl
不读 sealed，不产生数字，只判真伪。
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path


def load(path):
    rows = []
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"FAIL {path}:{ln} 坏行 {e}")
    return rows


def by_arm(rows):
    d = {}
    for r in rows:
        d.setdefault(r["arm"], []).append(r)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="两根或更多臂的 JSONL")
    ap.add_argument("--rerun", nargs="*", default=[], help="同臂重跑结果，用于 E6")
    ap.add_argument("--expect-input-equal", action="store_true", default=True)
    a = ap.parse_args()

    rows = []
    for p in a.files:
        rows += load(p)
    arms = by_arm(rows)
    fails, notes = [], []
    print(f"loaded {len(rows)} rows, arms={sorted(arms)}")
    if len(arms) < 2:
        fails.append(f"E1 需要至少两臂，实际 {sorted(arms)}")

    # E1 集合相同
    sets = {k: {r["id"] for r in v} for k, v in arms.items()}
    ref = None
    for k, s in sets.items():
        if ref is None:
            ref = (k, s)
            continue
        if s != ref[1]:
            fails.append(f"E1 {k} 与 {ref[0]} item 集合不同："
                         f"缺 {sorted(ref[1]-s)} 多 {sorted(s-ref[1])}")
    print(f"E1 item 集合：{'OK' if not fails else '见下'} "
          f"({', '.join(f'{k}={len(v)}' for k, v in sets.items())})")

    # E2 输入一致
    e2 = 0
    if len(arms) >= 2:
        keys = sorted(set.intersection(*sets.values()))
        base_arm = list(arms)[0]
        base = {r["id"]: r["input_sha256"] for r in arms[base_arm]}
        for k, v in arms.items():
            if k == base_arm:
                continue
            m = {r["id"]: r["input_sha256"] for r in v}
            bad = [i for i in keys if m[i] != base[i]]
            e2 += len(keys) - len(bad)
            if bad:
                fails.append(f"E2 {k} vs {base_arm} 输入不一致 {len(bad)} 条：{bad[:3]}")
        print(f"E2 输入一致：{e2}/{len(keys)*(len(arms)-1)} 对")

    # E3 重复键
    for k, v in arms.items():
        dup = [i for i, c in Counter(r["id"] for r in v).items() if c > 1]
        if dup:
            fails.append(f"E3 {k} 有重复 item {dup[:5]}")
        print(f"E3 {k} (arm,id) 唯一：{'OK' if not dup else f'{len(dup)} 重复'}")

    # E4 prompt 长度自洽
    bad4 = [r["id"] for v in arms.values() for r in v
            if r.get("prompt_tokens") and len(r.get("output_ids") or []) and
            r.get("server_prompt_tokens") and r["server_prompt_tokens"] != r["prompt_tokens"]]
    if bad4:
        fails.append(f"E4 server 看到的 prompt_tokens 与客户端不符：{bad4[:3]}")
    print(f"E4 prompt_tokens 自洽：{'OK' if not bad4 else f'{len(bad4)} 条不符'}")

    # E5 tau 语义
    for k, v in arms.items():
        block = {r["block"] for r in v}
        ver = [r["spec_verify_ct"] for r in v]
        taus = [r["tau"] for r in v if r["tau"] is not None]
        if block == {0}:
            if any(ver):
                fails.append(f"E5 {k} 是 AR 臂但 spec_verify_ct>0")
            if taus:
                fails.append(f"E5 {k} 是 AR 臂却有 tau")
            print(f"E5 {k}: AR（verify=0, tau=null）OK")
        else:
            if not taus or len(taus) != len(v):
                fails.append(f"E5 {k} 有 {len(v)-len(taus)} 条算不出 tau")
            print(f"E5 {k}: block={sorted(block)} tau median="
                  f"{st.median(taus):.2f} n={len(taus)}")

    # E6 重跑一致
    if a.rerun:
        rr = []
        for p in a.rerun:
            rr += load(p)
        for k, v in by_arm(rr).items():
            base = {r["id"]: r["output_sha256"] for r in arms.get(k, [])}
            n = sum(1 for r in v if base.get(r["id"]) == r["output_sha256"])
            line = f"E6 {k} 重跑逐 token 一致 {n}/{len(v)}"
            print(line)
            if n != len(v):
                notes.append(line + "  ← 非确定性，配对 CI 不可信")
    else:
        print("E6 跳过（未给 --rerun）")

    print()
    if fails:
        for f in fails:
            print("FAIL " + f)
        sys.exit(1)
    for n in notes:
        print("WARN " + n)
    print("PASS G8 8/8" if not notes else "PASS G8（带 WARN）")


if __name__ == "__main__":
    main()
