"""0006：隔离临时 SQLite 库验证既有数据保留、增量列回填默认、往返与 alembic check。"""
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text


def test_0006_preserves_existing_rows_and_roundtrips(tmp_path):
    api = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path}/m6.sqlite3"
    env = dict(os.environ, DATABASE_URL=url)

    def alembic(*args):
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=api, env=env, check=True, capture_output=True)

    alembic("upgrade", "0005")
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO source_documents (id,title,subject,rights_status,verified,created_at) VALUES ('s6','虚构测试数据：迁移','math','unknown',0,CURRENT_TIMESTAMP)"))
    alembic("upgrade", "head")
    alembic("check")
    insp = inspect(engine)
    assert {"knowledge_nodes", "knowledge_node_versions", "question_knowledge_links", "errata", "question_source_regions", "research_runs"} <= set(insp.get_table_names())
    with engine.begin() as c:
        row = c.execute(text("SELECT title, source_class, ingest_status, review_status FROM source_documents WHERE id='s6'")).one()
    assert tuple(row) == ("虚构测试数据：迁移", "unclassified", "recorded", "pending")
    alembic("downgrade", "0005")
    alembic("upgrade", "head")
    with engine.begin() as c:
        assert c.execute(text("SELECT title FROM source_documents WHERE id='s6'")).scalar() == "虚构测试数据：迁移"
