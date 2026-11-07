"""KV/掩码对齐 + 无损性 + 真实 prompt 上的 τ。

三件事必须同时成立，否则投机解码的测量没有意义：
  1. 分块前向（带 cache, T>1, is_causal）与整段前向的 logits 数值一致
     → 证明因果掩码是右下对齐的，缓存里 query 能看见全部历史 key。
  2. 投机解码输出与 AR 贪心逐 token 相同 → 无损。
  3. draft=target 时 τ 应≈block 长度 → 接受逻辑本身正确。
"""
import json, os, sys, time
import torch
sys.path.insert(0, "/gpfs/users/jixinpeng/SpecDec/SpecPilot")
from harness.qwen_backend import QwenConfig, load_checkpoint, greedy_decode, KV
from harness.qwen_spec import SpecEngine, SpecOptions

D = "/gpfs/users/jixinpeng/models/Qwen3-8B"
DEV = sys.argv[1] if len(sys.argv) > 1 else "cuda:0"
NEW = int(sys.argv[2]) if len(sys.argv) > 2 else 24
ROOT = "/gpfs/users/jixinpeng/SpecDec/SpecPilot"

cfg = QwenConfig.from_dir(D)
m = load_checkpoint(D, cfg, device=DEV)

# ---------------- 真实 prompt
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(D)
rec = json.loads(open(os.path.join(ROOT, "assets/upstream/dev/gsm8k.jsonl")).readline())
prompt = tok.apply_chat_template([{"role": "user", "content": rec["turns"][0]}],
                                 add_generation_prompt=True, tokenize=True, return_dict=False)
prompt = list(prompt)
print(f"prompt tokens = {len(prompt)}", flush=True)

# ---------------- 1. 掩码对齐
with torch.no_grad():
    ids = torch.tensor([prompt], device=DEV)
    whole = m.forward(ids)[0]                      # 整段，无 cache
    # 分两段：先 1/2，再 1/2
    h = len(prompt) // 2
    tc = [KV() for _ in m.layers]
    m.forward(ids[:, :h], tc)
    tail = m.forward(ids[:, h:], tc)[0]
    d1 = (tail - whole[h:]).abs().max().item()
    # 逐 token
    tc = [KV() for _ in m.layers]
    outs = []
    for t in range(len(prompt)):
        outs.append(m.forward(ids[:, t:t+1], tc)[0, 0])
    d2 = (torch.stack(outs) - whole).abs().max().item()
print(json.dumps({"mask_halfdiff": d1, "mask_tokdiff": d2, "argmax_half_ok":
                  bool((tail.argmax(-1) == whole[h:].argmax(-1)).all())}), flush=True)

# ---------------- 2/3. AR vs 投机
ar, ar_tps = greedy_decode(m, prompt, NEW, DEV)
print(f"AR {ar_tps:.1f} tok/s", flush=True)
ref = ar[len(prompt):]
for bv in (False, True):
    for blk in (4, 8):
        eng = SpecEngine(m, m, SpecOptions(block=blk, block_verify=bv, device=DEV))
        r = eng.generate(prompt, NEW)
        print(json.dumps({"block_verify": bv, "block": blk,
                          "match": r.tokens == ref,
                          "tok_s": round(r.tokens_per_s, 2), "tau": round(r.tau, 2),
                          "tgt_fwd": r.tgt_forwards, "draft_fwd": r.draft_forwards,
                          "wall": round(r.wall_s, 2)}), flush=True)
