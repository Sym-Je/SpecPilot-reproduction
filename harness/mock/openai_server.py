"""最小 OpenAI-compatible mock server，带故障注入。

用途：G2 —— 验证编排层在 provider 故障（500 / SSE 中断 / 慢响应）下能否
依靠 checkpoint 续跑，而不是整轮重来或静默丢步。

故障计划用 JSON 字符串传入，按请求序号（从 0 起）匹配：
  {"0": "500", "1": "truncate", "2": "slow", "3": "ok"}

启动：
  python3 harness/mock/openai_server.py --port 8899 --plan '{"0":"500","1":"truncate"}'

每个请求都会追加到 --log 指定的 JSONL，便于事后核对重试次数与顺序。
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PLAN: dict[str, str] = {}
LOG_PATH: str | None = None
CALLS = {"n": 0}


def log(obj: dict) -> None:
    if LOG_PATH:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # 静默
        pass

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._send_json(200, {"object": "list", "data": [{"id": "mock-model", "object": "model"}]})
        else:
            self._send_json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        n = CALLS["n"]
        CALLS["n"] += 1
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length) or b"{}")
        mode = PLAN.get(str(n), "ok")
        log({"n": n, "mode": mode, "stream": bool(req.get("stream")), "messages": len(req.get("messages", []))})

        if mode == "500":
            self._send_json(500, {"error": {"message": "injected server error", "type": "server_error"}})
            return
        if mode == "slow":
            time.sleep(3)

        text = f"chunk-{n}"
        if not req.get("stream"):
            self._send_json(200, {
                "id": f"cmpl-{n}", "object": "chat.completion", "created": int(time.time()),
                "model": req.get("model", "mock-model"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(payload: str) -> None:
            data = payload.encode()
            self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
            self.wfile.flush()

        try:
            for piece in ("Hello", " from", " mock"):
                body = {"id": f"cmpl-{n}", "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                chunk(f"data: {json.dumps(body)}\n\n")
                time.sleep(0.05)
            if mode == "truncate":
                # 关键：不发 [DONE]，直接掐断连接
                log({"n": n, "event": "truncated"})
                self.wfile.flush()
                self.close_connection = True
                return
            chunk('data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n')
            chunk("data: [DONE]\n\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log({"n": n, "event": "client_gone"})


def main() -> None:
    global PLAN, LOG_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--plan", default="{}")
    ap.add_argument("--log", default=None)
    ns = ap.parse_args()
    PLAN = json.loads(ns.plan)
    LOG_PATH = ns.log
    srv = ThreadingHTTPServer(("127.0.0.1", ns.port), Handler)
    print(f"mock server on :{ns.port} plan={PLAN}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
