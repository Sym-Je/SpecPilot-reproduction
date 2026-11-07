"""冒烟测试：AR 贪心 vs 投机解码，token 序列必须逐位相同。

draft 直接复用 target 权重（接受率≈100%），这样 KV 任何错位都会立刻表现为
数字不一致；同时也给出 block 换 forward 次数的量级。
"""
import json, sys, time
import torch
sys.path.insert(0, "/gpfs/users/jixinpeng/SpecDec/SpecPilot")
from harness.qwen_backend import QwenConfig, load_checkpoint, greedy_decode
from harness.qwen_spec import SpecEngine, SpecOptions

D = "/gpfs/users/jixinpeng/models/Qwen3-8B"
DEV = sys.argv[1] if len(sys.argv) > 1 else "cuda:1"
NEW = int(sys.argv[2]) if len(sys.argv) > 2 else 24
cfg = QwenConfig.from_dir(D)
t0 = time.time()
m = load_checkpoint(D, cfg, device=DEV)
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

prompt = [int(x) for x in open("/tmp/smoke_prompt.txt").read().split()] if False else list(range(1000, 1060))

ar, ar_tps = greedy_decode(m, prompt, NEW, DEV)
print(f"AR  {ar_tps:.1f} tok/s  tail={ar[-8:]}", flush=True)

for bv in (False, True):
    for blk in (4, 8):
        eng = SpecEngine(m, m, SpecOptions(block=blk, block_verify=bv, device=DEV))
        r = eng.generate(prompt, NEW)
        same = r.tokens == ar[len(prompt):]
        print(json.dumps({"block_verify": bv, "block": blk, "match": same,
                          "tok_s": round(r.tokens_per_s, 2), "tau": round(r.tau, 2),
                          "tgt_fwd": r.tgt_forwards, "tgt_tokens": r.tgt_tokens,
                          "draft_fwd": r.draft_forwards, "wall": round(r.wall_s, 2)}), flush=True)
        if not same:
            for i, (a, b) in enumerate(zip(r.tokens, ar[len(prompt):])):
                if a != b:
                    print(f"  first diff at {i}: spec={a} ar={b}")
                    break
