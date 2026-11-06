"""单 GPU 上的引擎进程。controller 通过 stdin/stdout 的 JSONL 驱动它。

协议：
  → {"id": 0, "options": {...}, "prompt": [..], "max_new": 64}
  ← {"id": 0, "ok": true, "result": {...}}
  → {"id": 1, "cmd": "quit"}
  ← {"id": 1, "ok": true}

一个 worker 绑定一张卡；agent 进程不得直接启动 worker（否则可自报数字），
只能通过 controller.sandbox 里的 measure 入口。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    dev = os.environ.get("SPECPILOT_DEVICE", "cuda:0")
    import torch
    from harness.engine import Options, SpecEngine, StepStats, build_weights

    _wcache: dict[int, dict] = {}

    def weights_for(n_layers: int) -> dict:
        if n_layers not in _wcache:
            _wcache[n_layers] = build_weights(Options(), seed=1, draft_layers=n_layers)
        return _wcache[n_layers]
    engines: dict[tuple, SpecEngine] = {}
    print(json.dumps({"ready": True, "device": dev, "gpu": torch.cuda.get_device_name(0)}),
          flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        if req.get("cmd") == "quit":
            print(json.dumps({"id": req.get("id"), "ok": True}), flush=True)
            return
        try:
            key = tuple(sorted(req["options"].items()))
            eng = engines.get(key)
            if eng is None:
                opts = Options(**req["options"])
                eng = SpecEngine(opts, device=dev,
                                 weights=weights_for(opts.draft_layers))
                engines[key] = eng
            eng.stats = StepStats()
            # 预热：跑满一次并丢弃，让 GPU 时钟爬到稳态再计时
            for _ in range(int(req.get("warmup", 1))):
                eng.generate(req["prompt"], req["max_new"])
            eng.stats = StepStats()
            _, res = eng.generate(req["prompt"], req["max_new"])
            print(json.dumps({"id": req["id"], "ok": True,
                              "result": json.loads(res.to_json())}), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"id": req.get("id"), "ok": False,
                              "error": f"{type(e).__name__}: {e}"}), flush=True)


if __name__ == "__main__":
    main()
