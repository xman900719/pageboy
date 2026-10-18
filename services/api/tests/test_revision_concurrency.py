"""ST-002：隔离 PostgreSQL、真实 HTTP 和独立事务的并发验证。"""
from concurrent.futures import ThreadPoolExecutor
import os
import socket
from threading import Barrier, Lock, Thread
import time
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
import uvicorn

from shutong import models as m
from shutong.database import Base, get_db
from shutong.main import app

WORKERS = 8
TEST_URL = os.getenv('ST002_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not TEST_URL, reason='使用 scripts/test_revision_concurrency.py 启动隔离 PostgreSQL')


@pytest.fixture
def postgres_engine():
    url = make_url(TEST_URL)
    assert url.drivername == 'postgresql+psycopg' and url.database == 'pageboy_st002_test'
    schema = f'st002_{uuid4().hex}'
    admin = create_engine(url, connect_args={'connect_timeout': 5})
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, pool_size=WORKERS, max_overflow=0, pool_timeout=30,
                           connect_args={'connect_timeout': 5, 'options': f'-c search_path={schema} -c statement_timeout=30000 -c lock_timeout=20000'})
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            # 只清理本测试创建的随机 schema，不操作已有表或数据库。
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


@pytest.fixture
def revision_server(postgres_engine, monkeypatch):
    token = f'test-only-{uuid4().hex}'
    monkeypatch.setenv('SHUTONG_TOKEN', token)
    def independent_session():
        with Session(postgres_engine) as session:
            yield session
    monkeypatch.setitem(app.dependency_overrides, get_db, independent_session)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    base_url = f'http://127.0.0.1:{listener.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, '临时 HTTP 服务未启动'
        yield base_url, {'Authorization': f'Bearer {token}'}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), '临时 HTTP 服务未退出'


@pytest.mark.parametrize('round_number', range(1, 4))
@pytest.mark.parametrize('synchronize_reads', [False, True], ids=['natural', 'colliding'])
def test_concurrent_revisions(postgres_engine, revision_server, synchronize_reads, round_number):
    base_url, headers = revision_server
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        source = client.post('/api/admin/sources', json={
            'title': '虚构测试数据：并发修订题源', 'subject': 'math',
            'rights_status': 'personal_use_reviewed', 'verified': True,
        })
        assert source.status_code == 201
        body = {'source_document_id': source.json()['id'], 'stem': '虚构测试数据：1+1=?',
                'options': ['A. 1', 'B. 2'], 'correct_answer': 'B',
                'knowledge_ids': ['math.arithmetic'], 'max_points': 2}
        original = client.post('/api/admin/questions', json=body)
        assert original.status_code == 201
        old_id = original.json()['id']
        assert client.post(f'/api/admin/questions/{old_id}/review').status_code == 200
        assert client.post(f'/api/admin/questions/{old_id}/publish').status_code == 200
        exposure = client.get('/api/practice/next?subject=math').json()
        attempt = client.post('/api/practice/attempts', json={
            'exposure_id': exposure['exposure_id'], 'client_attempt_id': 'original-attempt', 'answer': 'B',
        })
        assert attempt.status_code == 201 and attempt.json()['earned_points'] == 2

    def history():
        with Session(postgres_engine) as session:
            result = {model.__tablename__: session.execute(select(model.__table__)).mappings().all()
                      for model in (m.Question, m.Exposure, m.AnswerAttempt)}
            result['original_version'] = session.execute(
                select(m.QuestionVersion.__table__).where(m.QuestionVersion.id == old_id)).mappings().one()
            return result

    before = history()
    start = Barrier(WORKERS)
    reads = Barrier(WORKERS)
    pids = set()
    lock = Lock()

    def synchronize(connection, cursor, statement, parameters, context, executemany):
        if 'max(question_versions.version)' in statement:
            with lock:
                pids.add(connection.connection.driver_connection.info.backend_pid)
            # 查询和返回结果完全来自 PostgreSQL，仅在读后阻挡写入。
            if synchronize_reads:
                reads.wait(timeout=20)

    def revise(index):
        payload = {**body, 'stem': f'虚构测试数据：并发更正 {index}', 'correct_answer': 'A'}
        with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
            start.wait(timeout=20)
            response = client.post(f'/api/admin/questions/{old_id}/revisions', json=payload)
            return index, response

    event.listen(postgres_engine, 'after_cursor_execute', synchronize)
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            results = list(executor.map(revise, range(WORKERS)))
    finally:
        event.remove(postgres_engine, 'after_cursor_execute', synchronize)

    assert all(response.status_code in (201, 409) for _, response in results), [
        (response.status_code, response.text) for _, response in results]
    succeeded = {index: response.json() for index, response in results if response.status_code == 201}
    rejected = [index for index, response in results if response.status_code == 409]
    assert succeeded
    assert len(pids) >= 2, '必须实际使用多个 PostgreSQL 后端连接'
    if synchronize_reads:
        assert len(pids) == WORKERS
        assert len(succeeded) == 1 and len(rejected) == WORKERS - 1
    for _, response in results:
        if response.status_code == 409:
            assert response.json()['detail'] == 'QUESTION_REVISION_CONFLICT'

    with Session(postgres_engine) as session:
        drafts = session.scalars(select(m.QuestionVersion).where(m.QuestionVersion.id != old_id)).all()
        assert {row.id for row in drafts} == {row['id'] for row in succeeded.values()}
        assert sorted(row.version for row in drafts) == list(range(2, len(succeeded) + 2))
        for index, result in succeeded.items():
            row = session.get(m.QuestionVersion, result['id'])
            assert row.stem == f'虚构测试数据：并发更正 {index}'
            assert row.question_id == original.json()['question_id']
            assert row.status == 'draft' and not row.reviewed_by_human and row.published_at is None
    assert history() == before

    # 冲突请求重新提交后逐一成功，且不遗留失败事务或编号空洞。
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        for index in rejected:
            response = client.post(f'/api/admin/questions/{old_id}/revisions', json={
                **body, 'stem': f'虚构测试数据：冲突后重试 {index}',
            })
            assert response.status_code == 201
    with Session(postgres_engine) as session:
        versions = session.scalars(select(m.QuestionVersion.version).order_by(m.QuestionVersion.version)).all()
        assert versions == list(range(1, WORKERS + 2))
    assert history() == before
    print(f'round={round_number} synchronized={synchronize_reads} requests={WORKERS} '
          f'connections={len(pids)} created={len(succeeded)} conflicts={len(rejected)} '
          f'retry_created={len(rejected)} history_unchanged=True')
