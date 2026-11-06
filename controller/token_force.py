"""token forcing —— 判定「输出是否逐 token 等价」的两条规则。

论文口径（docs/02-acceptance.md §1 T1）：
  rate rule ：分歧率上升 0.5pt @95%CI 即拒绝
  event rule：margin > 2*delta 的事件做二项检验，显著即拒绝

为什么不能用任务精度：Fig 2c 显示四个精度区间全部含 0，精度根本发现不了分歧。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .stats import binom_one_sided


@dataclass
class ForceResult:
    n: int
    diverged: int
    rate: float
    baseline_rate: float
    rate_delta_pt: float
    rate_ci_low: float
    rate_flagged: bool
    events: int
    event_p: float
    event_flagged: bool

    @property
    def lossless(self) -> bool:
        return not self.rate_flagged and not self.event_flagged

    def to_dict(self) -> dict:
        return {
            "n": self.n, "diverged": self.diverged, "rate": self.rate,
            "baseline_rate": self.baseline_rate, "rate_delta_pt": self.rate_delta_pt,
            "rate_ci_low": self.rate_ci_low, "rate_flagged": self.rate_flagged,
            "events": self.events, "event_p": self.event_p,
            "event_flagged": self.event_flagged, "lossless": self.lossless,
        }


def _wilson_low(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / d)


def judge_forcing(base_tokens: list[list[int]], cand_tokens: list[list[int]],
                  base_rate: float = 0.0072, delta: float = 0.02) -> ForceResult:
    """逐 token 比对。base_rate 是 stock 自身的已知 mismatch（论文 0.72%）。"""
    if len(base_tokens) != len(cand_tokens):
        raise ValueError("两侧样本数必须一致")
    n = total = 0
    events = 0
    for a, b in zip(base_tokens, cand_tokens):
        for ta, tb in zip(a, b):
            total += 1
            n += 1
            if ta != tb:
                events += 1
    rate = events / n if n else 0.0
    low = _wilson_low(events, n)
    flagged = (rate - base_rate) - low > 0.005
    # event rule：分歧是否显著多于 stock 水平
    p = binom_one_sided(events, n, base_rate) if n else 1.0
    return ForceResult(
        n=n, diverged=events, rate=rate, baseline_rate=base_rate,
        rate_delta_pt=(rate - base_rate) * 100, rate_ci_low=low,
        rate_flagged=flagged,
        events=events, event_p=p, event_flagged=p < 0.05,
    )
