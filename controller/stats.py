"""统计工具：配对 bootstrap 区间、噪声标定、二项检验。

为什么用 bootstrap：tok/s 的样本分布既不正态也不稳定，配对差值的中位数区间
用 t 检验会低估。论文用的是 95% 置信下界，这里用 percentile bootstrap，同口径。
"""
from __future__ import annotations

import math
import random


def _validate_bootstrap(xs, iters, alpha):
    if not xs or any(not math.isfinite(value) for value in xs):
        raise ValueError('bootstrap requires nonempty finite samples')
    if type(iters) is not int or iters < 1 or not 0 < alpha < 0.5:
        raise ValueError('invalid bootstrap iteration count or tail probability')


def bootstrap_ci(xs: list[float], iters: int = 2000, alpha: float = 0.05,
                 seed: int = 0) -> tuple[float, float]:
    """返回 (mean, lower_bound)。单样本 bootstrap 均值区间。"""
    _validate_bootstrap(xs, iters, alpha)
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
    _validate_bootstrap(a + b, iters, alpha)
    if any(value <= 0 for value in a + b):
        raise ValueError('paired measurements must be positive')
    ratios = [candidate / baseline for baseline, candidate in zip(a, b)]
    if any(not math.isfinite(value) or value <= 0 for value in ratios):
        raise ValueError('invalid paired ratios')
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


def stratified_geomean_ci(groups: dict[str, list[float]], iters: int = 10000,
                          seed: int = 0) -> dict:
    """Two-sided 95% CI; values are request log ratios with GPU rounds clustered."""
    if not groups:
        raise ValueError('missing benchmark groups')
    for values in groups.values():
        _validate_bootstrap(values, iters, .025)
    random_source = random.Random(seed)
    benchmarks = list(groups.values())
    estimates = []
    for _ in range(iters):
        estimate = sum(sum(values[random_source.randrange(len(values))]
                           for _ in values) / len(values)
                       for values in benchmarks) / len(benchmarks)
        estimates.append(estimate)
    estimates.sort()
    estimate = sum(sum(values) / len(values) for values in benchmarks) / len(benchmarks)
    return {'geomean': math.exp(estimate), 'lower': math.exp(estimates[int(iters * .025)]),
            'upper': math.exp(estimates[int(iters * .975)]), 'confidence_level': .95,
            'method': 'suite-stratified request-cluster log bootstrap; physical rounds kept together',
            'bootstrap_iters': iters, 'bootstrap_seed': seed}


def binom_one_sided(k: int, n: int, p0: float) -> float:
    """P(X >= k | n, p0)，用于 event rule。"""
    if type(k) is not int or type(n) is not int or not 0 <= k <= n:
        raise ValueError('invalid binomial counts')
    if not math.isfinite(p0) or not 0 <= p0 <= 1:
        raise ValueError('invalid binomial probability')
    if k == 0 or p0 == 1:
        return 1.0
    if p0 == 0:
        return 0.0
    log_success = math.log(p0)
    log_failure = math.log1p(-p0)
    complement = k <= n * p0
    start, stop = (0, k) if complement else (k, n + 1)
    log_term = (math.lgamma(n + 1) - math.lgamma(start + 1)
                - math.lgamma(n - start + 1)
                + start * log_success + (n - start) * log_failure)
    log_total = -math.inf
    for index in range(start, stop):
        largest = max(log_total, log_term)
        log_total = largest + math.log1p(math.exp(-abs(log_total - log_term)))
        if index < stop - 1:
            log_term += (math.log(n - index) - math.log(index + 1)
                         + log_success - log_failure)
    probability = -math.expm1(min(0.0, log_total)) if complement else math.exp(min(0.0, log_total))
    return min(1.0, max(0.0, probability))
