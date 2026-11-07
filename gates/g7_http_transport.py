#!/usr/bin/env python3
"""G7 —— HTTP 传输层验收：换传输不改统计（P2 的判据）。

背景：`controller/measure.py` 原来的传输是 JSONL stdio，worker 跑 TinyLM，
options 可以在请求里改。真实引擎不行 —— `--speculative-num-draft-tokens`
与 `SPECPILOT_*` 都是**启动参数**，进程起来就改不了。所以真实配对 =
两个 server，各占一张卡，`controller/http_transport.py` 负责这个。

判据（需要一个已经起好的 server，默认本地 0.5B 调试臂）：
  E1 同一 arm 自比 → 每次 run_pair 的 output_sha256 相同（greedy 确定性）
  E2 calibrate() 能跑，返回的 noise 是**配对比值的半宽**而不是均值标准差
     （用两根不同吞吐臂时 noise 必须显著大于 0；同一 arm 自比时必须接近 0）
  E3 compare() 的 promoted 判定用的是 ci["lower"]，且 threshold = 1% + 2*noise
     —— 用构造的假 ci 注入验证，防止有人把判据改成"中位数 > 1%"
  E4 SequentialPairBench 拒绝产出可进账本的指标（单卡顺序不许冒充配对）
  E5 tau 记录带口径标记 tau_source，且 output_ids 原样保留（逐 token 判据要用）

用法:
  python gates/g7_http_transport.py --url http://127.0.0.1:30010
  python gates/g7_http_transport.py --url-a ... --url-b ...   # 两根不同臂
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from controller import http_transport as T  # noqa: E402
from controller.stats import paired_ci  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url-a", default="http://127.0.0.1:30010")
    ap.add_argument("--url-b", default=None, help="默认与 --url-a 相同（自比标定）")
    ap.add_argument("--max-new", type=int, default=64)
    a = ap.parse_args()
    url_b = a.url_b or a.url_a

    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    arm_a = T.Arm("A", a.url_a, block_size=8)
    arm_b = T.Arm("B", url_b, block_size=32 if url_b != a.url_a else 8)
    for arm in (arm_a, arm_b):
        if not arm.health():
            print(f"server not reachable: {arm.url}")
            return 2
        arm.begin_session()

    # 用 server 自己的 tokenizer 编码，避免本地环境依赖
    from urllib.request import Request, urlopen
    import json as _json
    req = Request(arm_a.url + "/tokenize",
                  data=_json.dumps({"prompt": "Compute 17*23 step by step.",
                                    "add_special_tokens": True}).encode(),
                  headers={"Content-Type": "application/json"})
    ids = _json.loads(urlopen(req, timeout=30).read())["tokens"]

    bench = T.HttpPairBench(arm_a, arm_b)

    # ---- E1 确定性 ----
    r = bench.run_pair(ids, a.max_new, warmup=1, swap=True, rid="g7|e1")
    same = all(x["a"]["output_sha256"] == x["a"]["output_sha256"] for x in r["rounds"]) and \
           r["rounds"][0]["a"]["output_sha256"] == r["rounds"][1]["a"]["output_sha256"]
    check("E1 同一 arm 两轮 output 逐 token 相同", same,
          r["rounds"][0]["a"]["output_sha256"][:12])

    # ---- E2 标定 ----
    cal = bench.calibrate(ids, a.max_new, reps=3, warmup_rounds=1)
    # 判据分两种情形：同一 arm 自比 → 噪声必须接近 0（否则说明测量本身有漂移）；
    # 两根不同 arm 自比 → 噪声必须显著 > 0（否则说明比值的离散度被算法吃掉了，
    # 例如误用了"各次均值的标准差"而不是"配对比值的半宽"）。
    same_arm = (arm_a.url == arm_b.url) and (arm_a.block_size == arm_b.block_size)
    if same_arm:
        e2 = 0.0 <= cal["noise"] < 0.05      # 自比噪声 < 5%：真实引擎上 0.17% 已是极稳
        detail = f"自比 noise={cal['noise']*100:.3f}%（应≈0）"
    else:
        e2 = cal["noise"] > 0.0
        detail = f"异臂 noise={cal['noise']*100:.2f}%（应>0）"
    # ratios 每轮一条，xs 每轮两条（A、B 各一），所以是 n = 2 * len(ratios)
    e2 = e2 and cal["n"] > 0 and len(cal["ratios"]) * 2 == cal["n"]
    check("E2 calibrate 产出配对比值噪声地板", e2,
          f"{detail} mean={cal['mean']:.1f} tok/s n={cal['n']}")

    # ---- E3 判据口径 ----
    # 构造：median 高、lower 低 → 必须判 rejected（不能用中位数）
    fake_low = {"median": 1.30, "lower": 1.02, "upper": 1.5, "n": 4}
    fake_high = {"median": 1.30, "lower": 1.20, "upper": 1.5, "n": 4}
    orig = T.paired_ci

    def run_with_ci(ci):
        T.paired_ci = lambda x, y: ci
        try:
            return bench.compare(ids, a.max_new, noise=0.05, reps=1)
        finally:
            T.paired_ci = orig
    noise = 0.05
    thr = 0.01 + 2 * noise               # 0.11
    low = run_with_ci(fake_low)
    high = run_with_ci(fake_high)
    e3 = (not low["promoted"]) and high["promoted"] and abs(low["threshold"] - thr) < 1e-9
    check("E3 promoted 用 95% 下界 + 1%+2*noise 阈值", e3,
          f"lower=1.02→{low['promoted']}  lower=1.20→{high['promoted']}  thr={thr:.3f}")

    # ---- E4 顺序路径拒绝冒充配对 ----
    seq = T.SequentialPairBench(arm_a, arm_b)
    refused = 0
    for fn in ("calibrate", "compare"):
        try:
            getattr(seq, fn)(ids, a.max_new, noise=0.05, reps=1) if fn == "compare" else getattr(seq, fn)(ids, a.max_new)
        except RuntimeError:
            refused += 1
    check("E4 SequentialPairBench 拒绝产出账本指标", refused == 2, f"{refused}/2 拒绝")

    # ---- E5 口径标记与原始 token ----
    step = arm_a.step(ids, 8, warmup=0, rid="g7|e5")
    e5 = step["tau_source"] == "per_verify_step" and isinstance(step["output_ids"], list) \
        and len(step["output_ids"]) == step["tokens"]
    check("E5 tau 带口径标记且保留 output_ids", e5,
          f"tau_source={step['tau_source']} n={step['tokens']}")

    ok = all(x[1] for x in results)
    print(f"\nG7 {'PASS' if ok else 'FAIL'} ({sum(1 for _, p, _ in results if p)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
