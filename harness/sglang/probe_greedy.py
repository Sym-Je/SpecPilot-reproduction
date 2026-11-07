#!/usr/bin/env python3
"""第一条真实 greedy 请求：打 stock server，记录 output ids / 延迟 / spec 统计，并做确定性复跑。

用途（HANDOFF §三 的下一步）：
  1. 确认 /generate 在真实 27B + DFlash2 上跑得通；
  2. 确认 temperature=0 下同一输入两次的 output_ids 完全一致（greedy 确定性）；
  3. 拿到第一份 spec 统计（spec_verify_ct → accept_len），作为 τ 的口径校准点。

口径对齐上游 research/bench/bench.py：
  - prompt 用 tokenizer.apply_chat_template(add_generation_prompt=True, enable_thinking=True)
  - sampling = {"temperature": 0.0, "top_k": 1, "max_new_tokens": N}
  - 必须显式传 temperature，否则 SGLang 用模型 generation_config 的采样默认值

用法:
  python harness/sglang/probe_greedy.py                     # 前 3 条 gsm8k dev，各跑 2 遍
  python harness/sglang/probe_greedy.py --n 1 --max-new-tokens 256
  python harness/sglang/probe_greedy.py --out scratch/probe/gsm8k_probe.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

SP_ROOT = Path(__file__).resolve().parents[2]


def sha_ids(ids):
    return hashlib.sha256(json.dumps(list(ids), separators=(",", ":")).encode()).hexdigest()


def post(url, body, timeout=3600):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} {url}: {e.read()[:800]!r}")


def load_suite(path, n):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
            if len(out) >= n:
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:30000")
    ap.add_argument("--tokenizer", default="/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B")
    ap.add_argument("--suite", default=str(SP_ROOT / "assets/upstream/dev/gsm8k.jsonl"))
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--max-new-tokens", type=int, default=2048)
    ap.add_argument("--out", default=str(SP_ROOT / "scratch/probe/probe_greedy.json"))
    a = ap.parse_args()

    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(a.tokenizer)

    rows = []
    for item in load_suite(a.suite, a.n):
        ids = tok.apply_chat_template(
            [{"role": "user", "content": item["turns"][0]}],
            add_generation_prompt=True, tokenize=True, enable_thinking=True,
        )
        if not isinstance(ids, list):
            ids = list(ids["input_ids"])
        sampling = {"temperature": 0.0, "top_k": 1, "max_new_tokens": a.max_new_tokens}

        outs = []
        for rep in range(a.repeats):
            t0 = time.perf_counter()
            j = post(a.url + "/generate",
                     {"input_ids": ids, "sampling_params": sampling,
                      "rid": f"{item['id']}|probe|r{rep}"})
            dt = time.perf_counter() - t0
            m = j["meta_info"]
            out_ids = j["output_ids"]
            n_out = m["completion_tokens"]
            verify = m.get("spec_verify_ct") or 0
            outs.append({"rep": rep, "latency_s": dt,
                         "completion_tokens": n_out, "spec_verify_ct": verify,
                         "accept_len": (n_out / verify) if verify else None,
                         "server_e2e_s": m.get("e2e_latency"),
                         "finish_reason": (m.get("finish_reason") or {}).get("type"),
                         "output_sha256": sha_ids(out_ids), "output_ids": out_ids})
            print(f"[{item['id']}] rep{rep}: {n_out:5d} tok  {dt:7.2f}s  "
                  f"{n_out/dt:6.2f} tok/s  verify={verify:4d}  "
                  f"tau={(n_out/verify if verify else float('nan')):5.2f}  "
                  f"{outs[-1]['output_sha256'][:12]}")

        same = len({o["output_sha256"] for o in outs}) == 1
        print(f"[{item['id']}] deterministic over {len(outs)} reps: {same}")
        rows.append({"id": item["id"], "suite": item["suite"],
                     "prompt_tokens": len(ids), "input_sha256": sha_ids(ids),
                     "input_ids": ids, "repeats": outs, "deterministic": same})

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"url": a.url, "tokenizer": a.tokenizer, "suite": a.suite,
                               "max_new_tokens": a.max_new_tokens, "rows": rows},
                              indent=1))
    nd = sum(1 for r in rows if r["deterministic"])
    print(f"\nwrote {out}  | deterministic {nd}/{len(rows)}")
    print("ACCEPT" if nd == len(rows) else "REJECT: 非确定性，先查 random-seed / 采样参数")


if __name__ == "__main__":
    main()
