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
            joined_prompt = "\n".join(str(m.get("content") or "") for m in messages)
            if "root_cause_summary" in joined_prompt and "cognitive_gap_type" in joined_prompt:
                content = json.dumps(
                    {
                        "cognitive_gap_type": "condition_omission",
                        "root_cause_summary": "学生在审题阶段忽略了题干的限定条件，未先列出已知约束就直接套用直觉选项。",
                        "evidence_from_dialogue": "在多轮引导第 2 轮中经提示后才明确指出题干里的关键实数条件。",
                        "solutions": [
                            {
                                "option_id": "opt_1",
                                "title": "题干限定条件圈画三步法",
                                "approach_focus": "审题与条件提取",
                                "rationale": "强迫动笔前先提取限制范围，减少漏看。",
                                "action_steps": ["读题先圈出数值域与限定词", "在草稿纸列出未知数约束后再计算"],
                            },
                            {
                                "option_id": "opt_2",
                                "title": "选项逐项反代检验训练",
                                "approach_focus": "概念与验证纠偏",
                                "rationale": "通过反向代入验证能快速发现与题意冲突的选项。",
                                "action_steps": ["做完选择题后把结果代回原条件检验", "核对是否有边界反例"],
                            },
                            {
                                "option_id": "opt_3",
                                "title": "同类易漏条件变式对比练",
                                "approach_focus": "变式迁移巩固",
                                "rationale": "对比仅改变限定条件的题组能固化条件敏感度。",
                                "action_steps": ["连续完成 3 道条件微调的同类题", "口述每道题结论变化原因"],
                            },
                        ],
                    },
                    ensure_ascii=False,
                )
            elif len(assistant_turns) == 0:
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
