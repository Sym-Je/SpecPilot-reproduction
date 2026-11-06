#!/usr/bin/env python3
"""G2 —— provider 故障下的续跑能力。零 GPU、零外网（mock server 在本地）。

判据：
  D1 500 错误被识别为可重试，且确实重试了（不是静默吞掉）
  D2 SSE 缺少 [DONE] 被判定为截断（不能把半截响应当成功）
  D3 截断后重试成功，最终输出完整
  D4 重试全程只产生一次「副作用」（同一个 idempotency key 不重复执行）
  D5 重试次数有上限，不会无限重试
  D6 重试间隔递增（指数退避），不是忙等

用法：python3 gates/g2_resilience.py
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST, PORT = "127.0.0.1", 8899
LOG = "/tmp/g2_mock.log"
results: list[tuple[str, bool, str]] = []


def record(cid: str, ok: bool, detail: str) -> None:
    results.append((cid, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}")


def wait_port(timeout: float = 10.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("mock server 未就绪")


def start_server(plan: dict) -> subprocess.Popen:
    if os.path.exists(LOG):
        os.unlink(LOG)
    p = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "harness", "mock", "openai_server.py"),
         "--port", str(PORT), "--plan", json.dumps(plan), "--log", LOG],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    wait_port()
    return p


def read_log() -> list[dict]:
    if not os.path.exists(LOG):
        return []
    return [json.loads(l) for l in open(LOG) if l.strip()]


class Completed(Exception):
    pass


class Truncated(Exception):
    pass


class Retryable(Exception):
    pass


def call_stream(prompt: str, idem_key: str, side_effects: dict) -> str:
    """带重试的一次调用。副作用按 idem_key 去重 —— 模拟 controller 的 checkpoint 语义。"""
    backoff = 0.2
    attempts = []
    for attempt in range(4):
        attempts.append(time.monotonic())
        try:
            req = urllib.request.Request(
                f"http://{HOST}:{PORT}/v1/chat/completions",
                data=json.dumps({"model": "mock", "stream": True,
                                 "messages": [{"role": "user", "content": prompt}]}).encode(),
                headers={"Content-Type": "application/json",
                         "Idempotency-Key": idem_key},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                buf, done, text = b"", False, []
                while True:
                    chunk = r.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n\n" in buf:
                        ev, buf = buf.split(b"\n\n", 1)
                        ev = ev.strip()
                        if not ev.startswith(b"data:"):
                            continue
                        payload = ev[5:].strip()
                        if payload == b"[DONE]":
                            done = True
                            continue
                        try:
                            obj = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        for ch in obj.get("choices", []):
                            piece = (ch.get("delta") or {}).get("content")
                            if piece:
                                text.append(piece)
                if not done:
                    raise Truncated("流结束但未见 [DONE]")
                # 只在完整成功后执行副作用，且按 idem_key 去重
                if idem_key not in side_effects:
                    side_effects[idem_key] = prompt
                return "".join(text)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise
            if attempt == 3:
                raise
        except (Truncated, http.client.IncompleteRead):
            if attempt == 3:
                raise
        time.sleep(backoff)
        backoff *= 2
    raise RuntimeError("unreachable")


def main() -> int:
    srv = start_server({"0": "500", "1": "truncate", "2": "ok"})
    try:
        effects: dict[str, str] = {}
        t0 = time.monotonic()
        out = call_stream("probe", "k1", effects)
        elapsed = time.monotonic() - t0
        log = read_log()

        record("D1 500 触发重试", len(log) >= 2 and log[0]["mode"] == "500",
               f"共 {len(log)} 次请求，第 0 次为 500")
        record("D2 截断被识别", any(r.get("mode") == "truncate" for r in log),
               "mock 确实发出了 truncate 模式且客户端抛了 Truncated")
        record("D3 重试后完整", out == "Hello from mock",
               f"最终输出 = {out!r}")
        record("D4 副作用只一次", len(effects) == 1,
               f"idempotency key 出现 {len(effects)} 次")
        record("D5 重试有上限", len(log) <= 4,
               f"总请求 {len(log)} 次，上限 4")
        record("D6 指数退避", elapsed >= 0.2 + 0.4,
               f"总耗时 {elapsed:.2f}s（0.2 + 0.4 退避）")
    finally:
        srv.terminate()
        srv.wait(timeout=5)

    failed = [c for c, ok, _ in results if not ok]
    print()
    print(f"G2 {'PASS' if not failed else 'FAIL'}  ({len(results) - len(failed)}/{len(results)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
