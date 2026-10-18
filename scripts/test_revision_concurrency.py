#!/usr/bin/env python3
"""启动独立临时 PostgreSQL，执行 ST-002 并发测试并清理本次容器。"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    name = f'pageboy-st002-{uuid4().hex[:12]}'
    password = secrets.token_hex(24)
    env = dict(os.environ, POSTGRES_PASSWORD=password)
    subprocess.run([
        'docker', 'run', '--detach', '--rm', '--name', name,
        '--tmpfs', '/var/lib/postgresql/data:rw,size=256m',
        '--publish', '127.0.0.1::5432', '--env', 'POSTGRES_PASSWORD',
        '--env', 'POSTGRES_USER=pageboy_test', '--env', 'POSTGRES_DB=pageboy_st002_test',
        'postgres:16',
    ], env=env, check=True, capture_output=True, text=True)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'pageboy_test',
                                    '-d', 'pageboy_st002_test'], capture_output=True, timeout=10)
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('临时 PostgreSQL 在 60 秒内未就绪')
        port = subprocess.check_output(['docker', 'port', name, '5432/tcp'], text=True).strip().rsplit(':', 1)[1]
        version = subprocess.check_output(['docker', 'exec', name, 'postgres', '--version'], text=True).strip()
        print(f'Isolated database: {name}, {version}, loopback port={port}', flush=True)
        test_env = dict(os.environ, ST002_TEST_DATABASE_URL=(
            f'postgresql+psycopg://pageboy_test:{password}@127.0.0.1:{port}/pageboy_st002_test'))
        result = subprocess.run([sys.executable, '-m', 'pytest',
                                 'services/api/tests/test_revision_concurrency.py', '-q', '-s'],
                                cwd=ROOT, env=test_env)
        return result.returncode
    finally:
        subprocess.run(['docker', 'stop', '--time', '5', name], check=True, capture_output=True)
        print(f'Removed isolated database container: {name}', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
