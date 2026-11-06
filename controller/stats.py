"""统计工具：配对 bootstrap 区间、噪声标定、二项检验。

为什么用 bootstrap：tok/s 的样本分布既不正态也不稳定，配对差值的中位数区间
用 t 检验会低估。论文用的是 95% 置信下界，这里用 percentile bootstrap，同口径。
"""
from __future__ import annotations

import math
import random


def bootstrap_ci(xs: list[float], iters: int = 2000, alpha: float = 0.05,
                 seed: int = 0) -> tuple[float, float]:
    """返回 (mean, lower_bound)。单样本 bootstrap 均值区间。"""
    if not xs:
        raise ValueError("空样本")
    if len(xs) == 1:
        return xs[0], xs[0]
    rnd = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(iters):
        s = sum(xs[rnd.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    lo = means[int(iters * alpha)]
    return sum(xs) / n, lo


def paired_ci(a: list[float], b: list[float], iters: int = 2000,
              alpha: float = 0.05, seed: int = 0) -> dict:
    """配对样本：b 相对 a 的提升比例。返回中位数、下界、相对波动。"""
    if len(a) != len(b) or not a:
        raise ValueError("配对样本长度必须一致且非空")
    ratios = [(y / x) if x > 0 else 0.0 for x, y in zip(a, b)]
    rnd = random.Random(seed)
    n = len(ratios)
    meds = []
    for _ in range(iters):
        s = sorted(ratios[rnd.randrange(n)] for _ in range(n))
        meds.append(s[n // 2])
    meds.sort()
    med = sorted(ratios)[n // 2]
    return {
        "median": med,
        "lower": meds[int(iters * alpha)],
        "upper": meds[int(iters * (1 - alpha))],
        "n": n,
        "spread": (max(ratios) - min(ratios)) / med if med else 0.0,
    }


def noise_from_null(xs: list[float]) -> float:
    """stock vs stock 的相对波动，作为噪声地板。"""
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    if mean <= 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var) / mean


def binom_one_sided(k: int, n: int, p0: float) -> float:
    """P(X >= k | n, p0)，用于 event rule。"""
    if n == 0:
        return 1.0
    return sum(math.comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(k, n + 1))
