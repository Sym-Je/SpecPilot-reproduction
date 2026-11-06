"""配对测量 —— 唯一有权产出「进账本的数字」的模块。

协议（论文 §3.2 / 本仓库 AGENTS.md 铁律 1）：
  - 双卡同时各跑一个候选，同一请求、同一 token 数；
  - 每轮结束后**互换 GPU**，消除卡的个体差异与时钟漂移；
  - 结果取配对比值的 95% 置信下界，不用均值；
  - 每会话先跑 stock vs stock 标定噪声地板，进账本。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from .stats import bootstrap_ci, noise_from_null, paired_ci  # noqa: E402


@dataclass
class Worker:
    proc: subprocess.Popen
    gpu: str
    name: str

    def send(self, obj: dict) -> dict:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"worker {self.name} 提前退出")
            msg = json.loads(line)
            if msg.get("id") == obj.get("id"):
                return msg

    def close(self) -> None:
        try:
            self.send({"id": -1, "cmd": "quit"})
        except Exception:  # noqa: BLE001
            pass
        self.proc.terminate()


class PairBench:
    """管理两个 GPU worker，提供交错 + 互换的配对测量。"""

    def __init__(self, python: str | None = None, devices: tuple[str, str] = ("cuda:0", "cuda:1")):
        py = python or os.environ.get("SPECPILOT_PYTHON") or sys.executable
        self.workers: list[Worker] = []
        for i, dev in enumerate(devices):
            env = dict(os.environ, SPECPILOT_DEVICE=dev, PYTHONPATH=ROOT)
            proc = subprocess.Popen(
                [py, "-m", "harness.worker"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env, cwd=ROOT,
                preexec_fn=self._pin(i),
            )
            ready = json.loads(proc.stdout.readline())
            if not ready.get("ready"):
                raise RuntimeError(f"worker {dev} 未就绪: {ready}")
            self.workers.append(Worker(proc, dev, f"w{i}"))

    @staticmethod
    def _pin(idx: int):
        """让 worker 只看见自己那张卡 —— 否则两张卡都会分到同一个 device。"""
        def fn() -> None:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(idx)
        return fn

    def close(self) -> None:
        for w in self.workers:
            w.close()

    # ---------------------------------------------------------------- 测量
    def run_pair(self, req: dict, opt_a: dict, opt_b: dict, max_new: int,
                 warmup: int, swap: bool = True) -> dict:
        """一次配对：A 在卡0、B 在卡1；swap=True 时再跑一次 B在卡0、A在卡1。"""
        rounds = []
        assignments = [((0, 1), (opt_a, opt_b))]
        if swap:
            assignments.append(((1, 0), (opt_a, opt_b)))
        for r, ((ga, gb), (oa, ob)) in enumerate(assignments):
            ra = self.workers[ga].send({"id": r * 10 + 1, "options": oa,
                                        "prompt": req["prompt"], "max_new": max_new,
                                        "warmup": warmup})
            rb = self.workers[gb].send({"id": r * 10 + 2, "options": ob,
                                        "prompt": req["prompt"], "max_new": max_new,
                                        "warmup": warmup})
            if not ra.get("ok") or not rb.get("ok"):
                raise RuntimeError(f"测量失败: {ra} / {rb}")
            rounds.append({
                "gpu_a": self.workers[ga].gpu, "gpu_b": self.workers[gb].gpu,
                "a": ra["result"], "b": rb["result"],
            })
        a_tps = [x["a"]["tokens_per_s"] for x in rounds]
        b_tps = [x["b"]["tokens_per_s"] for x in rounds]
        return {"rounds": rounds, "a_tps": a_tps, "b_tps": b_tps}

    def calibrate(self, req: dict, opts: dict, max_new: int, reps: int = 4,
                  warm_rounds: int = 1) -> dict:
        """stock vs stock：同一配置在两张卡上对打。

        噪声地板定义为**配对比值**的离散度 —— 判定本身就是比值比较，
        用各次均值的标准差会把跨卡差异也算成噪声，把地板抬到 15% 量级，
        结果任何 <30% 的机制都无法晋升。
        """
        xs, ratios = [], []
        for i in range(reps + warm_rounds):
            r = self.run_pair(req, opts, opts, max_new, warmup=1 if i >= warm_rounds else 2,
                              swap=bool(i % 2))
            if i < warm_rounds:            # 首轮只用来点灯，不进统计
                continue
            xs.extend(r["a_tps"] + r["b_tps"])
            ratios.extend([y / x for x, y in zip(r["a_tps"], r["b_tps"])])
        ci = paired_ci([1.0] * len(ratios), ratios)
        half_width = max(abs(ci["upper"] - 1.0), abs(1.0 - ci["lower"]))
        return {"samples": xs, "ratios": ratios, "ci": ci,
                "noise": half_width, "mean": sum(xs) / len(xs), "n": len(xs)}

    def compare(self, req: dict, base: dict, cand: dict, max_new: int,
                noise: float, reps: int = 2) -> dict:
        """base vs cand，含互换。返回晋升判定所需的全部量。"""
        a, b = [], []
        for i in range(reps):
            r = self.run_pair(req, base, cand, max_new, warmup=1, swap=bool(i % 2))
            a.extend(r["a_tps"])
            b.extend(r["b_tps"])
        ci = paired_ci(a, b)
        # 论文判据：95% LB > 1% + 2x 噪声
        threshold = 0.01 + 2 * noise
        promoted = (ci["lower"] - 1.0) > threshold
        return {
            "base_tps": a, "cand_tps": b, "ci": ci, "noise": noise,
            "threshold": threshold, "promoted": promoted,
            "gain": ci["median"] - 1.0, "lower_gain": ci["lower"] - 1.0,
        }
