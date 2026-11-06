"""RSI 主循环：propose → gate → measure → judge → ledger → memory → 下一轮。

与论文的对应关系：
  - 每轮先让 master 定方向，direction 出提案（这里是确定性策略，见 Proposer）
  - controller 独立配对测量（agent 无法干预）
  - 判定用 1% + 2x 噪声 的 95% 下界，附加 token forcing 无损检查
  - 结果写入 append-only 账本与结构化记忆
  - 下一轮读取记忆，避免重复同一个已失败的方向

forcing 的方向性（重要）：它只能**否决**晋升，不能作为晋升的证据。
速度涨了但 token 流不等价 → 拒绝，理由写进账本。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from controller.ledger import Ledger  # noqa: E402
from controller.measure import PairBench  # noqa: E402
from controller.token_force import judge_forcing  # noqa: E402
from costmodel.floors import H100  # noqa: E402
from harness.engine import Options  # noqa: E402
from harness.replay import run_tokens  # noqa: E402
from patches.registry import default_registry  # noqa: E402

# 本仓库的 stock 是确定性 exact replay（同一 seed、同一贪心），逐 token 完全一致。
# 论文的 0.72% 是 27B 模型 + 采样解码下的经验值，不能套用。
BASE_RATE = 0.0


@dataclass
class Proposal:
    mechanism: str
    option: str
    stock: object
    candidate: object
    factor: str
    hypothesis: str


@dataclass
class RoundOutcome:
    round: int
    proposal: dict
    measurement: dict
    forcing: dict
    promoted: bool
    reason: str


class Proposer:
    """确定性 proposer：按记忆跳过已失败的机制，按因子优先级排序。

    真实系统里这一步是 LLM（agents/prompts.py 的 direction 角色）；
    这里保证「无 LLM 也能跑完整链路」，接口与 LLM proposer 一致。
    """

    def __init__(self, registry, memory: list[dict]):
        self.registry = registry
        self.tried = {m["mechanism"] for m in memory
                      if m.get("status") in ("rejected", "regressed")}
        self.promoted = {m["mechanism"] for m in memory if m.get("status") == "promoted"}

    def propose(self, focus: str | None = None) -> Proposal | None:
        cands = [m for m in self.registry.items
                 if m.name not in self.tried and m.name not in self.promoted]
        if focus:
            cands.sort(key=lambda m: (m.factor != focus, m.name))
        if not cands:
            return None
        m = cands[0]
        return Proposal(m.name, m.option, m.stock, m.candidate, m.factor, m.hypothesis)


def decide(meas: dict, forcing: dict) -> tuple[bool, str]:
    """晋升判定 = 速度判据 AND token 流等价。forcing 只能否决，不能作为证据。"""
    speed_ok = bool(meas["promoted"])
    if not speed_ok:
        return False, (f"95%LB={meas['ci']['lower']:.4f} <= 阈值 "
                       f"{1 + meas['threshold']:.4f}，拒绝")
    if not forcing["lossless"]:
        return False, (f"速度达标(95%LB={meas['ci']['lower']:.4f})但 token 流不等价 "
                       f"(分歧 {forcing['diverged']}/{forcing['n']})，拒绝")
    return True, (f"95%LB={meas['ci']['lower']:.4f} > 阈值 "
                  f"{1 + meas['threshold']:.4f} 且 forcing 无损，晋升")


def check_forcing(req: dict, base_opts: dict, cand_opts: dict, max_new: int,
                  n_samples: int = 2) -> dict:
    """对同一 prompt 跑 stock 与候选的 exact replay，逐 token 比对。"""
    opts_b = Options(**base_opts)
    opts_c = Options(**cand_opts)
    base, cand = [], []
    for i in range(n_samples):
        p = req["prompt"][: max(8, len(req["prompt"]) - i)]
        base.append(run_tokens(p, max_new, opts_b)["tokens"])
        cand.append(run_tokens(p, max_new, opts_c)["tokens"])
    r = judge_forcing(base, cand, base_rate=BASE_RATE)
    return r.to_dict()


def run(n_rounds: int = 3, max_new: int = 256, verbose: bool = True,
        focus: str | None = None) -> dict:
    ledger = Ledger(os.path.join(ROOT, "ledger", "rsi.jsonl"))
    memory_path = os.path.join(ROOT, "memory", "entries", "rsi.json")
    os.makedirs(os.path.dirname(memory_path), exist_ok=True)
    memory: list[dict] = json.load(open(memory_path)) if os.path.exists(memory_path) else []

    bench = PairBench()
    req = {"prompt": list(range(1, 33))}
    base_opts = {"tree_width": 1, "tree_depth": 4, "block_verify": False, "draft_layers": 1}

    try:
        calib = bench.calibrate(req, base_opts, max_new, reps=4, warm_rounds=1)
        noise = calib["noise"]
        ledger.append("gate", "noise-calibration",
                      {"noise": noise, "mean_tps": calib["mean"], "n": calib["n"],
                       "protocol": "stock-vs-stock paired, swap GPU, ratio dispersion"})
        if verbose:
            print(f"[calib] noise={noise * 100:.2f}% mean={calib['mean']:.1f} tok/s", flush=True)

        registry = default_registry()
        registry.assert_stock_defaults(base_opts)
        outcomes: list[RoundOutcome] = []

        for r in range(n_rounds):
            prop = Proposer(registry, memory).propose(focus)
            if prop is None:
                if verbose:
                    print("[loop] 没有未试过的机制，停止", flush=True)
                break
            cand_opts = dict(base_opts, **{prop.option: prop.candidate})
            if verbose:
                print(f"\n[round {r}] {prop.mechanism}: {prop.option} "
                      f"{prop.stock} -> {prop.candidate}", flush=True)

            meas = bench.compare(req, base_opts, cand_opts, max_new, noise, reps=3)
            forcing = check_forcing(req, base_opts, cand_opts, max_new, n_samples=2)
            speed_ok = bool(meas["promoted"])
            promoted, reason = decide(meas, forcing)

            ledger.append("measurement", prop.mechanism, {
                "proposal": asdict(prop), "ci": meas["ci"], "threshold": meas["threshold"],
                "noise": meas["noise"], "base_tps": meas["base_tps"],
                "cand_tps": meas["cand_tps"], "forcing": forcing,
                "speed_ok": speed_ok, "promoted": promoted, "reason": reason,
                "device": H100.name,
            })
            entry = {"mechanism": prop.mechanism, "factor": prop.factor,
                     "status": "promoted" if promoted else "rejected",
                     "gain": meas["gain"], "lower_gain": meas["lower_gain"],
                     "forcing_lossless": forcing["lossless"],
                     "hypothesis": prop.hypothesis, "round": r}
            memory.append(entry)
            ledger.append("memory", prop.mechanism, entry)
            outcomes.append(RoundOutcome(r, asdict(prop), meas, forcing, promoted, reason))

            if promoted:
                base_opts = cand_opts
                if verbose:
                    print(f"  → 晋升，新基线 {meas['cand_tps']} tok/s", flush=True)
            elif verbose:
                print(f"  → 拒绝: {reason}", flush=True)
            with open(memory_path, "w") as f:
                json.dump(memory, f, indent=2, ensure_ascii=False)

        report = {"noise": noise,
                  "outcomes": [asdict(o) for o in outcomes],
                  "promoted": [o.proposal["mechanism"] for o in outcomes if o.promoted],
                  "ledger_problems": ledger.verify()}
        ledger.append("summary", "rsi-run", {k: v for k, v in report.items()
                                             if k != "outcomes"})
        return report
    finally:
        bench.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--max-new", type=int, default=256)
    ap.add_argument("--focus", default=None)
    a = ap.parse_args()
    rep = run(a.rounds, a.max_new, focus=a.focus)
    print("\n=== summary ===")
    print(json.dumps({k: v for k, v in rep.items() if k != "outcomes"},
                     indent=2, ensure_ascii=False))
