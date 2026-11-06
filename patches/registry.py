"""机制注册表：每个机制 = 一个 option + 一个默认值 + 一个 hook。

铁律 3：默认值必须复现 stock。registry 负责保证这一点 —— controller 在测量前
用 `assert_stock_defaults()` 校验，任何把默认值改掉的提交直接拒绝进入测量。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 与 harness/engine.py:Options 保持一致
STOCK = {
    "tree_width": 1,
    "tree_depth": 4,
    "block_verify": False,
    "draft_layers": 1,
}


@dataclass
class Mechanism:
    name: str
    option: str
    stock: object
    candidate: object
    factor: str            # tau / overhead / kernel
    hypothesis: str
    author: str = "unknown"
    enabled: bool = False

    def as_options(self) -> dict:
        return {self.option: self.candidate}


@dataclass
class Registry:
    items: list[Mechanism] = field(default_factory=list)

    def add(self, m: Mechanism) -> None:
        if m.option not in STOCK:
            raise ValueError(f"未知 option: {m.option}")
        if STOCK[m.option] != m.stock:
            raise ValueError(f"{m.name}: stock 值 {m.stock!r} 与基线 {STOCK[m.option]!r} 不一致")
        self.items.append(m)

    def assert_stock_defaults(self, current: dict) -> None:
        """测量前必须调用：确认当前引擎默认值仍是 stock。"""
        for k, v in STOCK.items():
            if k in current and current[k] != v:
                raise AssertionError(f"默认值被改：{k} = {current[k]!r}，应为 {v!r}")

    def by_factor(self, factor: str) -> list[Mechanism]:
        return [m for m in self.items if m.factor == factor]


def default_registry() -> Registry:
    r = Registry()
    r.add(Mechanism(
        name="batch-verify", option="block_verify", stock=False, candidate=True,
        factor="overhead",
        hypothesis="逐 token 验证改为一次前向批验证，验证开销从 O(depth) 降到 O(1)",
    ))
    r.add(Mechanism(
        name="deeper-draft", option="draft_layers", stock=1, candidate=3,
        factor="tau",
        hypothesis="加深 draft 提升 top-1 一致率，tau 上升但每步成本也上升",
    ))
    r.add(Mechanism(
        name="longer-chain", option="tree_depth", stock=4, candidate=8,
        factor="tau",
        hypothesis="更长的候选链摊薄 verify 次数；受接受率衰减限制",
    ))
    return r
