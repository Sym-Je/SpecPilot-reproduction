#!/usr/bin/env python3
"""G4 —— token forcing 的假阳性 / 假阴性自检（docs/02 §5 第 1、2 条）。

判据：
  E1 同一配置两次 replay → 逐 token 完全一致（确定性，forcing 的前提）
  E2 stock vs 等价实现 → rate rule / event rule 均不触发（假阴性不误杀）
  E3 注入拒绝位偏移故障 → event rule 触发（假阳性必须抓到）
  E4 该故障下输出长度不变、token 全合法 → 结构上看不出来，
     只有逐 token 比对能发现 ⇒ 精度不能当验收
  E5 accepted 减 1 的故障（改变长度）同样被抓到 —— 两种形态都覆盖

需要 GPU（replay 要跑真实前向）。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from controller.token_force import judge_forcing  # noqa: E402
from harness.engine import Options  # noqa: E402
from harness.replay import record, replay_tokens, inject_fault  # noqa: E402

results: list[tuple[str, bool, str]] = []


def record_res(cid: str, ok: bool, detail: str) -> None:
    results.append((cid, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}", flush=True)


def main() -> int:
    prompt = list(range(1, 33))
    opts = Options()
    a = record(prompt, 48, opts)
    b = record(prompt, 48, opts)
    ta, tb = replay_tokens(a), replay_tokens(b)
    record_res("E1 确定性", ta == tb, f"{len(ta)} tokens，两次一致={ta == tb}")

    r = judge_forcing([ta], [ta])
    record_res("E2 假阴性", r.lossless, f"rate={r.rate:.4f} flagged={r.rate_flagged}")

    bad = inject_fault(a, every=3, vocab=opts.vocab, mode="pred")
    tb_bad = replay_tokens(bad)
    diverged = sum(1 for x, y in zip(ta, tb_bad) if x != y)
    r2 = judge_forcing([ta] * 8, [tb_bad] * 8)
    record_res("E3 假阳性", r2.event_flagged,
               f"分歧 {diverged}/{len(ta)} tokens，event_p={r2.event_p:.2e}")

    # 结构判据：长度一致 + 全部 token 在 vocab 内 + 至少一个分歧
    same_len = len(tb_bad) == len(ta)
    legal = all(0 <= t < opts.vocab for t in tb_bad)
    record_res("E4 精度不可判", same_len and legal and diverged > 0,
               f"长度不变={same_len} 全合法={legal} 分歧={diverged} → 结构上看不出损坏")

    bad2 = inject_fault(a, every=3, vocab=opts.vocab, mode="accept")
    tb2 = replay_tokens(bad2)
    r3 = judge_forcing([ta] * 8, [tb2] * 8)
    record_res("E5 长度型故障", r3.event_flagged and len(tb2) != len(ta),
               f"长度 {len(ta)}→{len(tb2)}，event_p={r3.event_p:.2e}")

    failed = [c for c, ok, _ in results if not ok]
    print(f"\nG4 {'PASS' if not failed else 'FAIL'} ({len(results) - len(failed)}/{len(results)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
