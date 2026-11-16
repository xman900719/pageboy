#!/usr/bin/env python3
"""
书童日常开发环境一键管理脚本（后端 8000 + Vite 热重载 5173 + 隔离开发凭据）。

职责：
1. init-env      - 在 pageboy-home/development/env/dev.env 初始化或校验独立开发令牌（可选同时录入 DeepSeek API Key），
                   并同步写入已被 Git 忽略的 apps/web/.env.development.local（仅 vite dev 读取）。
2. config-ai     - 在 dev.env 中单独配置、从 Shell 导入或清理 DEEPSEEK_API_KEY / 模型参数（不改动既有双端令牌）。
3. start         - 自动执行 init-env 与数据库迁移后，以 127.0.0.1 回环地址启动后端与 Vite dev（自动透传 DeepSeek Key）。
4. stop          - 优雅停止开发环境进程，释放 8000 与 5173 端口。
5. status        - 检查服务端口、开发凭据与 DeepSeek AI 脱敏配置状态。
6. sim           - 打开 iPadOS 竖屏 (810×1080) 模拟机窗口直连开发前端。
7. sim-landscape - 打开 iPadOS 横屏 (1080×810) 模拟机窗口直连开发前端。
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from getpass import getpass
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
# 已删除的人工测试脚本遗留端口：仅提示，不自动杀进程，避免误伤其他服务。
LEGACY_TEST_PORTS = (18765, 4173)


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


_AI_ENV_KEYS = {
    "DEEPSEEK_API_KEY",
    "SHUTONG_AI_API_KEY",
    "SHUTONG_VISION_API_KEY",
    "DEEPSEEK_BASE_URL",
    "SHUTONG_AI_BASE_URL",
    "SHUTONG_VISION_BASE_URL",
    "SHUTONG_AI_MODEL",
    "SHUTONG_TEXT_ENRICH_MODEL",
    "SHUTONG_VISION_MODEL",
}


def _mask_secret(value: str) -> str:
    """仅返回密钥首尾脱敏摘要，避免明文写入终端。"""
    text = (value or "").strip()
    if not text:
        return "未配置"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-4:]}"


def _build_ai_updates(
    api_key: str = "",
    *,
    base_url: str = "",
    vision_model: str = "",
    text_model: str = "",
) -> dict[str, str]:
    """构造 DeepSeek 与书童 AI 统一开发环境变量更新映射。"""
    updates: dict[str, str] = {}
    cleaned_key = (api_key or "").strip()
    if cleaned_key:
        updates["DEEPSEEK_API_KEY"] = cleaned_key
        updates["SHUTONG_AI_API_KEY"] = cleaned_key
        updates["SHUTONG_VISION_API_KEY"] = cleaned_key
    cleaned_url = (base_url or "").strip().rstrip("/")
    if cleaned_url:
        if not cleaned_url.startswith(("http://", "https://")):
            raise ValueError("DeepSeek Base URL 必须以 http:// 或 https:// 开头")
        updates["DEEPSEEK_BASE_URL"] = cleaned_url
        updates["SHUTONG_AI_BASE_URL"] = cleaned_url
        updates["SHUTONG_VISION_BASE_URL"] = cleaned_url
    if (vision_model or "").strip():
        updates["SHUTONG_VISION_MODEL"] = vision_model.strip()
    if (text_model or "").strip():
        updates["SHUTONG_AI_MODEL"] = text_model.strip()
        updates["SHUTONG_TEXT_ENRICH_MODEL"] = text_model.strip()
    return updates


def _load_verified_user_k12100_ai_env() -> dict[str, str]:
    """在权限严格校验通过（dir 0700、file 0600、当前用户）时，读取开发环境 k12100.env 中的 AI 配置。"""
    cfg_dir = Path(os.getenv("SHUTONG_K12100_CONFIG_DIR", str(DEV_HOME / "k12100"))).expanduser().resolve()
    env_file = cfg_dir / "k12100.env"
    if not cfg_dir.is_dir() or not env_file.is_file():
        return {}
    uid = os.getuid()
    dir_st = cfg_dir.stat()
    file_st = env_file.stat()
    if dir_st.st_uid != uid or stat.S_IMODE(dir_st.st_mode) & 0o077 != 0:
        return {}
    if file_st.st_uid != uid or stat.S_IMODE(file_st.st_mode) & 0o077 != 0:
        return {}
    parsed = parse_env_file(env_file)
    return {k: v for k, v in parsed.items() if k in _AI_ENV_KEYS and v}


def ensure_dev_env(
    *,
    ai_updates: dict[str, str] | None = None,
    remove_keys: set[str] | None = None,
) -> dict[str, str]:
    """确保 dev.env 与 apps/web/.env.development.local 存在且包含独立的双端开发令牌。"""
    if not DEV_HOME.is_dir():
        raise RuntimeError(f"开发 Home 目录不存在：{DEV_HOME}")

    DEV_ENV_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DEV_ENV_DIR, 0o700)

    env_map = parse_env_file(DEV_ENV_FILE)
    for k in remove_keys or set():
        env_map.pop(k, None)
    for k, v in (ai_updates or {}).items():
        if v.strip():
            env_map[k] = v.strip()

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
        "DEEPSEEK_API_KEY",
        "SHUTONG_AI_API_KEY",
        "SHUTONG_VISION_API_KEY",
        "DEEPSEEK_BASE_URL",
        "SHUTONG_AI_BASE_URL",
        "SHUTONG_VISION_BASE_URL",
        "SHUTONG_AI_MODEL",
        "SHUTONG_TEXT_ENRICH_MODEL",
        "SHUTONG_VISION_MODEL",
    ]
    seen_ordered: set[str] = set()
    ordered_lines: list[str] = []
    for k in ordered_keys:
        if k in env_map and env_map[k]:
            ordered_lines.append(f"{k}={env_map[k]}")
            seen_ordered.add(k)
    extra_keys = sorted(k for k in env_map if k not in seen_ordered and env_map[k])
    dev_lines = [
        "# 书童本地开发环境配置（仅开发态生效，严禁提交至 Git）",
        *ordered_lines,
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


def _propagate_ai_env(proc_env: dict[str, str], dev_vars: dict[str, str]) -> str:
    """将 dev.env、已验权限的 k12100.env 或 Shell 中的 DEEPSEEK_API_KEY 透传给开发后端，返回来源说明。"""
    source_desc = "未配置"
    if dev_vars.get("SHUTONG_AI_API_KEY") or dev_vars.get("SHUTONG_VISION_API_KEY") or dev_vars.get("DEEPSEEK_API_KEY"):
        source_desc = f"dev.env ({_mask_secret(dev_vars.get('DEEPSEEK_API_KEY') or dev_vars.get('SHUTONG_AI_API_KEY') or dev_vars.get('SHUTONG_VISION_API_KEY', ''))})"
    else:
        user_ai = _load_verified_user_k12100_ai_env()
        if user_ai:
            proc_env.update(user_ai)
            source_desc = f"development/k12100/k12100.env ({_mask_secret(user_ai.get('DEEPSEEK_API_KEY') or user_ai.get('SHUTONG_AI_API_KEY', ''))})"
        elif proc_env.get("DEEPSEEK_API_KEY", "").strip():
            source_desc = f"当前 Shell DEEPSEEK_API_KEY ({_mask_secret(proc_env['DEEPSEEK_API_KEY'])})"
        elif proc_env.get("SHUTONG_AI_API_KEY", "").strip():
            source_desc = f"当前 Shell SHUTONG_AI_API_KEY ({_mask_secret(proc_env['SHUTONG_AI_API_KEY'])})"

    ai_key = (
        proc_env.get("SHUTONG_AI_API_KEY", "").strip()
        or proc_env.get("SHUTONG_VISION_API_KEY", "").strip()
        or proc_env.get("DEEPSEEK_API_KEY", "").strip()
    )
    if ai_key:
        for k in ("SHUTONG_AI_API_KEY", "SHUTONG_VISION_API_KEY", "DEEPSEEK_API_KEY"):
            if not proc_env.get(k, "").strip():
                proc_env[k] = ai_key
    ai_base = (
        proc_env.get("SHUTONG_AI_BASE_URL", "").strip()
        or proc_env.get("SHUTONG_VISION_BASE_URL", "").strip()
        or proc_env.get("DEEPSEEK_BASE_URL", "").strip()
    ).rstrip("/")
    # 书童后端走 OpenAI /v1/chat/completions 协议；剥离宿主环境常见的 Anthropic 兼容后缀 /anthropic
    if ai_base.endswith("/anthropic"):
        ai_base = ai_base[: -len("/anthropic")].rstrip("/") or "https://api.deepseek.com"
    if ai_base:
        for k in ("SHUTONG_AI_BASE_URL", "SHUTONG_VISION_BASE_URL"):
            if not proc_env.get(k, "").strip() or proc_env[k].strip().rstrip("/").endswith("/anthropic"):
                proc_env[k] = ai_base
        if not proc_env.get("DEEPSEEK_BASE_URL", "").strip():
            proc_env["DEEPSEEK_BASE_URL"] = ai_base
    return source_desc


def init_env_cmd(args: argparse.Namespace | None = None) -> int:
    """仅初始化并同步开发环境凭据文件（可选同时写入 DeepSeek AI 配置）。"""
    ai_updates: dict[str, str] = {}
    if args is not None:
        raw_key = (args.deepseek_api_key or "").strip()
        if not raw_key and args.from_shell_deepseek:
            raw_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            if not raw_key:
                print("❌ 错误：当前 Shell 环境变量 DEEPSEEK_API_KEY 未设置或为空。", file=sys.stderr)
                return 1
        try:
            ai_updates = _build_ai_updates(
                raw_key,
                base_url=args.deepseek_base_url,
                vision_model=args.deepseek_vision_model,
                text_model=args.deepseek_model,
            )
        except ValueError as exc:
            print(f"❌ 错误：{exc}", file=sys.stderr)
            return 1

    env_map = ensure_dev_env(ai_updates=ai_updates or None)
    print("✅ 开发环境学生端与管理端令牌已就绪（仅保存在本地受保护目录）：")
    print(f"   - 后端配置：{DEV_ENV_FILE} (0600)")
    print(f"   - 前端配置：{WEB_DEV_ENV_FILE} (0600，仅 vite dev 生效)")
    print(f"   - 学生令牌长度：{len(env_map['SHUTONG_STUDENT_TOKEN'])}，管理令牌长度：{len(env_map['SHUTONG_ADMIN_TOKEN'])}")
    ai_key = env_map.get("DEEPSEEK_API_KEY") or env_map.get("SHUTONG_AI_API_KEY") or ""
    print(f"   - DeepSeek AI Key：{_mask_secret(ai_key)}")
    return 0


def config_ai_cmd(args: argparse.Namespace) -> int:
    """在 dev.env 中单独配置、从 Shell 导入或清理 DeepSeek AI 参数（保留既有开发令牌）。"""
    if args.clear:
        ensure_dev_env(remove_keys=_AI_ENV_KEYS)
        print(f"✅ 已清理 {DEV_ENV_FILE} 中的 DeepSeek AI 配置（既有学生/管理开发令牌已保留）。")
        return 0

    raw_key = (args.deepseek_api_key or "").strip()
    if not raw_key and args.from_shell:
        raw_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not raw_key:
            print("❌ 错误：当前 Shell 环境变量 DEEPSEEK_API_KEY 未设置或为空。", file=sys.stderr)
            return 1
    has_other = any([args.base_url, args.vision_model, args.text_model])
    if not raw_key and not args.from_shell and not has_other:
        raw_key = getpass("请输入 DEEPSEEK_API_KEY（不回显）: ").strip()

    try:
        ai_updates = _build_ai_updates(
            raw_key,
            base_url=args.base_url,
            vision_model=args.vision_model,
            text_model=args.text_model,
        )
    except ValueError as exc:
        print(f"❌ 错误：{exc}", file=sys.stderr)
        return 1

    if not ai_updates:
        print("❌ 错误：未提供 DEEPSEEK_API_KEY 或有效 AI 配置项。", file=sys.stderr)
        return 1

    env_map = ensure_dev_env(ai_updates=ai_updates)
    print(f"✅ 已安全写入 DeepSeek AI 配置至 {DEV_ENV_FILE} (0600，保留既有开发令牌)：")
    print(f"   - DEEPSEEK_API_KEY：{_mask_secret(env_map.get('DEEPSEEK_API_KEY', ''))}")
    if env_map.get("DEEPSEEK_BASE_URL"):
        print(f"   - DEEPSEEK_BASE_URL：{env_map['DEEPSEEK_BASE_URL']}")
    return 0


def _api_python() -> str:
    """优先使用 API 自己的 venv，避免外层 VIRTUAL_ENV 与 uv 项目环境不一致。"""
    candidate = API_DIR / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


def _format_subprocess_failure(stdout: str, stderr: str) -> str:
    """迁移/启动失败时同时保留 stdout 与 stderr，避免只显示 warning 掩盖真实错误。"""
    parts = [part.strip() for part in (stdout, stderr) if part and part.strip()]
    return "\n".join(parts) if parts else "(无输出)"


def start_env() -> int:
    """启动本地日常开发环境（后端 8000 + Vite dev 5173）。"""
    missing_tools = [name for name in ("npm",) if shutil.which(name) is None]
    if missing_tools:
        print(f"❌ 缺少运行工具：{', '.join(missing_tools)}；请先安装后再启动开发环境。")
        return 1
    for legacy_port in LEGACY_TEST_PORTS:
        if is_port_in_use(legacy_port):
            print(
                f"⚠️ 旧测试端口 {legacy_port} 仍被占用；开发环境只使用 8000/5173。"
                " 请停止遗留的测试/人工环境进程后再继续。"
            )
    if is_port_in_use(API_PORT):
        print(f"❌ 错误：后端端口 {API_PORT} 已被占用，请先执行 `stop` 或排查残留进程。")
        return 1
    if is_port_in_use(WEB_PORT):
        print(f"❌ 错误：前端端口 {WEB_PORT} 已被占用，请先执行 `stop` 或排查残留进程。")
        return 1

    try:
        dev_vars = ensure_dev_env()
    except RuntimeError as exc:
        print(f"❌ 开发环境初始化失败：{exc}")
        return 1
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    proc_env = os.environ.copy()
    proc_env.update(dev_vars)
    ai_source = _propagate_ai_env(proc_env, dev_vars)
    print(f"🤖 DeepSeek AI 配置：{ai_source}")

    print("📦 正在检查并升级开发数据库迁移 (alembic upgrade head)...")
    mig = subprocess.run(
        [_api_python(), "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=proc_env,
        capture_output=True,
        text=True,
    )
    if mig.returncode != 0:
        detail = _format_subprocess_failure(mig.stdout, mig.stderr)
        print(f"❌ 数据库迁移失败：\n{detail}")
        if "Can't locate revision" in detail:
            print(
                "提示：开发库的 alembic revision 与当前 checkout 的迁移文件不一致。\n"
                "请确认在修复后的工作树运行（而不是旧 checkout），且该 checkout 包含数据库中记录的最新迁移。"
            )
        return 1

    api_log_path = LOG_DIR / "dev-api.log"
    web_log_path = LOG_DIR / "dev-web.log"

    print(f"🌐 正在启动本地开发后端 (127.0.0.1:{API_PORT})...")
    with open(api_log_path, "w", encoding="utf-8") as api_log:
        api_proc = subprocess.Popen(
            [
                _api_python(),
                "-m",
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
    """检查日常开发环境运行状态与凭据配置情况（仅脱敏展示密钥摘要）。"""
    api_live = is_port_in_use(API_PORT)
    web_live = is_port_in_use(WEB_PORT)
    dev_env_ok = DEV_ENV_FILE.is_file()
    web_env_ok = WEB_DEV_ENV_FILE.is_file()
    dev_vars = parse_env_file(DEV_ENV_FILE) if dev_env_ok else {}
    dev_ai = dev_vars.get("DEEPSEEK_API_KEY") or dev_vars.get("SHUTONG_AI_API_KEY") or dev_vars.get("SHUTONG_VISION_API_KEY") or ""
    k12_ai_map = _load_verified_user_k12100_ai_env()
    k12_ai = k12_ai_map.get("DEEPSEEK_API_KEY") or k12_ai_map.get("SHUTONG_AI_API_KEY") or ""
    shell_ai = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if dev_ai:
        ai_status = f"🟢 已写入 dev.env ({_mask_secret(dev_ai)})"
    elif k12_ai:
        ai_status = f"🟡 来自 development/k12100/k12100.env ({_mask_secret(k12_ai)})"
    elif shell_ai:
        ai_status = f"🟡 来自当前 Shell ({_mask_secret(shell_ai)}，可运行 config-ai --from-shell 持久化)"
    else:
        ai_status = "🔴 未配置"

    print("==================================================================")
    print("🔍 书童日常开发环境状态")
    print("==================================================================")
    print(f"后端凭据 ({DEV_ENV_FILE}): {'🟢 已配置' if dev_env_ok else '🔴 缺失'}")
    print(f"前端凭据 ({WEB_DEV_ENV_FILE}): {'🟢 已同步' if web_env_ok else '🔴 缺失'}")
    print(f"DeepSeek AI 配置: {ai_status}")
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


def build_parser() -> argparse.ArgumentParser:
    """构建日常开发环境管理 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(description="书童日常开发环境管理与 DeepSeek AI 配置 CLI")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init-env", help="初始化或校验 dev.env 与前端开发令牌（可选同步写入 DeepSeek Key）")
    p_init.add_argument("--deepseek-api-key", default="", help="同时写入 DEEPSEEK_API_KEY / SHUTONG_AI_API_KEY")
    p_init.add_argument("--from-shell-deepseek", action="store_true", help="从当前 Shell DEEPSEEK_API_KEY 导入到 dev.env")
    p_init.add_argument("--deepseek-base-url", default="", help="可选 DeepSeek API Base URL")
    p_init.add_argument("--deepseek-vision-model", default="", help="可选视觉模型名")
    p_init.add_argument("--deepseek-model", default="", help="可选文本/助教模型名")

    p_ai = sub.add_parser("config-ai", help="在 dev.env 中单独配置、从 Shell 导入或清理 DeepSeek AI 参数")
    p_ai.add_argument("--deepseek-api-key", default="", help="传入 DEEPSEEK_API_KEY（不填则交互输入或配合 --from-shell 使用）")
    p_ai.add_argument("--from-shell", action="store_true", help="从当前 Shell 环境变量 DEEPSEEK_API_KEY 导入")
    p_ai.add_argument("--base-url", default="", help="可选 DeepSeek API Base URL")
    p_ai.add_argument("--vision-model", default="", help="可选视觉模型名")
    p_ai.add_argument("--text-model", default="", help="可选文本/助教模型名")
    p_ai.add_argument("--clear", action="store_true", help="仅清除 dev.env 中的 DeepSeek AI 配置（保留双端开发令牌）")

    sub.add_parser("start", help="启动本地日常开发环境（后端 8000 + Vite dev 5173）")
    sub.add_parser("stop", help="停止本地日常开发环境")
    sub.add_parser("status", help="检查开发服务端口、凭据与 DeepSeek AI 配置状态")
    sub.add_parser("sim", help="打开 iPadOS 竖屏模拟机窗口直连开发前端")
    sub.add_parser("sim-portrait", help="打开 iPadOS 竖屏模拟机窗口直连开发前端")
    sub.add_parser("sim-landscape", help="打开 iPadOS 横屏模拟机窗口直连开发前端")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """执行日常开发环境 CLI 子命令并返回退出码。"""
    args = build_parser().parse_args(argv)
    action = args.command or "status"
    if action == "init-env":
        return init_env_cmd(args)
    if action == "config-ai":
        return config_ai_cmd(args)
    if action == "start":
        return start_env()
    if action == "stop":
        return stop_env()
    if action == "status":
        return status_env()
    if action in ("sim", "sim-portrait"):
        return open_sim(landscape=False)
    if action == "sim-landscape":
        return open_sim(landscape=True)
    return 2


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
