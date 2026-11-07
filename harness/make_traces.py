"""**WIP / 不在主路径**：DFlash2 是已训练好的 drafter，RSI 闭环不需要自蒸馏语料。
保留是为了以后要做 draft 域适配（换 target 或换领域）时有个起点。未在真实模型上验证过。

用 target 生成蒸馏轨迹，但走**批处理**而不是逐 token 自回归。

逐 token 是 15 tok/s，32 条 × 512 token ≈ 18 分钟，纯浪费。
这里每条 prompt 一次前向（prompt 一次 + 一个 chunk 一次），配合 KV cache 分块推进，
chunk 内 T=40 时一次前向出 40 个预测，速度提升 10 倍以上。

产出 JSONL：{"prompt": [...], "tokens": [...]}，作为 draft 的自蒸馏语料。
"""
from __future__ import annotations

import json
import os
import sys
import time

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.qwen_backend import QwenConfig, KV, load_checkpoint  # noqa: E402


@torch.no_grad()
def gen_batched(model, prompt: list[int], n_new: int, device: str,
                chunk: int = 32) -> list[int]:
    """贪心解码，每轮前向只接受「自洽前缀」，从第一个不自洽处回滚。

    做法：用上一轮预测出的 token 填满 chunk，一次前向拿到每个位置的预测
    preds[i]。preds 在「填进去的 token 与贪心输出一致」之前都是有效的
    （因为那些位置的前缀本身就是贪心前缀）。一旦 preds[i] != toks[i]，
    说明 toks[i] 填错了，回滚到 i 重来。因此每次前向至少推进 1 个、
    通常推进整块，比逐 token 快一个数量级，且与逐 token 贪心**逐位等价**。
    """
    caches = [KV() for _ in model.layers]
    ids = torch.tensor([prompt], device=device)
    logits = model.forward(ids, caches)[:, -1, :]
    out: list[int] = []
    while len(out) < n_new:
        n = min(chunk, n_new - len(out))
        toks = [int(logits[0].argmax())]
        toks += [toks[-1]] * (n - 1)          # 占位，下面按自洽前缀重放
        lg = model.forward(torch.tensor([toks], device=device), caches)[0]
        preds = [int(x) for x in lg.argmax(-1)]
        ok = 0
        while ok < n and preds[ok] == toks[ok]:
            ok += 1
        if ok == 0:                            # 理论上不会：toks[0] 就是 argmax
            ok = 1
        base = caches[0].n - n
        for c in caches:
            c.truncate(base + ok)
        real = preds[:ok]
        logits = model.forward(torch.tensor([real], device=device),
                               caches)[:, -1, :]
        out.extend(real)
    return out[:n_new]


if __name__ == "__main__":
    D = "/gpfs/users/jixinpeng/models/Qwen3-8B"
    OUT = sys.argv[1] if len(sys.argv) > 1 else "/gpfs/users/jixinpeng/models/traces.jsonl"
    N_NEW = int(sys.argv[2]) if len(sys.argv) > 2 else 384
    DEV = sys.argv[3] if len(sys.argv) > 3 else "cuda:0"
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from transformers import AutoTokenizer

    cfg = QwenConfig.from_dir(D)
    tok = AutoTokenizer.from_pretrained(D)
    model = load_checkpoint(D, cfg, device=DEV)

    prompts = []
    for suite in ("gsm8k", "humaneval", "math500", "mbpp"):
        f = os.path.join(ROOT, "assets", "upstream", "dev", f"{suite}.jsonl")
        with open(f) as fh:
            for i, line in enumerate(fh):
                if i >= 6:
                    break
                text = json.loads(line)["turns"][0]
                ids = tok.apply_chat_template([{"role": "user", "content": text}],
                                              add_generation_prompt=True,
                                              tokenize=True, return_dict=False)
                prompts.append(list(ids))

    t0 = time.time()
    with open(OUT, "w") as f:
        for i, p in enumerate(prompts):
            toks = gen_batched(model, p, N_NEW, DEV)
            f.write(json.dumps({"prompt": p, "tokens": toks}) + "\n")
            f.flush()
            print(f"[{i+1}/{len(prompts)}] len={len(toks)} t={time.time()-t0:.0f}s",
                  flush=True)
    print("saved", OUT)
