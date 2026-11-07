"""Qwen3 上的投机解码引擎。

option 语义与 harness/engine.py（TinyLM 版）一致，只是换成真实权重：

  block_verify=False  → stock：线性链 + 逐 token 验证（DFlash 式块内逐位置判）
  block_verify=True   → 批验证：候选块一次前向算完（用 block 换 launch 次数）

唯一不变量：**target 与 draft 的 KV 长度都等于 prompt+已提交 token 数**。
位置一律由 cache.n 推出（forward(offset=None)）。上一版手工维护 _dpos 并与
append 混用，导致 draft KV 与 target 错位；这里改成「提议后回滚 + 重放提交块」。

无损性：每个提交的 token 都是 target 的贪心 argmax。draft 提议被采用 iff 与
target argmax 相同，第一处不一致由 target 的 argmax 顶上。所以输出序列必然
与纯 AR 贪心逐 token 相同 —— 这是 token forcing 要守住的性质。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

import torch

from harness.qwen_backend import KV, QwenModel


@dataclass
class SpecOptions:
    block: int = 8              # stock=8，对齐上游 DFlash2 的 block size
    block_verify: bool = False  # stock=False：逐 token 验证
    device: str = "cuda:0"


@dataclass
class SpecResult:
    tokens: list[int]
    tokens_per_s: float
    tau: float
    proposed: int
    accepted: int
    tgt_forwards: int
    tgt_tokens: int
    draft_forwards: int
    wall_s: float
    prefill_s: float

    def to_json(self) -> str:
        import json
        return json.dumps(asdict(self), ensure_ascii=False)


class SpecEngine:
    def __init__(self, tgt: QwenModel, draft: QwenModel, opts: SpecOptions):
        self.tgt, self.draft, self.o = tgt, draft, opts
        self.dev = opts.device

    @torch.no_grad()
    def _propose(self, n: int) -> list[int]:
        """从 draft 当前状态（KV = 已提交前缀）提出 n 个候选。

        draft 的 KV 会被推进 n 个位置；调用方必须记录提议前的位置以便回滚。
        """
        dc = self._dc
        out, logits = [], self._dlog
        for _ in range(n):
            tok = int(logits[0].argmax())
            out.append(tok)
            logits = self.draft.forward(torch.tensor([[tok]], device=self.dev), dc)[:, -1, :]
        self._dlog = logits
        return out

    @torch.no_grad()
    def _verify_per_token(self, cand: list[int]) -> tuple[int, int]:
        """逐 token 验证。返回 (命中数, target 前向次数)。

        关键：命中 i 个后 target KV 停在 base+i。第一处失配时，bonus 必须是
        **给定已接受前缀**的 target argmax，也就是被拒之前那个 logits——
        不能拿「喂入被拒 token 之后」的 logits，那等于用了 target 不该看到的上下文。
        """
        tc = self._tc
        base = tc[0].n
        logits, acc, fwd = self._tlog, 0, 0
        for i, tok in enumerate(cand):
            if int(logits[0].argmax()) != tok:
                for c in tc:
                    c.truncate(base + i)
                self._tlog = logits                 # 被拒之前的预测 = 正确的 bonus
                return i, fwd
            logits = self.tgt.forward(torch.tensor([[tok]], device=self.dev), tc)[:, -1, :]
            fwd += 1
            acc += 1
        self._tlog = logits
        return acc, fwd

    @torch.no_grad()
    def _verify_batched(self, cand: list[int]) -> tuple[int, int]:
        """批验证：候选块一次前向。

        _tlog 判 cand[0]；喂进去以后位置 base+i 的输出判 cand[i+1]。
        命中 acc 个后回滚到 base+acc，并把最后一个可用 logits 留到下一步。
        """
        tc = self._tc
        base = tc[0].n
        lg = self.tgt.forward(torch.tensor([cand], device=self.dev), tc)
        preds = lg[0].argmax(-1)
        acc = 0
        if int(self._tlog[0].argmax()) == cand[0]:
            acc = 1
            while acc < len(cand) and int(preds[acc - 1]) == cand[acc]:
                acc += 1
        # 留下的必须是**整行 logits**，不是 argmax 之后的 token id：
        # 下一轮要 argmax 它来判下一个候选，喂 token id 进去会恒得到 0。
        if acc > 0:
            self._tlog = lg[0, acc - 1:acc]
        for c in tc:
            c.truncate(base + acc)
        return acc, 1

    @torch.no_grad()
    def generate(self, prompt: list[int], max_new: int) -> SpecResult:
        o = self.o
        self._prompt = prompt
        self._tc = [KV() for _ in self.tgt.layers]
        self._dc = [KV() for _ in self.draft.layers]
        p = torch.tensor([prompt], device=self.dev)

        torch.cuda.synchronize()
        t0 = time.perf_counter()
        self._tlog = self.tgt.forward(p, self._tc)[:, -1, :]
        self._dlog = self.draft.forward(p, self._dc)[:, -1, :]
        # 首个 token 由 prompt 的 logits 取得，必须显式送进两边，否则 KV 恒少一个
        first = torch.tensor([[int(self._tlog[0].argmax())]], device=self.dev)
        self._tlog = self.tgt.forward(first, self._tc)[:, -1, :]
        self._dlog = self.draft.forward(first, self._dc)[:, -1, :]
        torch.cuda.synchronize()
        prefill = time.perf_counter() - t0

        out = [int(first[0, 0])]
        proposed = accepted = tf = tt = df = 0
        torch.cuda.synchronize()
        t1 = time.perf_counter()

        while len(out) < max_new:
            n = min(o.block, max_new - len(out))
            dpos = self._dc[0].n
            cand = self._propose(n)
            df += n
            proposed += n
            if o.block_verify:
                acc, f = self._verify_batched(cand)
            else:
                acc, f = self._verify_per_token(cand)
            tf += f
            tt += n
            accepted += acc
            self._commit(out, cand, acc, dpos, max_new)
            if len(out) >= max_new:
                break

        torch.cuda.synchronize()
        wall = time.perf_counter() - t1
        n_out = len(out) - 1
        return SpecResult(out, n_out / wall if wall else 0.0,
                          accepted / proposed if proposed else 0.0,
                          proposed, accepted, tf, tt, df, wall, prefill)

    @torch.no_grad()
    def _commit(self, out, cand, acc, dpos, max_new):
        """提交 acc 个候选 + 1 个 target bonus，把两边 KV 拉回同一长度。

        draft 在提议阶段自己前进了 n 个位置，这里回滚到 dpos 再重放提交块；
        target 停在 base+acc（验证阶段已回滚）。之后两边都等于
        prompt + 已提交数 —— 这是全引擎唯一的不变量。
        """
        tc, dc = self._tc, self._dc
        bonus = int(self._tlog[0].argmax())
        new = cand[:acc] + [bonus]

        self._tlog = self.tgt.forward(
            torch.tensor([[bonus]], device=self.dev), tc)[:, -1, :]

        for c in dc:
            c.truncate(dpos)
        self._dlog = self.draft.forward(
            torch.tensor([new], device=self.dev), dc)[:, -1, :]

        committed = len(out) + len(new)      # KV 里真实存在的 token 数（不含 prompt）
        room = max_new - len(out)
        out.extend(new[:room])               # 输出按 max_new 截断，KV 不截断
        self._committed = committed
        want = len(self._prompt) + committed
        assert tc[0].n == want, ("target KV misaligned", tc[0].n, want)
        assert dc[0].n == want, ("draft KV misaligned", dc[0].n, want)
