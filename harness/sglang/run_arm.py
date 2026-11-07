#!/usr/bin/env python3
"""跑一根臂的完整请求集，落 JSONL。由 exp/p3_pair.sh 在 server 就绪后调用。

环境（由 p3_pair.sh 传入）：P3_URL / P3_ARM / P3_BLOCK / P3_TREE_SHA / P3_OUT

口径（与上游 research/bench/bench.py 逐项对齐，**不要自行改**）
--------------------------------------------------------------
- prompt：客户端用 **target 的 tokenizer** `apply_chat_template(add_generation_prompt=True,
  enable_thinking=True)` 预先展开成 input_ids，再打 `/generate`。
  为什么不用 server 的 `/tokenize`：`/tokenize` 吃的是裸文本，没有 chat template 的
  system/生成提示，跑出来的 prompt 比上游短一截，三臂之间也不可比。
- sampling：`{"temperature": 0.0, "top_k": 1, "max_new_tokens": N}`，必须显式给
  temperature，否则 SGLang 落到模型 generation_config 的默认采样。
- 只跑 **turn 0**（等价上游 `--first-turn-only`）：多轮的 2..n 轮输入依赖上一轮输出，
  三臂输出不同 → 输入不同 → 配对失效。turn 0 的 input_ids 在三臂间**按构造完全相同**，
  这是配对测量的前提，也是本文件写 input_sha256 的目的。

自洽性：每条请求同时落 input_sha256 / output_sha256。同一 (arm, id) 出现两次即视为
重复运行 —— 直接拒绝，不静默追加（否则配对时会拿两条同臂样本算 CI）。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from controller.http_transport import sha_ids  # noqa: E402

URL = os.environ["P3_URL"]
ARM = os.environ["P3_ARM"]
BLOCK = int(os.environ["P3_BLOCK"])
TREE_SHA = os.environ.get("P3_TREE_SHA", "unknown")
OUT = Path(os.environ["P3_OUT"])
TOKENIZER = os.environ.get("P3_TOKENIZER",
                           "/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B")

MAX_NEW = int(os.environ.get("P3_MAX_NEW", "1024"))
WARMUP = int(os.environ.get("P3_WARMUP", "2"))
SPLIT = os.environ.get("P3_SPLIT", "dev")
SUITES = os.environ.get("P3_SUITES", "gsm8k math500 humaneval mbpp mt-bench").split()
PER_SUITE = int(os.environ.get("P3_PER_SUITE", "8"))


def post(body, timeout=3600):
    req = urllib.request.Request(URL + "/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} {URL}/generate: {e.read()[:600]!r}")


def load_split(split, suites, per_suite):
    out = []
    for s in suites:
        p = ROOT / "assets" / "upstream" / split / f"{s}.jsonl"
        if not p.exists():
            print(f"[warn] missing {p}", file=sys.stderr)
            continue
        n = 0
        with open(p) as f:
            for line in f:
                if n >= per_suite:
                    break
                line = line.strip()
                if line:
                    out.append(json.loads(line))
                    n += 1
    return out


def existing_keys(path):
    """已落盘的 (arm,id)。OUT 是跨臂共享的 JSONL 时，只关心本臂的键。"""
    keys = set()
    if not path.exists():
        return keys
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                raise SystemExit(f"REJECT: {path} 有损坏行，先人工检查")
            if r.get("arm") == ARM:
                keys.add(r["id"])
    return keys


def main():
    items = load_split(SPLIT, SUITES, PER_SUITE)
    if not items:
        raise SystemExit("no items")

    done = existing_keys(OUT)
    if done and os.environ.get("P3_RESUME") != "1":
        raise SystemExit(
            f"REJECT: {OUT} 已有 arm={ARM} 的 {len(done)} 行。"
            f"  重跑整臂：删掉该臂行或换 OUT；断点续跑：P3_RESUME=1")
    todo = [it for it in items if it["id"] not in done]
    print(f"[arm {ARM}] {len(items)} items ({len(todo)} todo), block={BLOCK}, "
          f"tree={TREE_SHA[:12]}", file=sys.stderr)

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TOKENIZER)

    def encode_text(text):
        ids = tok.apply_chat_template(
            [{"role": "user", "content": text}],
            add_generation_prompt=True, tokenize=True, enable_thinking=True)
        if not isinstance(ids, list):
            ids = ids["input_ids"]
        return list(ids)

    def encode(item):
        # turn 0 only。mt-bench 是多轮，第 2 轮起输入依赖本臂自己的输出 → 三臂不可比。
        return encode_text(item["turns"][0])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # 预热：不同长度的短请求，让 prefill/decode 图与时钟进稳态，不计入结果
    for w in range(WARMUP):
        post({"input_ids": encode_text("hello world " * (1 + 40 * w)),
              "sampling_params": {"temperature": 0.0, "top_k": 1, "max_new_tokens": 32},
              "rid": f"warm{w}|{ARM}"})

    rows = []
    for it in todo:
        ids = encode(it)
        t0 = time.perf_counter()
        j = post({"input_ids": ids,
                  "sampling_params": {"temperature": 0.0, "top_k": 1,
                                      "max_new_tokens": MAX_NEW},
                  "rid": f"{it['id']}|{ARM}"})
        dt = time.perf_counter() - t0
        m = j["meta_info"]
        n_out = m["completion_tokens"]
        verify = m.get("spec_verify_ct") or 0
        row = {"id": it["id"], "item": it["id"], "turn": 0,
               "suite": it["suite"], "category": it.get("category"),
               "arm": ARM, "block": BLOCK, "tree_sha": TREE_SHA,
               "prompt_tokens": len(ids), "server_prompt_tokens": m.get("prompt_tokens"),
               "input_sha256": sha_ids(ids),
               "completion_tokens": n_out, "latency_s": dt,
               "tokens_per_s": n_out / dt,
               "spec_verify_ct": verify,
               "tau": (n_out / verify) if verify else None,
               "tau_source": "per_verify_step" if verify > 0 else "ar_no_verify",
               "server_e2e_s": m.get("e2e_latency"),
               "finish_reason": (m.get("finish_reason") or {}).get("type"),
               "max_new_tokens": MAX_NEW,
               "output_sha256": sha_ids(j["output_ids"]),
               "output_ids": j["output_ids"]}
        rows.append(row)
        print(f"[{ARM}] {it['id']:16s} {len(ids):5d}→{n_out:5d} tok {dt:7.2f}s "
              f"{row['tokens_per_s']:7.2f} tok/s verify={verify:4d} "
              f"tau={row['tau'] if row['tau'] else float('nan'):5.2f}", file=sys.stderr)

    with open(OUT, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    bad = [r for r in rows if r["completion_tokens"] <= 0]
    hit = sum(1 for r in rows if r["finish_reason"] == "length")
    print(f"[arm {ARM}] wrote {len(rows)} rows -> {OUT} | empty={len(bad)} "
          f"truncated_at_max_new={hit}/{len(rows)}", file=sys.stderr)
    if bad:
        raise SystemExit("REJECT: 有 completion_tokens<=0 的行")



if __name__ == "__main__":
    main()
