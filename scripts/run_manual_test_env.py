#!/usr/bin/env python3
"""
前端人工测试环境一键管理工具 (针对 iPadOS 模拟机环境)

功能：
1. start  - 一键建表、拉起后端(18765)、灌入完整种子数据、拉起前端预览(4173)并完成连通性探测。
2. stop   - 干净停止前后端后台测试进程，释放 18765 与 4173 端口。
3. status - 探测当前测试服务健康度与网络 IP。
4. sim           - 在宿主机桌面上直接弹出 iPad 竖屏 (810×1080) 触控模拟机窗口。
5. sim-landscape - 在宿主机桌面上直接弹出 iPad 横屏 (1080×810) 触控模拟机窗口。

执行契约：
- 宿主机运行前后端测试服务与自动化门禁；
- 前端人工核验在用于模拟 iPadOS 环境的模拟机中运行与操作。
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# 统一路径与临时目录配置
REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = Path("/tmp/opencode")
PID_FILE = TMP_DIR / "manual_test_env.json"
DB_FILE = TMP_DIR / "manual_test.sqlite3"
ATTACHMENTS_DIR = TMP_DIR / "manual_attachments"

API_PORT = 18765
WEB_PORT = 4173
TEST_TOKEN = "test-journey-secret"


def is_port_in_use(port: int) -> bool:
    """检查指定 TCP 端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_http(url: str, timeout: float = 30.0, headers: dict[str, str] | None = None) -> bool:
    """等待指定 HTTP 路径返回 200"""
    start = time.time()
    req = Request(url, headers=headers or {})
    while time.time() - start < timeout:
        try:
            with urlopen(req, timeout=1.0) as res:
                if 200 <= res.status < 400:
                    return True
        except (URLError, TimeoutError, ConnectionResetError):
            pass
        time.sleep(0.3)
    return False


def start_env() -> int:
    """一键拉起人工测试环境与数据"""
    print("==================================================================")
    print("🚀 正在启动书童前端人工测试环境 (面向 iPadOS 模拟机)...")
    print("==================================================================")

    # 1. 检查端口占用
    if is_port_in_use(API_PORT):
        print(f"❌ 错误：后端端口 {API_PORT} 已被占用，请先执行 `stop` 或检查残留进程。")
        return 1
    if is_port_in_use(WEB_PORT):
        print(f"❌ 错误：前端端口 {WEB_PORT} 已被占用，请先执行 `stop` 或检查残留进程。")
        return 1

    # 2. 准备目录与全新测试数据库
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    if DB_FILE.exists():
        DB_FILE.unlink()

    print("📦 正在初始化临时 SQLite 数据库并执行元数据建表...")
    init_db_cmd = [
        "uv", "run", "python", "-c",
        "import shutong.models; from shutong.database import Base, engine; Base.metadata.create_all(engine)"
    ]
    env_db = os.environ.copy()
    env_db["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
    res = subprocess.run(init_db_cmd, cwd=REPO_ROOT, env=env_db, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ 数据库建表失败：\n{res.stderr}")
        return 1

    # 3. 启动后端 API 服务
    print(f"🌐 正在启动后端 API 服务 (监听 127.0.0.1:{API_PORT})...")
    api_log_path = TMP_DIR / "manual_api.log"
    api_log_file = open(api_log_path, "w", encoding="utf-8")
    api_env = os.environ.copy()
    api_env["SHUTONG_TOKEN"] = TEST_TOKEN
    api_env["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
    api_env["SHUTONG_PRIVATE_DIR"] = str(ATTACHMENTS_DIR)
    api_env["SHUTONG_ENV"] = "test"

    api_proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "uvicorn", "shutong.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=REPO_ROOT,
        env=api_env,
        stdout=api_log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    if not wait_for_http(f"http://127.0.0.1:{API_PORT}/health/live", timeout=20.0):
        print("❌ 后端服务启动超时，请查看日志：/tmp/opencode/manual_api.log")
        stop_env()
        return 1

    # 4. 灌入完整测试种子数据
    print("🌱 正在灌入完备的测试种子数据 (单选/主观自评/听力/题源/目标)...")
    seed_script = """
import('./apps/web/e2e/global-setup.ts').then(async m => {
  await m.default({});
  console.log('SEED_DONE');
}).catch(err => {
  console.error(err);
  process.exit(1);
});
"""
    seed_res = subprocess.run(["node", "-e", seed_script], cwd=REPO_ROOT, capture_output=True, text=True)
    if seed_res.returncode != 0 or "SEED_DONE" not in seed_res.stdout:
        print(f"❌ 种子数据灌入失败：\n{seed_res.stderr}")
        stop_env()
        return 1

    # 5. 启动前端 Vite 生产预览 (绑定 127.0.0.1:4173，内置同源代理)
    print(f"🎨 正在启动前端预览服务 (监听 127.0.0.1:{WEB_PORT})...")
    web_log_path = TMP_DIR / "manual_web.log"
    web_log_file = open(web_log_path, "w", encoding="utf-8")
    web_env = os.environ.copy()
    web_env["API_PROXY_TARGET"] = f"http://127.0.0.1:{API_PORT}"

    web_proc = subprocess.Popen(
        ["npm", "run", "preview", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT)],
        cwd=REPO_ROOT / "apps" / "web",
        env=web_env,
        stdout=web_log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    if not wait_for_http(f"http://127.0.0.1:{WEB_PORT}/", timeout=15.0):
        print("❌ 前端服务启动超时，请查看日志：/tmp/opencode/manual_web.log")
        stop_env()
        return 1

    # 6. 保存进程信息
    pids = {"api_pid": api_proc.pid, "web_pid": web_proc.pid}
    PID_FILE.write_text(json.dumps(pids, indent=2), encoding="utf-8")

    # 7. 打印就绪信息与 iPadOS 模拟机操作入口
    print("==================================================================")
    print("✅ 测试服务已在宿主机就绪！（仅监听回环地址，真实 iPad 不可访问；iPad 只连生产）")
    print(f"📱 iPadOS 模拟机访问入口 (学生端):  http://127.0.0.1:{WEB_PORT}")
    print(f"🖥️ PC 桌面端访问入口 (管理端):     http://127.0.0.1:{WEB_PORT}/admin.html")
    print(f"🔑 测试有效访问令牌:              {TEST_TOKEN}")
    print("==================================================================")
    print("测试人可直接在用于模拟 iPadOS 环境的模拟机中打开上述链接进行操作。")
    print("测试完成后，运行 `uv run python scripts/run_manual_test_env.py stop` 停止环境。")
    return 0


def stop_env() -> int:
    """优雅停止人工测试环境"""
    print("🛑 正在停止书童前端测试环境...")
    if not PID_FILE.exists():
        print("⚠️ 未发现正在运行的测试环境记录文件。尝试按端口清理...")
    else:
        try:
            pids = json.loads(PID_FILE.read_text(encoding="utf-8"))
            for name, pid in pids.items():
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    print(f"  - 已向 {name} (PGID {pid}) 发送终止信号")
                except ProcessLookupError:
                    pass
                except Exception as e:
                    print(f"  - 停止进程 {pid} 警告: {e}")
        finally:
            PID_FILE.unlink(missing_ok=True)

    # 确保端口彻底释放
    time.sleep(1.0)
    for port in [API_PORT, WEB_PORT]:
        if is_port_in_use(port):
            print(f"⚠️ 端口 {port} 仍被占用，正在执行强制清理...")
            subprocess.run(f"fuser -k {port}/tcp", shell=True, capture_output=True)

    print("✅ 测试环境已完全停止，端口已清理释放。")
    return 0


def status_env() -> int:
    """检查测试环境状态与连通性"""
    api_live = is_port_in_use(API_PORT)
    web_live = is_port_in_use(WEB_PORT)

    print("==================================================================")
    print("🔍 书童前端人工测试环境状态检查 (iPadOS 模拟机通道)")
    print("==================================================================")
    print(f"后端 API (端口 {API_PORT}): {'🟢 在线' if api_live else '🔴 离线'}")
    print(f"前端 Web (端口 {WEB_PORT}): {'🟢 在线' if web_live else '🔴 离线'}")
    if web_live:
        print(f"iPadOS 模拟机访问 URL: http://127.0.0.1:{WEB_PORT}")
    print("==================================================================")
    return 0 if (api_live and web_live) else 1


def open_sim(landscape: bool = False) -> int:
    """在宿主机图形桌面上启动 iPadOS 模拟机交互窗口供测试人操作"""
    if not is_port_in_use(WEB_PORT):
        print("⚠️ 检测到测试服务尚未在线，正在自动启动服务环境...")
        if start_env() != 0:
            return 1

    device_name = "iPad (gen 7) landscape" if landscape else "iPad (gen 7)"
    orientation_label = "横屏 (Landscape: 1080 × 810)" if landscape else "竖屏 (Portrait: 810 × 1080)"

    print("==================================================================")
    print(f"📱 正在宿主机图形桌面上拉起 iPadOS 模拟机交互窗口 [{orientation_label}]...")
    print(f"   - 模拟设备规格: {device_name}")
    print(f"   - 交互模式:     触控模拟 (Touch Simulation) + iPadOS Safari UA")
    print(f"   - 页面访问地址: http://127.0.0.1:{WEB_PORT}")
    print(f"   - 测试有效令牌: {TEST_TOKEN}")
    print("==================================================================")
    print("💡 提示：")
    print("   - 窗口关闭后将自动返回控制台。")
    if not landscape:
        print("   - 若要测试横屏布局，可运行: `uv run python scripts/run_manual_test_env.py sim-landscape`")
    else:
        print("   - 若要测试竖屏布局，可运行: `uv run python scripts/run_manual_test_env.py sim`")
    print("==================================================================")

    cmd = [
        "npx", "playwright", "open",
        f"--device={device_name}",
        f"http://127.0.0.1:{WEB_PORT}",
    ]
    res = subprocess.run(cmd, cwd=REPO_ROOT / "apps" / "web")
    return res.returncode


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "start":
        sys.exit(start_env())
    elif action == "stop":
        sys.exit(stop_env())
    elif action == "status":
        sys.exit(status_env())
    elif action in ("sim", "open", "sim-portrait", "sim-v"):
        sys.exit(open_sim(landscape=False))
    elif action in ("sim-landscape", "sim-h", "sim-land"):
        sys.exit(open_sim(landscape=True))
    else:
        print(f"未知参数: {action}。支持: start | stop | status | sim | sim-landscape")
        sys.exit(2)


if __name__ == "__main__":
    main()
