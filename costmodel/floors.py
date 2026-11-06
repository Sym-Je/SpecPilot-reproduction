"""byte/FLOP floor 表与三因子分解。

论文口径（docs/04-paper-facts.md）：
  S = tau(N) / c(N)                              —— 有效产出 / 每步成本
  ceiling = (tau_best/tau) * (T_prof/T_floor) * (T_step/T_prof)
  T_floor = max(FLOP @ 60% 峰值, bytes @ 90% 带宽)

三项分别是：
  tau      结构因子：树宽 / 草稿深度能带来多少次被接受的 token
  overhead 调度因子：实测每步时间 / roofline 下限
  kernel   内核因子：单次前向实际算力利用率

纸面收益与实际收益的差距必须能归因到这三个因子之一，否则就是测量口径变了。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    name: str
    flop_bf16: float      # FLOP/s
    bandwidth: float      # bytes/s
    smem: int             # bytes per SM


H100 = Device("H100-80G-HBM3", flop_bf16=989e12, bandwidth=3.35e12, smem=232448)
A100 = Device("A100-80G", flop_bf16=312e12, bandwidth=2.0e12, smem=163840)


@dataclass
class Factors:
    tau: float
    overhead: float
    kernel: float

    @property
    def ceiling(self) -> float:
        return self.tau * self.overhead * self.kernel

    def dominant(self) -> str:
        vals = {"tau": self.tau, "overhead": self.overhead, "kernel": self.kernel}
        return max(vals, key=vals.get)


def floor_latency(dev: Device, flops: float, nbytes: float) -> float:
    """一次前向的 roofline 下限（秒）。"""
    t_flop = flops / (0.60 * dev.flop_bf16)
    t_byte = nbytes / (0.90 * dev.bandwidth)
    return max(t_flop, t_byte)


def model_bytes(params: int, tokens: int, bytes_per: int = 2, kv_layers: int = 4,
                hidden: int = 256) -> float:
    """粗粒度字节数：权重读一遍 + KV 读写。"""
    weight = params * bytes_per
    kv = 2 * kv_layers * tokens * hidden * bytes_per
    return weight + kv


def decompose(dev: Device, params: int, prompt_len: int, gen_len: int,
              measured_step_ms: float, measured_tau: float,
              tau_best: float) -> Factors:
    """把实测折算成三因子。tau_best 由结构上限给出（例如树深）。"""
    flops = 2 * params * (prompt_len + gen_len)
    nbytes = model_bytes(params, prompt_len + gen_len)
    t_floor = floor_latency(dev, flops, nbytes)
    t_prof = measured_step_ms / 1000.0
    return Factors(
        tau=max(tau_best / max(measured_tau, 1e-9), 1.0),
        overhead=max(t_prof / max(t_floor, 1e-9), 1.0),
        kernel=1.0,   # 由 profiler 给出；无 profiler 时按 1 计，不虚构
    )
