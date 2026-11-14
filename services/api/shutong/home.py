"""书童 (Pageboy) Home 目录解析、环境身份校验与双环境防串扰门禁。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

# 宿主机统一运行根目录（包含 development 与 production 两个强隔离环境）
DEFAULT_PAGEBOY_HOME = Path("/media/xc/backup_ext4/pageboy-home")
FORMAT_VERSION = 1
EnvironmentName = Literal["development", "production"]

_ENV_ALIASES: dict[str, EnvironmentName] = {
    "": "development",
    "dev": "development",
    "development": "development",
    "test": "development",
    "prod": "production",
    "production": "production",
}


class HomeIdentityError(RuntimeError):
    """Home 目录身份缺失、损坏或跨环境串扰异常。"""


def normalize_environment(raw: str | None = None) -> EnvironmentName:
    """将 SHUTONG_ENV 归一化为 development 或 production；未知值立即失败关闭。"""
    value = (os.getenv("SHUTONG_ENV", "") if raw is None else raw).strip().lower()
    if value not in _ENV_ALIASES:
        raise HomeIdentityError(f"未知的运行环境标识 SHUTONG_ENV={value!r}")
    return _ENV_ALIASES[value]


def resolve_home_root(home_root: Path | str | None = None) -> Path:
    """解析 PAGEBOY_HOME 根目录，优先使用显式参数或环境变量。"""
    raw = str(home_root) if home_root is not None else os.getenv("PAGEBOY_HOME", "")
    path = Path(raw.strip() or DEFAULT_PAGEBOY_HOME)
    return path.expanduser().resolve()


def expected_identity(environment: EnvironmentName) -> dict[str, Any]:
    """生成指定环境唯一合法的 home.json 身份清单。"""
    return {
        "format_version": FORMAT_VERSION,
        "workspace_id": f"pageboy-{environment}",
        "environment": environment,
    }


def _validate_identity_payload(payload: Any, expected_env: EnvironmentName, identity_path: Path) -> dict[str, Any]:
    """校验 home.json 内容结构与环境身份一致性。"""
    if not isinstance(payload, dict):
        raise HomeIdentityError(f"home.json 格式非法（非 JSON 对象）: {identity_path}")
    expected = expected_identity(expected_env)
    if (
        payload.get("format_version") != expected["format_version"]
        or payload.get("workspace_id") != expected["workspace_id"]
        or payload.get("environment") != expected["environment"]
    ):
        raise HomeIdentityError(
            f"home.json 环境身份不匹配: 期望 {expected['environment']} ({expected['workspace_id']}), "
            f"实际 {payload!r} ({identity_path})"
        )
    return payload


def verify_home_identity(
    env_dir: Path,
    expected_env: EnvironmentName,
    *,
    require_exists: bool = False,
) -> dict[str, Any] | None:
    """校验环境子目录下的 home.json；若存在但身份不符则阻断执行。"""
    identity_path = env_dir / "home.json"
    if not identity_path.exists():
        if require_exists:
            raise HomeIdentityError(f"缺少环境身份文件 home.json: {identity_path}")
        return None
    if identity_path.is_symlink():
        raise HomeIdentityError(f"拒绝通过符号链接读取 home.json: {identity_path}")
    try:
        raw_text = identity_path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
    except OSError as exc:
        raise HomeIdentityError(f"无法读取 home.json ({identity_path}): {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HomeIdentityError(f"home.json JSON 解析失败 ({identity_path}): {exc}") from exc
    return _validate_identity_payload(payload, expected_env, identity_path)


def init_home_identity(env_dir: Path, environment: EnvironmentName) -> Path:
    """在指定环境目录中幂等初始化或校验 home.json。"""
    env_dir.mkdir(parents=True, exist_ok=True)
    identity_path = env_dir / "home.json"
    if identity_path.exists():
        verify_home_identity(env_dir, environment, require_exists=True)
        return identity_path
    payload = expected_identity(environment)
    identity_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(identity_path, 0o600)
    return identity_path


def assert_no_cross_environment_path(
    target: Path | str,
    expected_env: EnvironmentName | None = None,
    home_root: Path | str | None = None,
) -> Path:
    """阻断跨环境路径访问（例如开发模式访问 production 目录，或生产模式访问 development 目录）。"""
    env = expected_env or normalize_environment()
    root = resolve_home_root(home_root)
    resolved = Path(target).expanduser().resolve()
    forbidden_env: EnvironmentName = "production" if env == "development" else "development"
    forbidden_dir = root / forbidden_env
    if resolved == forbidden_dir or forbidden_dir in resolved.parents:
        raise HomeIdentityError(
            f"禁止跨环境访问: 当前运行环境为 {env}，拒绝访问 {forbidden_env} 路径 {resolved}"
        )
    return resolved


def get_env_home(
    environment: str | None = None,
    home_root: Path | str | None = None,
    *,
    require_identity: bool = False,
) -> Path:
    """解析当前环境在 PAGEBOY_HOME 下的专属根目录，并执行 home.json 身份防错检查。"""
    env = normalize_environment(environment)
    root = resolve_home_root(home_root)
    # 若错误地将 PAGEBOY_HOME 直接指向了某个已含 home.json 的环境子目录，立即阻断
    root_identity = root / "home.json"
    if root_identity.exists():
        raise HomeIdentityError(f"PAGEBOY_HOME 不得直接指向具体环境目录（检测到 {root_identity}）")
    env_dir = root / env
    verify_home_identity(env_dir, env, require_exists=require_identity)
    return env_dir


def default_sqlite_path(home_root: Path | str | None = None) -> Path:
    """返回开发环境默认 SQLite 数据库绝对路径（位于 pageboy-home/development/data/）。"""
    root = resolve_home_root(home_root)
    env_dir = root / "development"
    if home_root is not None or normalize_environment() == "development":
        verify_home_identity(env_dir, "development", require_exists=False)
    return env_dir / "data" / "shutong-dev.sqlite3"


def validate_database_url(url: str, home_root: Path | str | None = None) -> str:
    """校验数据库连接字符串，阻断开发/生产跨环境访问本地 SQLite 文件。"""
    if url.startswith("sqlite") and ":///" in url:
        file_part = url.split(":///", 1)[1].split("?", 1)[0]
        if file_part and file_part != ":memory:":
            assert_no_cross_environment_path(file_part, home_root=home_root)
    return url


def default_attachments_dir(
    environment: str | None = None,
    home_root: Path | str | None = None,
) -> Path:
    """返回当前环境默认私有附件存储目录。"""
    env_dir = get_env_home(environment, home_root=home_root)
    return env_dir / "data" / "attachments"


def curriculum_standards_dir(
    environment: str | None = None,
    home_root: Path | str | None = None,
) -> Path:
    """解析官方课标 PDF 原件目录，优先使用环境变量 SHUTONG_STANDARDS_DIR 并阻断跨环境串扰。"""
    env = normalize_environment(environment)
    override = os.getenv("SHUTONG_STANDARDS_DIR", "").strip()
    if override:
        return assert_no_cross_environment_path(override, expected_env=env, home_root=home_root)
    env_dir = get_env_home(env, home_root=home_root)
    candidate = env_dir / "data" / "curriculum_standards"
    if candidate.is_dir():
        return candidate
    # 生产容器内的标准只读挂载回退路径
    container_mount = Path("/app/private-data/curriculum_standards")
    if env == "production" and container_mount.is_dir():
        return container_mount
    return candidate


def resolve_repo_root(anchor: str | Path | None = None) -> Path:
    """解析包含 contracts/ 目录的项目根路径，同时兼容源码仓库树与容器 /app 浅层布局。"""
    base = Path(anchor).resolve() if anchor is not None else Path(__file__).resolve()
    for parent in base.parents:
        if (parent / "contracts").is_dir():
            return parent
    cwd = Path.cwd()
    if (cwd / "contracts").is_dir():
        return cwd
    container_root = Path("/app")
    if (container_root / "contracts").is_dir():
        return container_root
    return base.parent


def resolve_repo_path(relative_path: str, anchor: str | Path | None = None) -> Path:
    """将仓库相对路径（如 contracts/...）解析为兼容本地与容器的实际路径。"""
    p = Path(relative_path)
    if p.exists():
        return p
    return resolve_repo_root(anchor=anchor) / relative_path

