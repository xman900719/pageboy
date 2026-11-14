#!/usr/bin/env python3
"""
书童日常开发环境一键管理脚本（后端 8000 + Vite 热重载 5173 + 隔离开发凭据）。

职责：
1. init-env      - 在 pageboy-home/development/env/dev.env 初始化或校验独立开发令牌，
                   并同步写入已被 Git 忽略的 apps/web/.env.development.local（仅 vite dev 读取）。
2. start         - 自动执行 init-env 与数据库迁移后，以 127.0.0.1 回环地址启动后端与 Vite dev。
3. stop          - 优雅停止开发环境进程，释放 8000 与 5173 端口。
4. status        - 检查服务端口与开发凭据文件状态。
5. sim           - 打开 iPadOS 竖屏 (810×1080) 模拟机窗口直连开发前端。
6. sim-landscape - 打开 iPadOS 横屏 (1080×810) 模拟机窗口直连开发前端。
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "services" / "api"
WEB_DIR = REPO_ROOT / "apps" / "web"

PAGEBOY_HOME = Path(os.getenv("PAGEBOY_HOME", "/media/xc/backup_ext4/pageboy-home")).expanduser().resolve()
DEV_HOME = PAGEBOY_HOME / "development"
DEV_ENV_DIR = DEV_HOME / "env"
DEV_ENV_FILE = DEV_ENV_DIR / "dev.env"
WEB_DEV_ENV_FILE = WEB_DIR / ".env.development.local"
RUN_DIR = DEV_HOME / "run"
LOG_DIR = DEV_HOME / "logs"
PID_FILE = RUN_DIR / "dev_env.json"

API_PORT = int(os.getenv("SHUTONG_DEV_API_PORT", "8000"))
WEB_PORT = int(os.getenv("SHUTONG_DEV_WEB_PORT", "5173"))


def is_port_in_use(port: int) -> bool:
    """检查本地回环端口是否已被占用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_http(url: str, timeout: float = 30.0) -> bool:
    """等待本地 HTTP 端口就绪。"""
    start = time.time()
    req = Request(url)
    while time.time() - start < timeout:
        try:
            with urlopen(req, timeout=1.0) as res:
                if 200 <= res.status < 400:
                    return True
        except (URLError, TimeoutError, ConnectionResetError):
            pass
        time.sleep(0.3)
    return False


def parse_env_file(path: Path) -> dict[str, str]:
    """解析 KEY=VALUE 格式的本地环境文件。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        cleaned_key = key.strip()
        cleaned_val = val.strip().strip('"').strip("'")
        if cleaned_key:
            values[cleaned_key] = cleaned_val
    return values


def write_secure_env_file(path: Path, lines: list[str]) -> None:
    """以 0600 权限写入环境文件，防止同机其他用户读取开发凭据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def ensure_dev_env() -> dict[str, str]:
    """确保 dev.env 与 apps/web/.env.development.local 存在且包含独立的双端开发令牌。"""
    if not DEV_HOME.is_dir():
        raise RuntimeError(f"开发 Home 目录不存在：{DEV_HOME}")

    DEV_ENV_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DEV_ENV_DIR, 0o700)

    env_map = parse_env_file(DEV_ENV_FILE)
    env_map["PAGEBOY_HOME"] = str(PAGEBOY_HOME)
    env_map["SHUTONG_ENV"] = "development"

    student_token = env_map.get("SHUTONG_STUDENT_TOKEN", "").strip()
    admin_token = env_map.get("SHUTONG_ADMIN_TOKEN", "").strip()

    if not student_token:
        student_token = f"dev-student-{secrets.token_urlsafe(18)}"
    if not admin_token or admin_token == student_token:
        admin_token = f"dev-admin-{secrets.token_urlsafe(18)}"

    env_map["SHUTONG_STUDENT_TOKEN"] = student_token
    env_map["SHUTONG_ADMIN_TOKEN"] = admin_token

    ordered_keys = [
        "PAGEBOY_HOME",
        "SHUTONG_ENV",
        "SHUTONG_STUDENT_TOKEN",
        "SHUTONG_ADMIN_TOKEN",
    ]
    extra_keys = sorted(k for k in env_map if k not in ordered_keys)
    dev_lines = [
        "# 书童本地开发环境配置（仅开发态生效，严禁提交至 Git）",
        *(f"{k}={env_map[k]}" for k in ordered_keys),
        *(f"{k}={env_map[k]}" for k in extra_keys),
    ]
    write_secure_env_file(DEV_ENV_FILE, dev_lines)

    web_lines = [
        "# 由 scripts/run_dev_env.py 从 pageboy-home/development/env/dev.env 自动同步",
        "# 已被 .gitignore 忽略且仅 Vite dev 模式读取，npm run build 生产构建不加载此文件",
        f"VITE_DEV_STUDENT_TOKEN={student_token}",
        f"VITE_DEV_ADMIN_TOKEN={admin_token}",
    ]
    write_secure_env_file(WEB_DEV_ENV_FILE, web_lines)
    return env_map


def init_env_cmd() -> int:
    """仅初始化并同步开发环境凭据文件。"""
    env_map = ensure_dev_env()
    print("✅ 开发环境学生端与管理端令牌已就绪（仅保存在本地受保护目录）：")
    print(f"   - 后端配置：{DEV_ENV_FILE} (0600)")
    print(f"   - 前端配置：{WEB_DEV_ENV_FILE} (0600，仅 vite dev 生效)")
    print(f"   - 学生令牌长度：{len(env_map['SHUTONG_STUDENT_TOKEN'])}，管理令牌长度：{len(env_map['SHUTONG_ADMIN_TOKEN'])}")
    return 0


def start_env() -> int:
    """启动本地日常开发环境（后端 8000 + Vite dev 5173）。"""
    if is_port_in_use(API_PORT):
        print(f"❌ 错误：后端端口 {API_PORT} 已被占用，请先执行 `stop` 或排查残留进程。")
        return 1
    if is_port_in_use(WEB_PORT):
        print(f"❌ 错误：前端端口 {WEB_PORT} 已被占用，请先执行 `stop` 或排查残留进程。")
        return 1

    dev_vars = ensure_dev_env()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    proc_env = os.environ.copy()
    proc_env.update(dev_vars)

    print("📦 正在检查并升级开发数据库迁移 (alembic upgrade head)...")
    mig = subprocess.run(
        ["uv", "--directory", str(API_DIR), "run", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=proc_env,
        capture_output=True,
        text=True,
    )
    if mig.returncode != 0:
        print(f"❌ 数据库迁移失败：\n{mig.stderr or mig.stdout}")
        return 1

    api_log_path = LOG_DIR / "dev-api.log"
    web_log_path = LOG_DIR / "dev-web.log"

    print(f"🌐 正在启动本地开发后端 (127.0.0.1:{API_PORT})...")
    with open(api_log_path, "w", encoding="utf-8") as api_log:
        api_proc = subprocess.Popen(
            [
                "uv",
                "run",
                "uvicorn",
                "shutong.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(API_PORT),
                "--reload",
                "--reload-dir",
                "shutong",
            ],
            cwd=API_DIR,
            env=proc_env,
            stdin=subprocess.DEVNULL,
            stdout=api_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    if not wait_for_http(f"http://127.0.0.1:{API_PORT}/health/live", timeout=20.0):
        print(f"❌ 后端开发服务启动超时，请查看日志：{api_log_path}")
        _terminate_pg(api_proc.pid)
        return 1

    print(f"🎨 正在启动本地前端 Vite dev 服务 (127.0.0.1:{WEB_PORT})...")
    web_env = proc_env.copy()
    web_env["API_PROXY_TARGET"] = f"http://127.0.0.1:{API_PORT}"
    with open(web_log_path, "w", encoding="utf-8") as web_log:
        web_proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT), "--strictPort"],
            cwd=WEB_DIR,
            env=web_env,
            stdin=subprocess.DEVNULL,
            stdout=web_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    if not wait_for_http(f"http://127.0.0.1:{WEB_PORT}/", timeout=20.0):
        print(f"❌ 前端 Vite dev 服务启动超时，请查看日志：{web_log_path}")
        _terminate_pg(web_proc.pid)
        _terminate_pg(api_proc.pid)
        return 1

    PID_FILE.write_text(
        json.dumps(
            {
                "api_pid": api_proc.pid,
                "web_pid": web_proc.pid,
                "api_port": API_PORT,
                "web_port": WEB_PORT,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.chmod(PID_FILE, 0o600)

    print("==================================================================")
    print("✅ 书童开发环境已在宿主机回环地址就绪！（支持学生端/管理端自动登录）")
    print(f"📱 学生端入口：http://127.0.0.1:{WEB_PORT}/")
    print(f"🖥️ 管理端入口：http://127.0.0.1:{WEB_PORT}/admin.html")
    print(f"🔑 凭据配置：  {DEV_ENV_FILE}")
    print(f"📄 运行日志：  {api_log_path} | {web_log_path}")
    print("==================================================================")
    print("提示：点击页面右上角「退出」仍可回到令牌门进行人工测试。")
    print("停止命令：uv run python scripts/run_dev_env.py stop")
    return 0


def _terminate_pg(pid: int) -> None:
    """按进程组优雅终止后台子进程。"""
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass


def stop_env() -> int:
    """停止开发环境后台进程。"""
    print("🛑 正在停止书童日常开发环境...")
    if PID_FILE.exists():
        try:
            data = json.loads(PID_FILE.read_text(encoding="utf-8"))
            for key in ("web_pid", "api_pid"):
                pid = data.get(key)
                if isinstance(pid, int):
                    _terminate_pg(pid)
        finally:
            PID_FILE.unlink(missing_ok=True)
        time.sleep(0.8)
    else:
        print("⚠️ 未发现 dev_env.json，检查端口状态...")

    for port in (API_PORT, WEB_PORT):
        if is_port_in_use(port):
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)

    print("✅ 日常开发环境已停止。")
    return 0


def status_env() -> int:
    """检查日常开发环境运行状态与凭据配置情况。"""
    api_live = is_port_in_use(API_PORT)
    web_live = is_port_in_use(WEB_PORT)
    dev_env_ok = DEV_ENV_FILE.is_file()
    web_env_ok = WEB_DEV_ENV_FILE.is_file()
    print("==================================================================")
    print("🔍 书童日常开发环境状态")
    print("==================================================================")
    print(f"后端凭据 ({DEV_ENV_FILE}): {'🟢 已配置' if dev_env_ok else '🔴 缺失'}")
    print(f"前端凭据 ({WEB_DEV_ENV_FILE}): {'🟢 已同步' if web_env_ok else '🔴 缺失'}")
    print(f"后端 API (127.0.0.1:{API_PORT}): {'🟢 在线' if api_live else '🔴 离线'}")
    print(f"前端 Vite dev (127.0.0.1:{WEB_PORT}): {'🟢 在线' if web_live else '🔴 离线'}")
    print("==================================================================")
    return 0 if (dev_env_ok and web_env_ok and api_live and web_live) else 1


def open_sim(landscape: bool = False) -> int:
    """在宿主机桌面打开 iPadOS 模拟机窗口直连开发前端。"""
    if not is_port_in_use(WEB_PORT) or not is_port_in_use(API_PORT):
        if start_env() != 0:
            return 1
    device_name = "iPad (gen 7) landscape" if landscape else "iPad (gen 7)"
    res = subprocess.run(
        ["npx", "playwright", "open", f"--device={device_name}", f"http://127.0.0.1:{WEB_PORT}"],
        cwd=WEB_DIR,
    )
    return res.returncode


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "init-env":
        sys.exit(init_env_cmd())
    if action == "start":
        sys.exit(start_env())
    if action == "stop":
        sys.exit(stop_env())
    if action == "status":
        sys.exit(status_env())
    if action in ("sim", "sim-portrait"):
        sys.exit(open_sim(landscape=False))
    if action in ("sim-landscape",):
        sys.exit(open_sim(landscape=True))
    print(f"未知子命令: {action}。支持: init-env | start | stop | status | sim | sim-landscape")
    sys.exit(2)


if __name__ == "__main__":
    main()
