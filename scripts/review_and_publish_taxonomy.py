"""宿主机便捷脚本：对全学科 135 个候选知识点执行条款核验、审核入库并发布 v2022.1.0。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from shutong.taxonomy_audit import main  # noqa: E402

if __name__ == "__main__":
    # 若未显式指定数据库，默认指向本地开发库 services/api/shutong-dev.sqlite3
    if not os.getenv("SHUTONG_DATABASE_URL") and "--database-url" not in sys.argv:
        default_sqlite = API_DIR / "shutong-dev.sqlite3"
        os.environ["SHUTONG_DATABASE_URL"] = f"sqlite:///{default_sqlite}"
    main()
