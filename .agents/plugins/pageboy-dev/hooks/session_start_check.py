#!/usr/bin/env python3
"""SessionStart hook: inject concise dev environment & isolation summary."""
import json
import os
from pathlib import Path
import sys


def main() -> None:
    _ = json.loads(sys.stdin.read() or "{}")
    home_root = Path(os.environ.get("PAGEBOY_HOME", "/media/xc/backup_ext4/pageboy-home"))
    dev_home = home_root / "development"
    dev_ok = (dev_home / "home.json").is_file()
    legacy_shutong = (Path.home() / ".config" / "shutong").exists()

    msg = (
        f"[pageboy-dev] 环境自检: dev_home={'OK' if dev_ok else 'MISSING'} ({dev_home}), "
        f"legacy_config={'CLEAN' if not legacy_shutong else 'WARN_EXISTS'}. "
        "红线提醒: (1) 开发/测试服务仅限 scripts/run_dev_env.py (127.0.0.1:8000/5173, 禁用 4173/0.0.0.0); "
        "(2) 严禁自动灌入虚构数据 (seed_demo.py 默认 fail-closed); "
        "(3) 前端改动提交前须完成 iPadOS 模拟机选项式人工核验并获测试人全项确认。"
    )
    json.dump(
        {"injectSteps": [{"systemMessage": {"systemMessage": msg}}]},
        sys.stdout,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    main()
