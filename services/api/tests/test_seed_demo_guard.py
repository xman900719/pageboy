"""环境隔离：seed_demo.py 对自报 env=prod 的目标必须拒绝写入（仅用本地假服务，不触碰任何真实环境）。"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SEED = Path(__file__).resolve().parents[3] / "scripts" / "seed_demo.py"


def _run_seed(env_value, *, approved=True):
    posts = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"status": "alive", "env": env_value} if env_value else {"status": "alive"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            posts.append(self.path)
            self.send_response(500)  # 立即失败，避免真正灌数据
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = dict(os.environ, SHUTONG_TOKEN="t", SHUTONG_API_URL=f"http://127.0.0.1:{server.server_port}")
        if approved:
            env["PAGEBOY_OWNER_TEST_DATA_APPROVED"] = "1"
            env["PAGEBOY_OWNER_APPROVAL_REF"] = "test-owner-approval"
        result = subprocess.run([sys.executable, str(SEED)], env=env, capture_output=True, text=True, timeout=30)
    finally:
        server.shutdown()
    return result, posts


def test_seed_refuses_prod_target():
    result, posts = _run_seed("prod")
    assert result.returncode != 0 and "env=prod" in result.stderr
    assert posts == []  # 一次写请求都不得发出


def test_seed_proceeds_on_non_prod_target():
    result, posts = _run_seed("test")
    assert posts, "非生产目标应进入写入流程（假服务返回 500 使其立即中止）"


def test_seed_requires_owner_test_data_approval():
    result, posts = _run_seed("test", approved=False)
    assert result.returncode != 0
    assert "拒绝写入开发环境虚构测试数据" in result.stderr
    assert posts == []
