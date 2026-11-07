"""用 target 的输出蒸馏一个浅层 draft（Qwen3-8B → 2 层，共享 embedding/head）。

为什么必须自己蒸：上游只发布了 27B 的 DFlash2/DSpark drafter，8B 没有公开草稿。
draft 的层数取 target 的前 k 层权重初始化、共享 token embedding 与 lm_head，
再在 target 自己生成的 token 序列上做几十分钟的自蒸馏。

验收：draft 的 top-1 与 target 的一致率。stock 投机解码的 τ 直接由它决定
（一致率 p、块长 B 时 τ ≈ (1-p^B)/(1-p)）。
"""
from __future__ import annotations

import json
import os
import sys
import time

import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.qwen_backend import QwenConfig, QwenModel, KV, load_checkpoint  # noqa: E402


def build_draft(tgt: QwenModel, cfg: QwenConfig, n_layers: int) -> QwenModel:
    d = QwenModel(cfg, n_layers=n_layers)
    sd_t = tgt.state_dict()
    sd_d = d.state_dict()
    for k, v in sd_t.items():
        if k.startswith("layers.") and k in sd_d:
            sd_d[k] = v
        elif k in ("emb.weight", "lm_head.weight", "norm.w"):
            sd_d[k] = v
    d.load_state_dict(sd_d)
    return d


@torch.no_grad()
def sample_texts(tgt: QwenModel, prompts: list[list[int]], n_new: int,
                 device: str = "cuda:0") -> list[list[int]]:
    outs = []
    for p in prompts:
        ids = torch.tensor([p], device=device)
        caches = [KV() for _ in tgt.layers]
        lg = tgt.logits_last(ids, caches, 0)
        pos = ids.shape[1]
        cur_tok = int(lg[0].argmax())
        seq = list(p) + [cur_tok]
        for _ in range(n_new - 1):
            lg = tgt.logits_last(torch.tensor([[cur_tok]], device=device), caches, pos)
            pos += 1
            cur_tok = int(lg[0].argmax())
            seq.append(cur_tok)
        outs.append(seq)
    return outs


def train(draft: QwenModel, tgt: QwenModel, seqs: list[list[int]], steps: int = 300,
          bs: int = 2, win: int = 512, lr: float = 2e-4, device: str = "cuda:0",
          log_every: int = 20) -> list[dict]:
    """在 target 的贪心输出上做 next-token 蒸馏（贪心解码 → target 是 hard label）。

    draft 共享 target 的 lm_head，所以 loss 直接落在 target 的词表分布上。
    取窗必须容忍序列比 win 短：按「本序列实际可用长度」截断，否则 xi/yi 会差一位，
    cross_entropy 报 batch_size 不匹配（上一版就这么挂的）。
    """
    for p in draft.emb.parameters():
        p.requires_grad_(False)
    for p in draft.lm_head.parameters():
        p.requires_grad_(False)
    trainable = [p for p in draft.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=lr)
    log = []
    t0 = time.time()
    for step in range(steps):
        segs = []
        for b in range(bs):
            s = seqs[(step * bs + b) % len(seqs)]
            w = min(win, len(s) - 2)              # 序列本身可能比 win 短
            if w < 2:
                continue
            st = torch.randint(0, len(s) - w - 1, (1,)).item()
            segs.append(s[st:st + w + 1])
        if not segs:
            continue
        T = min(len(g) for g in segs) - 1
        xi = torch.tensor([g[:T] for g in segs], device=device)
        yi = torch.tensor([g[1:T + 1] for g in segs], device=device)
        lg = draft.forward(xi)
        loss = F.cross_entropy(lg.reshape(-1, lg.shape[-1]).float().view(-1, lg.shape[-1]),
                               yi.reshape(-1))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(trainable, 1.0)
        opt.step()
        if step % log_every == 0:
            rec = {"step": step, "loss": round(loss.item(), 4),
                   "elapsed_s": round(time.time() - t0, 1)}
            log.append(rec)
            print(json.dumps(rec), flush=True)
    return log


@torch.no_grad()
def top1_agreement(draft: QwenModel, tgt: QwenModel, seqs: list[list[int]],
                   n: int = 64, win: int = 256, device: str = "cuda:0") -> float:
    same = tot = 0
    for s in seqs[:n]:
        x = torch.tensor([s[:win + 1]], device=device)
        a = draft.forward(x)[0, :-1]
        b = tgt.forward(x)[0, :-1]
        same += int((a.argmax(-1) == b.argmax(-1)).sum())
        tot += a.shape[0]
    return same / tot


def load_prompts(model_dir: str, n_per_suite: int = 8) -> list[list[int]]:
    """用上游 research/bench 的 dev 请求集当蒸馏语料（真实分布，非随机 token）。"""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_dir)
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "assets", "upstream", "dev")
    prompts = []
    for suite in ("gsm8k", "humaneval", "math500", "mbpp"):
        f = os.path.join(root, f"{suite}.jsonl")
        if not os.path.exists(f):
            continue
        with open(f) as fh:
            for i, line in enumerate(fh):
                if i >= n_per_suite:
                    break
                rec = json.loads(line)
                text = rec["turns"][0]
                ids = tok.apply_chat_template(
                    [{"role": "user", "content": text}],
                    add_generation_prompt=True, tokenize=True,
                    return_dict=False)
                prompts.append(list(ids))
    return prompts


if __name__ == "__main__":
    D = sys.argv[1] if len(sys.argv) > 1 else "/gpfs/users/jixinpeng/models/Qwen3-8B"
    NL = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    STEPS = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    OUT = sys.argv[4] if len(sys.argv) > 4 else "/gpfs/users/jixinpeng/models/qwen3-8b-draft2.pt"
    DEV = sys.argv[5] if len(sys.argv) > 5 else "cuda:0"
    cfg = QwenConfig.from_dir(D)
    tgt = load_checkpoint(D, cfg, device=DEV)
    prompts = load_prompts(D)
    print(f"[gen] {len(prompts)} prompts, sampling target trajectories ...", flush=True)
    seqs = sample_texts(tgt, prompts, 512, DEV)
    print("[gen] done", [len(s) for s in seqs], flush=True)

    draft = build_draft(tgt, cfg, NL).to(DEV, torch.bfloat16)
    for p in draft.parameters():
        p.requires_grad_(True)
    for p in draft.emb.parameters():
        p.requires_grad_(False)
    a0 = top1_agreement(draft, tgt, seqs, device=DEV)
    print(f"[draft] {NL} layers, agree before train {a0:.3f}", flush=True)
    log = train(draft, tgt, seqs, steps=STEPS, device=DEV)
    agree = top1_agreement(draft, tgt, seqs, device=DEV)
    print(f"[draft] agree after train {agree:.3f}", flush=True)
    torch.save({"layers": {k: v.cpu() for k, v in draft.state_dict().items()
                           if k.startswith("layers.")},
                "n_layers": NL, "agreement": agree, "agree_before": a0, "log": log}, OUT)
    print("saved", OUT, flush=True)
