"""P2：把配对测量的传输从 JSONL stdio 换成 HTTP，**统计逻辑一行不改**。

为什么必须换
------------
`measure.PairBench` 原来的 worker 是 `harness/worker.py`：两张卡各起一个进程、
各跑一份 TinyLM，靠 stdin/stdout 传 options。真实引擎（SGLang）里
"options" 是**启动参数**（`--speculative-num-draft-tokens`、`SPECPILOT_*` 环境变量），
进程起来之后就改不了了。所以真实配对只能是**两个独立 server，各占一张卡**。

这一层做的事
------------
    Arm      = 一个 server 端点 + 一个固定的采样口径
    HttpPairBench = 两根 Arm，提供和 PairBench 相同签名的方法
                    （run_pair / calibrate / compare），复用 controller.stats

关键约束（显存决定）
--------------------
一条 27B 臂要 78 GB / 80 GB。**两臂不可能同卡**，所以：
  - 本机：arm A 起在 cuda:0，arm B 起在 cuda:1，天然配对；
  - NorthJob 单卡：只能 A→B 顺序跑，此时"互换"退化为"顺序交换"
    （`SequentialPairBench`），必须显式声明，不许冒充配对。
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .stats import paired_ci


def _post(url, body, timeout=3600, timing=None, capture=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        if timing is not None:
            timing.update(http_open_start_ns=time.perf_counter_ns(), url=url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if timing is not None:
                timing['body_complete_ns'] = time.perf_counter_ns()
            result = json.loads(payload)
            if capture is not None:
                capture.update(url=url, request=body, response=result, http_status=r.status)
            return result
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url}: {e.read()[:400]!r}")


def sha_ids(ids) -> str:
    return hashlib.sha256(json.dumps(list(ids), separators=(",", ":")).encode()).hexdigest()


@dataclass
class Arm:
    """一根测量臂 = 一个已经起好的 server。"""
    name: str
    url: str
    block_size: int | None = None
    tree_sha: str | None = None
    env: dict = field(default_factory=dict)
    sampling: dict = field(default_factory=lambda: {"temperature": 0.0, "top_k": 1})
    trace_timing: bool = False
    raw_dir: Path | None = None

    def health(self, timeout=5.0) -> bool:
        try:
            urllib.request.urlopen(self.url + "/model_info", timeout=timeout)
            return True
        except Exception:  # noqa: BLE001
            return False

    def begin_session(self) -> None:
        """一次测量的开始。真实 server 只能在同一臂上换不了配置，
        所以这里只做一条记录：这个 arm 的身份（tree sha + block + 关键 env）。
        进账本时这些必须一起写，否则"同一臂"不可证。"""
        self._session = {"arm": self.name, "url": self.url, "block_size": self.block_size,
                         "tree_sha": self.tree_sha,
                         "env": {k: v for k, v in self.env.items() if k.startswith("SPECPILOT_")}}
        if self.raw_dir is not None:
            self.raw_dir = Path(self.raw_dir)
            self.raw_dir.mkdir(parents=True, exist_ok=False)
            self._evidence_sequence = 0

    def step(self, input_ids, max_new: int, warmup: int = 0, rid: str | None = None) -> dict:
        """跑一次生成，返回和 harness.engine.RunResult 对齐的字段。"""
        sampling = dict(self.sampling, max_new_tokens=max_new)
        for _ in range(warmup):        # 预热结果丢弃，只为了让时钟爬到稳态
            _post(self.url + "/generate",
                  {"input_ids": input_ids, "sampling_params": sampling,
                   "rid": f"{(rid or 'w')}|warmup"})
        timing = {'step_start_ns': time.perf_counter_ns(), 'started_unix': time.time()} if self.trace_timing else None
        capture = {} if self.raw_dir is not None else None
        t0 = time.perf_counter()
        j = _post(self.url + "/generate",
                  {"input_ids": input_ids, "sampling_params": sampling,
                   "rid": f"{(rid or 'r')}|measure"}, timing=timing,
                  **({'capture': capture} if capture is not None else {}))
        dt = time.perf_counter() - t0
        if timing is not None:
            timing['step_end_ns'] = time.perf_counter_ns()
        m = j["meta_info"]
        out = j["output_ids"]
        n_out = m["completion_tokens"]
        verify = m.get("spec_verify_ct") or 0
        result = {
            "tokens_per_s": n_out / dt,
            "latency_ms": dt * 1000.0,
            "tokens": n_out,
            "tau": (n_out / verify) if verify else None,
            "spec_verify_ct": verify,
            "server_e2e_s": m.get("e2e_latency"),
            "output_ids": out,
            "output_sha256": sha_ids(out),
            "input_sha256": sha_ids(input_ids),
            "finish_reason": (m.get("finish_reason") or {}).get("type"),
            # 口径标记：stock 的 tau 是 per verify step，final 的 TLV 不是，必须写进记录
            "tau_source": "per_verify_step",
        }
        if timing is not None:
            result['client_timing'] = timing
        if capture is not None:
            self._evidence_sequence += 1
            destination = self.raw_dir / f'{self._evidence_sequence:06d}.json'
            with destination.open('x') as output:
                json.dump(capture, output, allow_nan=False)
            result['raw_evidence'] = dict(path=str(destination), sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
        return result


class HttpPairBench:
    """两根 arm 的配对测量。方法签名与 measure.PairBench 保持一致。"""

    def __init__(self, arm_a: Arm, arm_b: Arm, synchronized_start: bool = False,
                 reverse_submission: bool = False):
        self.a, self.b = arm_a, arm_b
        if synchronized_start:
            self._simultaneous = lambda first, second: self._synchronized(first, second, reverse_submission)

    @staticmethod
    def _synchronized(fa, fb, reverse=False):
        from threading import Barrier
        barrier = Barrier(2)

        def ready(function):
            barrier.wait(timeout=30)
            return function()

        if reverse:
            result_b, result_a = HttpPairBench._simultaneous(lambda: ready(fb), lambda: ready(fa))
            return result_a, result_b
        return HttpPairBench._simultaneous(lambda: ready(fa), lambda: ready(fb))

    @staticmethod
    def _simultaneous(fa, fb):
        """两卡同时发。任一抛异常就把另一个的结果也丢掉 —— 半次配对不是配对。"""
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as ex:
            xa, xb = ex.submit(fa), ex.submit(fb)
            return xa.result(), xb.result()

    def run_pair(self, input_ids, max_new: int, warmup: int = 1,
                 swap: bool = True, rid: str = "") -> dict:
        """一次配对。swap=True 时第二轮把 A/B 的角色对调重跑。

        注意：真实 server 换不了卡，所以"互换"在这里的含义是
        **交换时序先后**（谁先发），而不是交换物理 GPU。
        这条路只有在两根 arm 各自独占一张卡时才成立。
        """
        rounds = []
        for r in range(2 if swap else 1):
            a_first = (r == 0)
            rid_r = f"{rid}|r{r}"
            if a_first:
                ra, rb = self._simultaneous(
                    lambda: self.a.step(input_ids, max_new, warmup, rid_r + "|A"),
                    lambda: self.b.step(input_ids, max_new, warmup, rid_r + "|B"))
            else:
                rb, ra = self._simultaneous(
                    lambda: self.b.step(input_ids, max_new, warmup, rid_r + "|B"),
                    lambda: self.a.step(input_ids, max_new, warmup, rid_r + "|A"))
            rounds.append({"round": r, "a_first": a_first, "a": ra, "b": rb})
        return {"rounds": rounds,
                "a_tps": [x["a"]["tokens_per_s"] for x in rounds],
                "b_tps": [x["b"]["tokens_per_s"] for x in rounds],
                "a_tau": [x["a"]["tau"] for x in rounds],
                "b_tau": [x["b"]["tau"] for x in rounds]}

    def calibrate(self, input_ids, max_new: int, reps: int = 4, warmup_rounds: int = 1) -> dict:
        """同一根 arm 自比：噪声地板必须用**配对比值的离散度**，不是均值标准差。"""
        xs, ratios = [], []
        for i in range(reps + warmup_rounds):
            r = self.run_pair(input_ids, max_new, warmup=2 if i < warmup_rounds else 1,
                              swap=True, rid=f"calib|{i}")
            if i < warmup_rounds:
                continue
            xs.extend(r["a_tps"] + r["b_tps"])
            ratios.extend([y / x for x, y in zip(r["a_tps"], r["b_tps"])])
        ci = paired_ci([1.0] * len(ratios), ratios)
        return {"samples": xs, "ratios": ratios, "ci": ci,
                "noise": max(abs(ci["upper"] - 1.0), abs(1.0 - ci["lower"])),
                "mean": sum(xs) / len(xs), "n": len(xs),
                "arm": self.a.name}

    def compare(self, input_ids, max_new: int, noise: float, reps: int = 2) -> dict:
        if not math.isfinite(noise) or noise < 0 or type(reps) is not int or reps < 1:
            raise ValueError('invalid noise or comparison repetitions')
        a, b, shas = [], [], []
        for i in range(reps):
            r = self.run_pair(input_ids, max_new, warmup=1, swap=bool(i % 2), rid=f"cmp|{i}")
            a.extend(r["a_tps"]); b.extend(r["b_tps"])
            for x in r["rounds"]:
                shas.append({"a": x["a"]["output_sha256"], "b": x["b"]["output_sha256"]})
        ci = paired_ci(a, b)
        output_identical = all(item['a'] == item['b'] for item in shas)
        threshold = max(0.01 + 2 * noise, 0.03 if not output_identical else 0.0)
        return {"base_tps": a, "cand_tps": b, "ci": ci, "noise": noise,
                "threshold": threshold,
                "promoted": (ci["lower"] - 1.0) > threshold,
                "gain": ci["median"] - 1.0, "lower_gain": ci["lower"] - 1.0,
                "scope": "HTTP performance diagnostic; requires calibrated correctness and null evidence",
                "ledger_eligible": False,
                "output_identical": output_identical,
                "output_sha256": shas}


class SequentialPairBench:
    """单卡（NorthJob）退化路径：A 跑完 → 停 server → 起 B → 跑。

    **不许把它当配对测量**。它测的是"两次独立启动的吞吐"，中间隔了一次
    完整的冷启动 + 权重加载，卡温/时钟状态与配对完全不同。
    只用于 smoke / 快速筛方向，进账本必须标 `mode=sequential`。
    """

    def __init__(self, arm_a: Arm, arm_b: Arm):
        self.a, self.b = arm_a, arm_b
        self.one_card = True

    def run_pair(self, input_ids, max_new: int, warmup: int = 1, swap: bool = True,
                 rid: str = "") -> dict:
        ra = self.a.step(input_ids, max_new, warmup, rid + "|A")
        rb = self.b.step(input_ids, max_new, warmup, rid + "|B")
        return {"rounds": [{"a": ra, "b": rb, "a_first": True}],
                "a_tps": [ra["tokens_per_s"]], "b_tps": [rb["tokens_per_s"]],
                "a_tau": [ra["tau"]], "b_tau": [rb["tau"]],
                "mode": "sequential"}

    def calibrate(self, *a, **k):
        raise RuntimeError("单卡顺序路径无法标定噪声地板：配对被时序污染。"
                           "要么上 NorthJob 双卡，要么只做 smoke。")

    def compare(self, *a, **k):
        raise RuntimeError("单卡顺序路径不产出可进账本的指标。见 SequentialPairBench 文档。")
