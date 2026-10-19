#!/usr/bin/env python3
"""启动独立临时 PostgreSQL，执行 ST-004 练习并发测试并清理本次容器。"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def migration_leg(name, env):
    """Gate1 MATERIAL#1：PG 上验证 0003 迁移往返与 question_id 回填；失败须在 pytest 之前终止脚本。"""
    api = ROOT / 'services/api'

    def alembic(*args):
        subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=api, env=env,
                       check=True, capture_output=True)

    alembic('upgrade', 'head')
    alembic('check')
    # 全部为虚构测试数据；经原始 psql 落一条完整逻辑题链，供降级/升级后断言回填。
    seed_sql = (
        "INSERT INTO source_documents (id,title,subject,rights_status,verified,created_at) "
        "VALUES ('src-pg','虚构测试数据：PG 迁移腿','math','unknown',false,CURRENT_TIMESTAMP); "
        "INSERT INTO questions (id,source_document_id,subject) VALUES ('q-pg','src-pg','math'); "
        "INSERT INTO question_versions (id,question_id,version,status,stem,kind,options,correct_answer,"
        "knowledge_ids,max_points,reviewed_by_human,created_at) "
        "VALUES ('v1-pg','q-pg',1,'published','虚构测试数据：1+1=?','single_choice','[\"A. 1\", \"B. 2\"]',"
        "'B','[\"math.arithmetic\"]',2.0,true,CURRENT_TIMESTAMP); "
        "INSERT INTO exposures (id,learner_id,question_version_id,question_id,purpose,is_unseen_at_exposure,shown_at) "
        "VALUES ('exp-pg','owner','v1-pg','q-pg','training',true,CURRENT_TIMESTAMP);"
    )
    subprocess.run(['docker', 'exec', name, 'psql', '-U', 'pageboy_test', '-d', 'pageboy_st004_test',
                    '-v', 'ON_ERROR_STOP=1', '-c', seed_sql], check=True, capture_output=True, text=True)
    alembic('downgrade', '0002')
    alembic('upgrade', 'head')
    alembic('check')

    def scalar(sql):
        return subprocess.check_output(['docker', 'exec', name, 'psql', '-U', 'pageboy_test',
                                        '-d', 'pageboy_st004_test', '-t', '-c', sql], text=True).strip()

    restored = scalar("SELECT question_id FROM exposures WHERE id='exp-pg'")
    if restored != 'q-pg':
        raise RuntimeError(f'PG 迁移腿：回填断言失败，exposures.question_id={restored!r}（期望 q-pg）')
    nulls = scalar('SELECT count(*) FROM exposures WHERE question_id IS NULL')
    if int(nulls) != 0:
        raise RuntimeError(f'PG 迁移腿：回填后仍有 {nulls} 行 question_id 为 NULL')
    print('Migration leg (PG alembic round-trip + backfill): OK', flush=True)


def main():
    name = f'pageboy-st004-{uuid4().hex[:12]}'
    password = secrets.token_hex(24)
    env = dict(os.environ, POSTGRES_PASSWORD=password)
    subprocess.run([
        'docker', 'run', '--detach', '--rm', '--name', name,
        '--tmpfs', '/var/lib/postgresql/data:rw,size=256m',
        '--publish', '127.0.0.1::5432', '--env', 'POSTGRES_PASSWORD',
        '--env', 'POSTGRES_USER=pageboy_test', '--env', 'POSTGRES_DB=pageboy_st004_test',
        'postgres:16',
    ], env=env, check=True, capture_output=True, text=True)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'pageboy_test',
                                    '-d', 'pageboy_st004_test'], capture_output=True, timeout=10)
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('临时 PostgreSQL 在 60 秒内未就绪')
        port = subprocess.check_output(['docker', 'port', name, '5432/tcp'], text=True).strip().rsplit(':', 1)[1]
        version = subprocess.check_output(['docker', 'exec', name, 'postgres', '--version'], text=True).strip()
        print(f'Isolated database: {name}, {version}, loopback port={port}', flush=True)
        database_url = f'postgresql+psycopg://pageboy_test:{password}@127.0.0.1:{port}/pageboy_st004_test'
        test_env = dict(os.environ, ST004_TEST_DATABASE_URL=database_url)
        # 迁移腿与 pytest 走同一个数据库 URL（alembic env 读取 DATABASE_URL）。
        migration_leg(name, dict(test_env, DATABASE_URL=database_url))
        result = subprocess.run([sys.executable, '-m', 'pytest',
                                 'services/api/tests/test_practice_concurrency.py', '-q', '-s'],
                                cwd=ROOT, env=test_env)
        return result.returncode
    finally:
        subprocess.run(['docker', 'stop', '--time', '5', name], check=True, capture_output=True)
        print(f'Removed isolated database container: {name}', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
