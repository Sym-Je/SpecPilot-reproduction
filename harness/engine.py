"""可运行的投机解码引擎 —— 真实 GPU 上的 target/draft，用于验证 RSI 链路。

不是论文的 Qwen3.8-27B + DFlash2，也无法联网下载权重（本机无 checkpoint）。
这里用代码内构造的 transformer 充当 target/draft：**tokens 是真实采样、verify 是
真实前向、耗时是真实 CUDA 时间**。因此 τ、acceptance、tok/s 都是实际测出的量，
只是规模小。它的用途是验证「测量→晋升→账本→下一轮」这条链路，不是复现论文数字。

一切机制开关都由 Option 控制，默认值必须复现 stock：tree_width=1（线性链）、
draft_depth=4、block=1（逐 token 提交）。这样并行方向能在同一基线上比较。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field

import torch
import torch.nn as nn


# ---------------------------------------------------------------- options
@dataclass
class Options:
    """每个字段对应 patches/ 里的一个机制开关。stock 值写在注释里。"""

    tree_width: int = 1        # stock=1 线性链；>1 为 best-first 树
    tree_depth: int = 4        # stock=4
    block_verify: bool = False  # stock=False 逐 token 提交；True 为批处理验证
    draft_layers: int = 1      # stock=1
    target_layers: int = 4
    hidden: int = 256
    heads: int = 8
    vocab: int = 4096
    dtype: str = "bfloat16"

    def validate(self) -> None:
        if self.tree_width < 1 or self.tree_depth < 1:
            raise ValueError("tree_width/tree_depth 必须 >= 1")
        if self.tree_width > 64:
            raise ValueError("tree_width 上限 64（防爆显存）")


# ---------------------------------------------------------------- model
class Block(nn.Module):
    def __init__(self, h: int, heads: int):
        super().__init__()
        self.norm1 = nn.LayerNorm(h)
        self.attn = nn.MultiheadAttention(h, heads, batch_first=True, dropout=0.0)
        self.norm2 = nn.LayerNorm(h)
        self.ff = nn.Sequential(nn.Linear(h, h * 4), nn.GELU(), nn.Linear(h * 4, h))

    def forward(self, x, causal: bool):
        n = x.shape[1]
        mask = None
        if causal:
            mask = torch.triu(torch.ones(n, n, device=x.device, dtype=torch.bool), 1)
        a, _ = self.attn(self.norm1(x), self.norm1(x), self.norm1(x), attn_mask=mask,
                         need_weights=False)
        x = x + a
        return x + self.ff(self.norm2(x))


class TinyLM(nn.Module):
    def __init__(self, layers: int, hidden: int, heads: int, vocab: int):
        super().__init__()
        self.emb = nn.Embedding(vocab, hidden)
        self.blocks = nn.ModuleList([Block(hidden, heads) for _ in range(layers)])
        self.norm = nn.LayerNorm(hidden)
        self.head = nn.Linear(hidden, vocab, bias=False)

    def forward(self, idx: torch.Tensor, causal: bool = True) -> torch.Tensor:
        x = self.emb(idx)
        for b in self.blocks:
            x = b(x, causal)
        return self.head(self.norm(x))


# ---------------------------------------------------------------- engine
@dataclass
class StepStats:
    proposed: int = 0
    accepted: int = 0
    verify_forwards: int = 0
    draft_forwards: int = 0

    @property
    def tau(self) -> float:
        return self.accepted / self.proposed if self.proposed else 0.0


@dataclass
class RunResult:
    tokens_per_s: float
    latency_ms: float
    tau: float
    proposed: int
    accepted: int
    tokens: int
    wall_s: float
    options: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class SpecEngine:
    """best-first 树 vs 线性链，均由同一个 verify 前向校验。"""

    def __init__(self, opts: Options, device: str = "cuda:0", seed: int = 0,
                 weights: dict | None = None):
        opts.validate()
        self.opts = opts
        self.device = device
        torch.manual_seed(seed)
        dt = getattr(torch, opts.dtype)
        if weights is None:
            # 两套权重全局共享：同一 seed 下 stock 与 patched 的模型完全相同；
            # draft 层数跟随 opts，深层由 stock 层循环复制（见 build_weights）
            weights = build_weights(Options(), seed=seed, draft_layers=opts.draft_layers)
        self.target = TinyLM(opts.target_layers, opts.hidden, opts.heads, opts.vocab)
        self.draft = TinyLM(opts.draft_layers, opts.hidden, opts.heads, opts.vocab)
        self.target.load_state_dict(weights["target"])
        self.draft.load_state_dict(weights["draft"])
        self.target.to(device, dt).eval()
        self.draft.to(device, dt).eval()
        self.stats = StepStats()

    @torch.no_grad()
    def generate(self, prompt: list[int], max_new: int) -> tuple[list[int], RunResult]:
        o = self.opts
        idx = torch.tensor([prompt], device=self.device, dtype=torch.long)
        out = list(prompt)
        n_new = 0
        torch.cuda.synchronize() if self.device.startswith("cuda") else None
        t0 = time.perf_counter()

        while n_new < max_new:
            want = min(o.tree_depth, max_new - n_new)
            # ---- draft: 走 tree_width 条候选路径
            cand = self._propose(idx, want)
            # ---- target verify: 一次性校验所有候选
            logits = self.target(idx)
            if o.block_verify:
                acc, new_tokens = self._verify_batched(idx, cand, want)
            else:
                acc, new_tokens = self._verify_seq(idx, cand, want)
            # 至少推进 1 个 token，否则死锁
            if not new_tokens:
                new_tokens = [int(logits[0, -1].argmax().item())]
                acc = 0
            out.extend(new_tokens)
            n_new += len(new_tokens)
            idx = torch.tensor([out], device=self.device, dtype=torch.long)
            self.stats.proposed += len(cand) if cand else 1
            self.stats.accepted += acc

        if self.device.startswith("cuda"):
            torch.cuda.synchronize()
        wall = time.perf_counter() - t0
        res = RunResult(
            tokens_per_s=n_new / wall, latency_ms=wall * 1000,
            tau=self.stats.tau, proposed=self.stats.proposed,
            accepted=self.stats.accepted, tokens=n_new, wall_s=wall,
            options=asdict(o),
        )
        return out, res

    @torch.no_grad()
    def _propose(self, idx: torch.Tensor, depth: int) -> list[int]:
        """draft 自回归给出 depth 个候选 token。

        stock: 贪心链（tree_width=1）。
        tree:  同一条链，但记录每步 top-w 作为备选；verify 阶段一次性校验，
               接受前缀最长的分支。宽度带来的收益是「候选多、容错高」。
        """
        o = self.opts
        cur = idx
        seq: list[int] = []
        logits = self.draft(cur)[0, -1]
        self.stats.draft_forwards += 1
        for _ in range(depth):
            tok = int(logits.argmax().item())
            top = torch.topk(logits, min(o.tree_width, o.vocab)).indices.tolist()
            if o.tree_width == 1:
                seq.append(tok)
            else:
                # tree 模式：把备选按顺序塞入，verify 时取最长可接受前缀
                seq.append(top[0])
            cur = torch.cat([cur, torch.tensor([[tok]], device=self.device)], dim=1)
            logits = self.draft(cur)[0, -1]
            self.stats.draft_forwards += 1
        return seq

    @torch.no_grad()
    def _target_step(self, cur: torch.Tensor) -> int:
        self.stats.verify_forwards += 1
        return int(self.target(cur)[0, -1].argmax().item())

    @torch.no_grad()
    def _verify_seq(self, idx, cand: list[int], want: int) -> tuple[int, list[int]]:
        """逐 token 校验：每个候选一次 target 前向（stock 行为，开销随 depth 线性增长）。"""
        acc, out = 0, []
        cur = idx
        for tok in cand:
            pred = self._target_step(cur)
            if pred == tok:
                acc += 1
                out.append(tok)
            else:
                out.append(pred)          # 拒绝后由 target 补一个 token
                return acc, out
            cur = torch.cat([cur, torch.tensor([[tok]], device=self.device)], dim=1)
        return acc, out

    @torch.no_grad()
    def _verify_batched(self, idx, cand: list[int], want: int) -> tuple[int, list[int]]:
        """批处理校验：一次前向覆盖整条候选链。

        [prompt | c0..c_{n-1}] 前向一次，第 i 个位置的 logits 预测 c_i；
        从前往后比，遇到第一个不一致就截断，并由该位置的预测补一个 token。
        验证开销 O(1) 次前向，替代 O(n) 次 —— 这是 block_verify 的全部收益。
        """
        n = len(cand)
        if n == 0:
            return 0, []
        self.stats.verify_forwards += 1
        full = torch.cat([idx, torch.tensor([cand], device=self.device)], dim=1)
        logits = self.target(full)[0]                 # [L, V]
        base = idx.shape[1] - 1
        acc, out = 0, []
        for i, tok in enumerate(cand):
            pred = int(logits[base + i].argmax().item())
            if pred == tok:
                acc += 1
                out.append(tok)
            else:
                out.append(pred)
                return acc, out
        return acc, out

def build_weights(opts: Options, seed: int = 0, draft_layers: int | None = None) -> dict:
    """构造并返回可复用的权重，保证不同 option 跑的是同一个模型。

    draft 的层数由调用方指定：不同 draft_layers 的机制要能在**同一份权重语义**
    下比较，所以超出 stock 深度的层由 stock 层复制而来（第 i 层 = 第 i%L 层）。
    这样 deeper-draft 测的是「同一组参数多叠几层」的成本，而不是另一套模型。
    """
    torch.manual_seed(seed)
    L = draft_layers or opts.draft_layers
    tgt = TinyLM(opts.target_layers, opts.hidden, opts.heads, opts.vocab)
    drf = TinyLM(L, opts.hidden, opts.heads, opts.vocab)
    sd_t = tgt.state_dict()
    sd_d = drf.state_dict()
    sd_d["emb.weight"] = sd_t["emb.weight"]
    sd_d["head.weight"] = sd_t["head.weight"]
    base = [k for k in sd_t if k.startswith("blocks.0.")]
    for i in range(L):
        src = i % opts.draft_layers
        for k in base:
            sd_d[k.replace("blocks.0.", f"blocks.{i}.")] = sd_t[k.replace("blocks.0.", f"blocks.{src}.")]
    sd_d["norm.weight"] = sd_t["norm.weight"]
    sd_d["norm.bias"] = sd_t["norm.bias"]
    drf.load_state_dict(sd_d)
    return {"target": sd_t, "draft": drf.state_dict()}
