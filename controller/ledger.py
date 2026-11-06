"""append-only 测量账本，带哈希链。

铁律：只有 controller 进程能写。写入用 O_APPEND 单次 write，天然抗并发交错；
每条记录包含前一条的 sha256，任何回改或删除都会在 verify() 处断开。

记录字段（最小集）：
  seq      单调递增序号，必须等于前一条 + 1
  ts       ISO8601 UTC 写入时刻（controller 时钟，不是 agent 自报）
  kind     记录类型：measurement | promotion | rejection | memory | gate
  subject  被测对象（patch id / 条目 id / 闸门名）
  payload  结构化内容（数字、区间、证据指针）
  prev     前一条的 sha256（首条为 64 个 0）
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Iterator

GENESIS = "0" * 64


class LedgerError(RuntimeError):
    pass


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def record_hash(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(_canonical(body)).hexdigest()


@dataclass
class Ledger:
    path: str

    def __post_init__(self) -> None:
        d = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(d, exist_ok=True)

    # ---------- 写 ----------
    def append(self, kind: str, subject: str, payload: dict) -> dict:
        last = self._last()
        rec = {
            "seq": (last["seq"] + 1) if last else 0,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "kind": kind,
            "subject": subject,
            "payload": payload,
            "prev": last["hash"] if last else GENESIS,
        }
        rec["hash"] = record_hash(rec)
        line = json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        return rec

    # ---------- 读 ----------
    def __iter__(self) -> Iterator[dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        raise LedgerError(f"第 {i} 行不是合法 JSON: {e}") from e
        except FileNotFoundError:
            return

    def _last(self) -> dict | None:
        last = None
        for rec in self:
            last = rec
        return last

    def records(self) -> list[dict]:
        return list(self)

    def verify(self) -> list[str]:
        """返回问题列表，空列表表示链完整。"""
        problems: list[str] = []
        prev = GENESIS
        expect_seq = 0
        for rec in self:
            if rec.get("seq") != expect_seq:
                problems.append(f"seq 断裂：期望 {expect_seq}，实际 {rec.get('seq')}")
            if rec.get("prev") != prev:
                problems.append(f"seq {rec.get('seq')} 的 prev 不匹配前一条 hash")
            if record_hash(rec) != rec.get("hash"):
                problems.append(f"seq {rec.get('seq')} 内容被改动（hash 不符）")
            prev = rec.get("hash", "")
            expect_seq = (rec.get("seq") or 0) + 1
        return problems
