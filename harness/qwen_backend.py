"""真实模型后端：Qwen3-8B 的 KV-cache 贪心解码 + 我们自己的 draft。

为什么不用 transformers 的 generate / SGLang：
  本仓库的测量口径要求「stock 与 patched 走**同一条**解码路径，只差一个 option」。
  上游仓库的 engine 是它们自己的 SGLang 分支，直接跑等于调用它们的实现，
  无法区分收益来自我们的机制还是它们的内核。这里从权重开始自己写前向，
  stock = 线性链投机解码（tree_width=1, block_verify=False），其余全是 option。

权重来源：ModelScope 的 Qwen/Qwen3-8B（与上游 Qwen3.8-27B 同架构族，只是小一号）。
本机无法下载 27B（HF 直连不通）；8B 的结论在**方向**上可比，绝对倍数不可比。
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, asdict

import torch
import torch.nn as nn
import torch.nn.functional as F


# ------------------------------------------------------------------ 配置
@dataclass
class QwenConfig:
    hidden: int = 4096
    layers: int = 36
    heads: int = 32
    kv_heads: int = 8
    head_dim: int = 128
    intermediate: int = 12288
    vocab: int = 151936
    eps: float = 1e-6
    rope_theta: float = 1_000_000.0

    @classmethod
    def from_dir(cls, d: str) -> "QwenConfig":
        cfg = json.load(open(os.path.join(d, "config.json")))
        return cls(
            hidden=cfg["hidden_size"], layers=cfg["num_hidden_layers"],
            heads=cfg["num_attention_heads"], kv_heads=cfg["num_key_value_heads"],
            head_dim=cfg.get("head_dim", cfg["hidden_size"] // cfg["num_attention_heads"]),
            intermediate=cfg["intermediate_size"], vocab=cfg["vocab_size"],
            eps=cfg.get("rms_norm_eps", 1e-6),
            rope_theta=cfg.get("rope_theta", 1_000_000.0),
        )


# ------------------------------------------------------------------ 组件
class RMSNorm(nn.Module):
    def __init__(self, h: int, eps: float):
        super().__init__()
        self.w = nn.Parameter(torch.ones(h))
        self.eps = eps

    def forward(self, x):
        d = x.dtype
        x = x.float()
        x = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        return (x.to(d) * self.w)


def rope_cache(seq_len: int, head_dim: int, theta: float, device, dtype):
    inv = 1.0 / (theta ** (torch.arange(0, head_dim, 2, device=device).float() / head_dim))
    t = torch.arange(seq_len, device=device).float()
    freqs = torch.outer(t, inv)
    emb = torch.cat([freqs, freqs], dim=-1)
    return emb.cos().to(dtype), emb.sin().to(dtype)


def apply_rope(x, cos, sin, offset: int = 0):
    # x: [B, H, T, D]
    T = x.shape[-2]
    c = cos[offset:offset + T].unsqueeze(0).unsqueeze(0)
    s = sin[offset:offset + T].unsqueeze(0).unsqueeze(0)
    d = x.shape[-1] // 2
    c, s = c[..., :d], s[..., :d]      # 只取前一半：interleaved→half-split 的等价形式
    x1, x2 = x[..., :d], x[..., d:]
    return torch.cat([x1 * c - x2 * s, x2 * c + x1 * s], dim=-1)


class Attention(nn.Module):
    def __init__(self, cfg: QwenConfig):
        super().__init__()
        self.cfg = cfg
        self.q = nn.Linear(cfg.hidden, cfg.heads * cfg.head_dim, bias=False)
        self.k = nn.Linear(cfg.hidden, cfg.kv_heads * cfg.head_dim, bias=False)
        self.v = nn.Linear(cfg.hidden, cfg.kv_heads * cfg.head_dim, bias=False)
        self.o = nn.Linear(cfg.heads * cfg.head_dim, cfg.hidden, bias=False)
        self.q_norm = RMSNorm(cfg.head_dim, cfg.eps)
        self.k_norm = RMSNorm(cfg.head_dim, cfg.eps)

    def forward(self, x, cos, sin, cache=None, offset=0):
        B, T, _ = x.shape
        c = self.cfg
        q = self.q(x).view(B, T, c.heads, c.head_dim).transpose(1, 2)
        k = self.k(x).view(B, T, c.kv_heads, c.head_dim).transpose(1, 2)
        v = self.v(x).view(B, T, c.kv_heads, c.head_dim).transpose(1, 2)
        q = self.q_norm(q)
        k = self.k_norm(k)
        q = apply_rope(q, cos, sin, offset)
        k = apply_rope(k, cos, sin, offset)
        if cache is not None:
            cache.append(k, v)
            k, v = cache.k, cache.v
        rep = c.heads // c.kv_heads
        k = k.repeat_interleave(rep, dim=1)
        v = v.repeat_interleave(rep, dim=1)
        S = k.shape[-2]
        # S>T 时 PyTorch 的 is_causal 是左上对齐：query i 只看到 key[0..i]。
        # 带 cache 分块时必须右下对齐（query i 看到 key[0..offset+i]），否则
        # 分块与整段前向不等价 —— 实测 logits 差 38，批验证直接失效。
        if T == 1 or S == T:
            out = F.scaled_dot_product_attention(q, k, v, is_causal=(T > 1))
        else:
            qpos = torch.arange(offset, offset + T, device=x.device)
            kpos = torch.arange(S, device=x.device)
            mask = kpos[None, :] <= qpos[:, None]
            out = F.scaled_dot_product_attention(q, k, v, attn_mask=mask,
                                                 is_causal=False)
        out = out.transpose(1, 2).reshape(B, T, c.heads * c.head_dim)
        return self.o(out)


class MLP(nn.Module):
    def __init__(self, cfg: QwenConfig):
        super().__init__()
        self.g = nn.Linear(cfg.hidden, cfg.intermediate, bias=False)
        self.u = nn.Linear(cfg.hidden, cfg.intermediate, bias=False)
        self.d = nn.Linear(cfg.intermediate, cfg.hidden, bias=False)

    def forward(self, x):
        return self.d(F.silu(self.g(x)) * self.u(x))


class Layer(nn.Module):
    def __init__(self, cfg: QwenConfig):
        super().__init__()
        self.n1 = RMSNorm(cfg.hidden, cfg.eps)
        self.attn = Attention(cfg)
        self.n2 = RMSNorm(cfg.hidden, cfg.eps)
        self.mlp = MLP(cfg)

    def forward(self, x, cos, sin, cache=None, offset=0):
        x = x + self.attn(self.n1(x), cos, sin, cache, offset)
        return x + self.mlp(self.n2(x))


class KV:
    """逐层 KV 缓存：预分配缓冲 + O(1) 追加 + 可回滚。

    不用 torch.cat 追加：2048 上下文下每写一个 token 都要拷一遍历史，
    36 层 × 8 head × 128 dim 的拷贝会直接吃掉整个解码时间。
    预分配后 append 是原地写，truncate 只把 n 往回拨（回滚未接受的候选）。
    """
    __slots__ = ("buf_k", "buf_v", "n")

    def __init__(self):
        self.buf_k = None
        self.buf_v = None
        self.n = 0

    def _grow(self, need, k, v):
        cap = max(need, 128)
        if self.buf_k is not None:
            cap = max(cap, self.buf_k.shape[2] * 2)
        bk = k.new_empty(k.shape[0], k.shape[1], cap, k.shape[3])
        bv = v.new_empty(v.shape[0], v.shape[1], cap, v.shape[3])
        if self.buf_k is not None and self.n:
            bk[:, :, :self.n] = self.buf_k[:, :, :self.n]
            bv[:, :, :self.n] = self.buf_v[:, :, :self.n]
        self.buf_k, self.buf_v = bk, bv

    def append(self, k, v):
        T = k.shape[2]
        need = self.n + T
        if self.buf_k is None or need > self.buf_k.shape[2]:
            self._grow(need, k, v)
        self.buf_k[:, :, self.n:need] = k
        self.buf_v[:, :, self.n:need] = v
        self.n = need

    @property
    def k(self):
        return self.buf_k[:, :, :self.n]

    @property
    def v(self):
        return self.buf_v[:, :, :self.n]

    def truncate(self, n):
        assert 0 <= n <= self.n, (n, self.n)
        self.n = n


class QwenModel(nn.Module):
    def __init__(self, cfg: QwenConfig, n_layers: int | None = None):
        super().__init__()
        self.cfg = cfg
        self.emb = nn.Embedding(cfg.vocab, cfg.hidden)
        self.layers = nn.ModuleList([Layer(cfg) for _ in range(n_layers or cfg.layers)])
        self.norm = RMSNorm(cfg.hidden, cfg.eps)
        self.lm_head = nn.Linear(cfg.hidden, cfg.vocab, bias=False)
        self._cos = self._sin = None

    def rope(self, n: int, device, dtype):
        if self._cos is None or self._cos.shape[0] < n:
            self._cos, self._sin = rope_cache(max(n, 4096), self.cfg.head_dim,
                                              self.cfg.rope_theta, device, dtype)
        return self._cos, self._sin

    def forward(self, ids, caches=None, offset: int | None = None, keep_top: int = 0):
        """ids: [B,T]；offset 默认取缓存已有长度（append-only 路径）。"""
        if offset is None:
            offset = caches[0].n if caches else 0
        cos, sin = self.rope(offset + ids.shape[1], ids.device, self.emb.weight.dtype)
        x = self.emb(ids)
        for i, l in enumerate(self.layers):
            x = l(x, cos, sin, caches[i] if caches else None, offset)
        x = self.norm(x)
        return self.lm_head(x) if keep_top <= 0 else top_logits(self.lm_head, x, keep_top)

    def logits_last(self, ids, caches=None, offset=None):
        return self.forward(ids, caches, offset)[:, -1, :]


def top_logits(head: nn.Linear, x, k: int):
    """只算 argmax + top-k 候选所属的行，省掉 [B,T,V] 的大张量。

    对 151936 的 vocab、T=32 的验证块，完整 logits 是 32x151936x4B ≈ 19MB，
    看着不大，但每步都要写一遍；这里只取最后一行（argmax）与预算好的前 k。
    """
    w = head.weight
    xl = x[:, -1, :]
    logits = xl @ w.t()
    top = torch.topk(logits, k, dim=-1).indices
    return logits, top


def load_checkpoint(model_dir: str, cfg: QwenConfig, device: str = "cuda:0",
                    dtype=torch.bfloat16, n_layers: int | None = None,
                    drop_layers: list[int] | None = None) -> QwenModel:
    """从 safetensors 直接装权重，不经过 transformers 的 modeling 代码。

    两处必须优化，否则每轮实验都要在加载上花 3 分钟：
      1. 分片并行读（GPFS 上串行读 5 个 3G 分片是纯等待）；
      2. 不走 load_state_dict —— 它先把整份 state_dict 拷进临时 dict 再逐键赋值，
         等于再拷 16G。这里直接按映射逐张量搬。
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from safetensors.torch import load_file

    t0 = time.perf_counter()
    idx = os.path.join(model_dir, "model.safetensors.index.json")
    if os.path.exists(idx):
        shards = sorted(set(json.load(open(idx))["weight_map"].values()))
    else:
        shards = sorted(f for f in os.listdir(model_dir) if f.endswith(".safetensors"))

    with ThreadPoolExecutor(max_workers=min(8, len(shards))) as ex:
        parts = list(ex.map(lambda s: load_file(os.path.join(model_dir, s), device="cpu"), shards))
    sd = {}
    for part in parts:
        sd.update(part)
    print(f"[load] {len(shards)} shards in {time.perf_counter() - t0:.1f}s", flush=True)

    m = QwenModel(cfg, n_layers)
    if drop_layers is None:
        drop_layers = list(range(len(m.layers)))
    mapping = {}
    for i in range(len(m.layers)):
        src = drop_layers[i]
        p = f"model.layers.{src}."
        mapping.update({
            f"layers.{i}.n1.w": p + "input_layernorm.weight",
            f"layers.{i}.attn.q.weight": p + "self_attn.q_proj.weight",
            f"layers.{i}.attn.k.weight": p + "self_attn.k_proj.weight",
            f"layers.{i}.attn.v.weight": p + "self_attn.v_proj.weight",
            f"layers.{i}.attn.o.weight": p + "self_attn.o_proj.weight",
            f"layers.{i}.attn.q_norm.w": p + "self_attn.q_norm.weight",
            f"layers.{i}.attn.k_norm.w": p + "self_attn.k_norm.weight",
            f"layers.{i}.n2.w": p + "post_attention_layernorm.weight",
            f"layers.{i}.mlp.g.weight": p + "mlp.gate_proj.weight",
            f"layers.{i}.mlp.u.weight": p + "mlp.up_proj.weight",
            f"layers.{i}.mlp.d.weight": p + "mlp.down_proj.weight",
        })
    mapping.update({"norm.w": "model.norm.weight", "emb.weight": "model.embed_tokens.weight"})

    m.to(device, dtype)          # 先建好目标设备上的参数，再原位写入
    with torch.no_grad():
        params = dict(m.named_parameters())
        for name, src in mapping.items():
            if name in params and src in sd:
                params[name].copy_(sd[src].to(device, dtype))
        if "lm_head.weight" in sd:
            params["lm_head.weight"].copy_(sd["lm_head.weight"].to(device, dtype))
        else:
            params["lm_head.weight"].copy_(params["emb.weight"])
    m.eval()
    for p_ in m.parameters():
        p_.requires_grad_(False)
    print(f"[load] total {time.perf_counter() - t0:.1f}s", flush=True)
    return m


# ------------------------------------------------------------------ 解码
@torch.no_grad()
def greedy_decode(model: QwenModel, prompt_ids: list[int], max_new: int,
                  device: str = "cuda:0") -> tuple[list[int], float]:
    """纯自回归贪心解码（AR 基线）。返回 (token 序列, 输出 tok/s)。"""
    import time
    ids = torch.tensor([prompt_ids], device=device)
    caches = [KV() for _ in model.layers]
    t0 = time.perf_counter()
    out = model.logits_last(ids, caches, 0)
    torch.cuda.synchronize()
    new = [int(out[0].argmax())]
    pos = ids.shape[1]
    cur = torch.tensor([[new[-1]]], device=device)
    while len(new) < max_new:
        lg = model.logits_last(cur, caches, pos)
        pos += 1
        new.append(int(lg[0].argmax()))
        cur = torch.tensor([[new[-1]]], device=device)
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    return list(prompt_ids) + new, len(new) / dt


@torch.no_grad()
def greedy_decode_batched(model: QwenModel, prompt_ids: list[int], max_new: int,
                          device: str = "cuda:0") -> tuple[list[int], float]:
    """一次性把整段喂进模型再贪心取前 max_new —— 只用于测试前缀一致性。"""
    ids = torch.tensor([prompt_ids], device=device)
    lg = model.forward(ids)[0]
    return list(prompt_ids) + [int(x) for x in lg[-1].argmax(-1, keepdim=True)]
