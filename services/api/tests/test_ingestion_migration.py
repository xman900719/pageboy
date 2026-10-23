"""仅在 pytest 临时 SQLite 库验证升级、结构一致与隔离回退。"""
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text


def test_private_ingestion_migration_preserves_foundation(tmp_path):
    api = Path(__file__).resolve().parents[1]
    url = f'sqlite+pysqlite:///{tmp_path}/migration.sqlite3'
    env = dict(os.environ, DATABASE_URL=url)
    def alembic(*args):
        subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=api, env=env, check=True, capture_output=True)
    alembic('upgrade', '0001')
    engine = create_engine(url)
    assert 'source_attachments' not in inspect(engine).get_table_names()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO source_documents (id,title,subject,rights_status,verified,created_at) VALUES ('synthetic','虚构测试数据','math','unknown',0,CURRENT_TIMESTAMP)"))
    alembic('upgrade', 'head')
    alembic('check')
    assert {'source_reviews', 'source_attachments', 'imported_questions'} <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT title FROM source_documents WHERE id='synthetic'")) == '虚构测试数据'
    alembic('downgrade', '0001')
    assert 'source_attachments' not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM source_documents')) == 1
    alembic('upgrade', 'head')
    alembic('check')
    engine.dispose()
