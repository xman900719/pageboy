"""Home 目录解析、home.json 身份校验与开发/生产防串扰单元测试。"""
from __future__ import annotations

import json
import pytest

from shutong.database import make_engine
from shutong.home import (
    HomeIdentityError,
    assert_no_cross_environment_path,
    curriculum_standards_dir,
    default_attachments_dir,
    default_sqlite_path,
    get_env_home,
    init_home_identity,
    normalize_environment,
    verify_home_identity,
)
from shutong.private_files import private_root


def test_init_and_verify_both_environments(tmp_path, monkeypatch):
    """正例：development 与 production 均可在隔离 Home 下初始化并解析正确子路径。"""
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path))
    monkeypatch.delenv("SHUTONG_STANDARDS_DIR", raising=False)
    monkeypatch.delenv("SHUTONG_PRIVATE_DIR", raising=False)

    dev_dir = tmp_path / "development"
    prod_dir = tmp_path / "production"
    dev_id = init_home_identity(dev_dir, "development")
    prod_id = init_home_identity(prod_dir, "production")

    assert json.loads(dev_id.read_text(encoding="utf-8")) == {
        "format_version": 1,
        "workspace_id": "pageboy-development",
        "environment": "development",
    }
    assert json.loads(prod_id.read_text(encoding="utf-8")) == {
        "format_version": 1,
        "workspace_id": "pageboy-production",
        "environment": "production",
    }

    monkeypatch.setenv("SHUTONG_ENV", "dev")
    assert get_env_home(require_identity=True) == dev_dir.resolve()
    assert default_sqlite_path() == (dev_dir / "data" / "shutong-dev.sqlite3").resolve()
    assert private_root() == (dev_dir / "data" / "attachments").resolve()
    assert curriculum_standards_dir() == (dev_dir / "data" / "curriculum_standards").resolve()

    monkeypatch.setenv("SHUTONG_ENV", "prod")
    assert get_env_home(require_identity=True) == prod_dir.resolve()
    assert default_attachments_dir() == (prod_dir / "data" / "attachments").resolve()
    assert private_root() == (prod_dir / "data" / "attachments").resolve()


def test_cross_environment_identity_mismatch_blocked(tmp_path, monkeypatch):
    """反例：环境目录中的 home.json 与 SHUTONG_ENV 不一致时必须失败关闭。"""
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path))
    # 故意在 development 目录写入 production 身份
    dev_dir = tmp_path / "development"
    dev_dir.mkdir(parents=True)
    (dev_dir / "home.json").write_text(
        json.dumps({"format_version": 1, "workspace_id": "pageboy-production", "environment": "production"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("SHUTONG_ENV", "development")
    with pytest.raises(HomeIdentityError, match="身份不匹配"):
        get_env_home(require_identity=True)

    # 损坏的 format_version 也必须拒绝
    (dev_dir / "home.json").write_text(
        json.dumps({"format_version": 99, "workspace_id": "pageboy-development", "environment": "development"}),
        encoding="utf-8",
    )
    with pytest.raises(HomeIdentityError, match="身份不匹配"):
        verify_home_identity(dev_dir, "development", require_exists=True)


def test_cross_environment_path_access_blocked(tmp_path, monkeypatch):
    """反例：严禁开发模式访问 production 路径，也严禁生产模式访问 development 路径。"""
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path))
    prod_db = tmp_path / "production" / "data" / "prod.sqlite3"
    dev_db = tmp_path / "development" / "data" / "shutong-dev.sqlite3"

    monkeypatch.setenv("SHUTONG_ENV", "development")
    with pytest.raises(HomeIdentityError, match="禁止跨环境访问"):
        assert_no_cross_environment_path(prod_db)
    with pytest.raises(HomeIdentityError, match="禁止跨环境访问"):
        make_engine(f"sqlite+pysqlite:///{prod_db}")
    with pytest.raises(HomeIdentityError, match="禁止跨环境访问"):
        monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(tmp_path / "production" / "data" / "attachments"))
        private_root()

    monkeypatch.delenv("SHUTONG_PRIVATE_DIR", raising=False)
    monkeypatch.setenv("SHUTONG_ENV", "prod")
    with pytest.raises(HomeIdentityError, match="禁止跨环境访问"):
        assert_no_cross_environment_path(dev_db)
    with pytest.raises(HomeIdentityError, match="禁止跨环境访问"):
        make_engine(f"sqlite+pysqlite:///{dev_db}")


def test_unknown_environment_and_nested_home_rejected(tmp_path, monkeypatch):
    """反例：未知 SHUTONG_ENV 或将 PAGEBOY_HOME 直接指向具体环境目录均须拒绝。"""
    with pytest.raises(HomeIdentityError, match="未知的运行环境标识"):
        normalize_environment("staging")

    dev_dir = tmp_path / "development"
    init_home_identity(dev_dir, "development")
    monkeypatch.setenv("PAGEBOY_HOME", str(dev_dir))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    with pytest.raises(HomeIdentityError, match="不得直接指向具体环境目录"):
        get_env_home()
