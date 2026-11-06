"""exact replay：录 draft 候选与 target 输出，离线判定接受/拒绝。

用途：
  1. token forcing 需要「同一输入下 stock 与 patched 的逐 token 输出」，不能重跑采样；
  2. 故障注入回归（复现 Fig 4）需要一致、可复算的判定路径。

两条入口：
  - `run_tokens()` 跑真实引擎，返回最终 token 流 —— 用于 forcing 比对；
  - `record()` 逐步留痕，`replay_tokens()` 纯 CPU 复原 —— 用于故障注入。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict

import torch

from .engine import Options, SpecEngine, build_weights


@dataclass
class Step:
    pos: int
    candidates: list[int]
    target_pred: list[int]
    accepted: int


def run_tokens(prompt: list[int], max_new: int, opts: Options,
               device: str = "cuda:0", seed: int = 1) -> dict:
    """跑一次真实生成，返回 token 流 + 统计。权重固定 seed，机制之间可比。"""
    eng = SpecEngine(opts, device=device, weights=build_weights(Options(), seed=seed, draft_layers=opts.draft_layers))
    tokens, res = eng.generate(prompt, max_new)
    return {"tokens": tokens, "tau": res.tau, "tokens_per_s": res.tokens_per_s,
            "verify_forwards": eng.stats.verify_forwards,
            "draft_forwards": eng.stats.draft_forwards}


def record(prompt: list[int], max_new: int, opts: Options, device: str = "cuda:0",
           seed: int = 1) -> dict:
    """跑一次生成，逐步记录。返回可直接 json 化的结构。"""
    eng = SpecEngine(opts, device=device, weights=build_weights(Options(), seed=seed, draft_layers=opts.draft_layers))
    steps: list[Step] = []
    idx = torch.tensor([prompt], device=device, dtype=torch.long)
    cur = list(prompt)

    with torch.no_grad():
        for pos in range(max_new // max(opts.tree_depth, 1) + 1):
            if len(cur) - len(prompt) >= max_new:
                break
            cand = eng._propose(idx, min(opts.tree_depth, max_new - (len(cur) - len(prompt))))
            full = torch.cat([idx, torch.tensor([cand], device=device)], dim=1)
            logits = eng.target(full)[0]
            base = idx.shape[1] - 1
            preds = [int(logits[base + i].argmax().item()) for i in range(len(cand))]
            acc = 0
            for a, b in zip(cand, preds):
                if a != b:
                    break
                acc += 1
            steps.append(Step(pos, cand, preds, acc))
            new = cand[:acc] + [preds[acc]] if acc < len(cand) else list(cand)
            cur.extend(new)
            idx = torch.tensor([cur], device=device, dtype=torch.long)

    return {"prompt": prompt, "options": asdict(opts), "steps": [asdict(s) for s in steps]}


def replay_tokens(rec: dict) -> list[int]:
    """从记录复原最终 token 序列 —— 不碰 GPU，纯确定性。"""
    out = list(rec["prompt"])
    for s in rec["steps"]:
        acc = s["accepted"]
        out.extend(s["candidates"][:acc])
        if acc < len(s["candidates"]):
            out.append(s["target_pred"][acc])
    return out


def inject_fault(rec: dict, every: int = 3, vocab: int = 4096, mode: str = "pred") -> dict:
    """复现 Fig 4 的故障注入。

    mode="pred"   ：把拒绝位置的 target 预测换成另一个 token —— **长度不变**，
                    序列仍然合法、仍然通顺，只是逐 token 不等价。这是论文
                    「任务精度发现不了」的真实形态。
    mode="accept" ：把 accepted 减 1 —— 候选链少接受一个，输出长度随之变化。
    """
    if mode not in ("pred", "accept"):
        raise ValueError(f"未知 mode: {mode}")
    bad = json.loads(json.dumps(rec))
    for s in bad["steps"]:
        if s["pos"] % every:
            continue
        acc = s["accepted"]
        if mode == "pred" and acc < len(s["candidates"]):
            old = s["target_pred"][acc]
            # 偏移 1 个 id，保证是合法 token 且与原来不同
            s["target_pred"][acc] = (old + 1) % vocab
        elif mode == "accept" and acc > 0:
            s["accepted"] = acc - 1
    return bad
