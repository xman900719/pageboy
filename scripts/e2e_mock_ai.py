"""Playwright E2E 专用的本地 OpenAI 兼容模拟服务端，支持苏格拉底错题引导端到端验证。"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockAiHandler(BaseHTTPRequestHandler):
    """拦截 /v1/chat/completions 与 /health，返回绝不直接给出答案的引导提示。"""

    def log_message(self, format: str, *args) -> None:
        return None

    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path in ("/v1/chat/completions", "/chat/completions"):
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            messages = payload.get("messages") or []
            user_turns = [m for m in messages if m.get("role") == "user"]
            assistant_turns = [m for m in messages if m.get("role") == "assistant"]
            if len(assistant_turns) == 0:
                content = "我们先不急着下结论。你能先指出题干里哪个已知条件决定了这道题的方向吗？"
            else:
                last_msg = str((user_turns[-1] if user_turns else {}).get("content") or "")[:24]
                content = f"你刚才提到「{last_msg}」，思路很对！沿着这个条件继续核对，哪个关键词与你的作答矛盾？"

            body = json.dumps(
                {
                    "id": "chatcmpl-e2e-mock",
                    "object": "chat.completion",
                    "model": payload.get("model") or "deepseek-chat-mock",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    port = int(os.getenv("E2E_MOCK_AI_PORT", "18766"))
    server = ThreadingHTTPServer(("127.0.0.1", port), MockAiHandler)
    server.serve_forever()
