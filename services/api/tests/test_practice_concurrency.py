"""ST-004：隔离 PostgreSQL、真实 HTTP、独立连接的练习并发验证。"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import os
import socket
from threading import Barrier, Event, Lock, Thread
import time
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
import uvicorn

from shutong import models as m
from shutong.database import Base, get_db
from shutong.main import app

WORKERS = 8
TEST_URL = os.getenv('ST004_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not TEST_URL, reason='使用 scripts/test_practice_concurrency.py 启动隔离 PostgreSQL')


@pytest.fixture
def postgres_engine():
    url = make_url(TEST_URL)
    assert url.drivername == 'postgresql+psycopg' and url.database == 'pageboy_st004_test'
    schema = f'st004_{uuid4().hex}'
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
def practice_server(postgres_engine, monkeypatch):
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


def make_gate(needed, pids, lock):
    # 一次性门：作答失败后的重查会再次触发钩子，循环 Barrier 会卡死，Event 只开一次。
    gate = Event(); state = {'count': 0}
    def wait(statement, pid):
        with lock:
            pids.add(pid)
            state['count'] += 1
            if state['count'] >= needed:
                gate.set()
        gate.wait(timeout=20)
    def record(statement, pid):
        with lock:
            pids.add(pid)
    return wait, record


def is_exposure_read(statement):
    """曝光读取：修复前的逐题 seen 检查与修复后的批量计数查询都命中，红绿两态都能制造竞争窗。"""
    return ('GROUP BY exposures.question_id' in statement) or ('FROM exposures JOIN question_versions' in statement)


def is_attempt_read(statement):
    """作答幂等预检 SELECT；修复后失败重查会再次命中，一次性门使重放无害。"""
    return statement.lstrip().upper().startswith('SELECT') and 'answer_attempts.client_attempt_id' in statement


def make_source(client):
    """经管理 API 创建已核实来源；全部内容为虚构测试数据。"""
    response = client.post('/api/admin/sources', json={
        'title': '虚构测试数据：并发练习题源', 'subject': 'math',
        'rights_status': 'personal_use_reviewed', 'verified': True,
    })
    assert response.status_code == 201
    return response.json()['id']


def make_published_question(client, source_id, stem):
    """经管理 API 创建并人工审核、发布一道单选题，返回 (question_id, version_id)。"""
    body = {'source_document_id': source_id, 'stem': stem, 'options': ['A. 1', 'B. 2'],
            'correct_answer': 'B', 'knowledge_ids': ['math.arithmetic'], 'max_points': 2}
    response = client.post('/api/admin/questions', json=body)
    assert response.status_code == 201
    version_id = response.json()['id']
    assert client.post(f'/api/admin/questions/{version_id}/review').status_code == 200
    assert client.post(f'/api/admin/questions/{version_id}/publish').status_code == 200
    return response.json()['question_id'], version_id


def fetch_rows(engine, model):
    """竞争前后的全表行快照，RowMapping 按值比较。"""
    with Session(engine) as session:
        return session.execute(select(model.__table__)).mappings().all()


def run_concurrent_race(postgres_engine, base_url, headers, matches, synchronize, request):
    """WORKERS 个线程同时发请求；钩子在匹配语句后同步（真实 HTTP + 独立连接）。"""
    start = Barrier(WORKERS)
    pids = set()
    lock = Lock()
    wait, record = make_gate(WORKERS, pids, lock)

    def hook(connection, cursor, statement, parameters, context, executemany):
        if matches(statement):
            action = wait if synchronize else record
            action(statement, connection.connection.driver_connection.info.backend_pid)

    def call(index):
        with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
            start.wait(timeout=20)
            return index, request(client, index)

    event.listen(postgres_engine, 'after_cursor_execute', hook)
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            results = list(executor.map(call, range(WORKERS)))
    finally:
        event.remove(postgres_engine, 'after_cursor_execute', hook)
    return pids, results


def assert_connection_spread(pids, synchronize):
    assert len(pids) >= 2, '必须实际使用多个 PostgreSQL 后端连接'
    if synchronize:
        assert len(pids) == WORKERS


def print_evidence(round_label, mode, pids, statuses, rows):
    distribution = ','.join(f'{status}:{count}' for status, count in sorted(Counter(statuses).items()))
    print(f'round={round_label} mode={mode} requests={WORKERS} connections={len(pids)} '
          f'statuses={distribution} rows={rows}')


@pytest.mark.parametrize('round_number', range(1, 4))
@pytest.mark.parametrize('synchronize', [False, True], ids=['natural', 'colliding'])
def test_concurrent_evaluation_first_exposure(postgres_engine, practice_server, synchronize, round_number):
    """evaluation 首曝竞争：每逻辑题至多一条 unseen 认定，抢曝失败者 404。"""
    base_url, headers = practice_server
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        source_id = make_source(client)
        for index in range(3):
            make_published_question(client, source_id, f'虚构测试数据：首曝竞争题 {index}')

    def request(client, index):
        return client.get('/api/practice/next?subject=math&purpose=evaluation')

    pids, results = run_concurrent_race(postgres_engine, base_url, headers, is_exposure_read, synchronize, request)

    statuses = [response.status_code for _, response in results]
    assert all(status in (200, 404) for status in statuses), [
        (response.status_code, response.text) for _, response in results]
    for _, response in results:
        if response.status_code == 404:
            assert response.json()['detail'] == 'NO_ELIGIBLE_QUESTION'
    successes = [response for _, response in results if response.status_code == 200]
    assert successes
    version_ids = [response.json()['question_version_id'] for response in successes]
    assert len(set(version_ids)) == len(version_ids), version_ids
    assert all(response.json()['unseen_at_exposure'] is True for response in successes)

    with Session(postgres_engine) as session:
        unseen_per_question = session.execute(
            select(m.QuestionVersion.question_id, func.count())
            .select_from(m.Exposure)
            .join(m.QuestionVersion, m.Exposure.question_version_id == m.QuestionVersion.id)
            .where(m.Exposure.is_unseen_at_exposure)
            .group_by(m.QuestionVersion.question_id)).all()
    assert all(count <= 1 for _, count in unseen_per_question)
    assert sum(count for _, count in unseen_per_question) == len(successes)
    exposures_total = len(fetch_rows(postgres_engine, m.Exposure))
    assert exposures_total == len(successes)

    assert_connection_spread(pids, synchronize)
    if synchronize:
        assert len(successes) == 3 and statuses.count(404) == 5

    print_evidence(round_number, 'colliding' if synchronize else 'natural', pids, statuses,
                   f'exposures={exposures_total}')


@pytest.mark.parametrize('synchronize', [False, True], ids=['natural', 'colliding'])
def test_concurrent_training_first_exposure(postgres_engine, practice_server, synchronize):
    """training 竞争：8 连发全部 200，复练合法，恰一条 unseen 首曝认定。"""
    base_url, headers = practice_server
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        source_id = make_source(client)
        question_id, _ = make_published_question(client, source_id, '虚构测试数据：training 竞争题')
    exposures_before = len(fetch_rows(postgres_engine, m.Exposure))

    def request(client, index):
        return client.get('/api/practice/next?subject=math&purpose=training')

    pids, results = run_concurrent_race(postgres_engine, base_url, headers, is_exposure_read, synchronize, request)

    statuses = [response.status_code for _, response in results]
    assert statuses == [200] * WORKERS, [(response.status_code, response.text) for _, response in results]
    assert [response.json()['unseen_at_exposure'] for _, response in results].count(True) == 1

    with Session(postgres_engine) as session:
        unseen_questions = session.execute(
            select(m.QuestionVersion.question_id)
            .select_from(m.Exposure)
            .join(m.QuestionVersion, m.Exposure.question_version_id == m.QuestionVersion.id)
            .where(m.Exposure.is_unseen_at_exposure)).scalars().all()
    exposures_after = len(fetch_rows(postgres_engine, m.Exposure))
    assert exposures_after == exposures_before + WORKERS
    assert unseen_questions == [question_id]

    assert_connection_spread(pids, synchronize)
    print_evidence(1, 'colliding' if synchronize else 'natural', pids, statuses,
                   f'exposures={exposures_after},unseen_true={len(unseen_questions)}')


@pytest.mark.parametrize('round_number', range(1, 4))
@pytest.mark.parametrize('synchronize', [False, True], ids=['natural', 'colliding'])
def test_concurrent_same_key_same_payload(postgres_engine, practice_server, synchronize, round_number):
    """同键同载荷并发：恰一条 recorded，其余 already_recorded 返回同一持久行。"""
    base_url, headers = practice_server
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        source_id = make_source(client)
        make_published_question(client, source_id, '虚构测试数据：幂等竞争题')
        exposure = client.get('/api/practice/next?subject=math&purpose=training').json()
        payload = {'client_attempt_id': 'race-key', 'exposure_id': exposure['exposure_id'],
                   'answer': 'B', 'hints_used': False}

    questions_before = fetch_rows(postgres_engine, m.Question)
    versions_before = fetch_rows(postgres_engine, m.QuestionVersion)
    exposures_before = fetch_rows(postgres_engine, m.Exposure)
    attempts_before = fetch_rows(postgres_engine, m.AnswerAttempt)

    def request(client, index):
        return client.post('/api/practice/attempts', json=payload)

    pids, results = run_concurrent_race(postgres_engine, base_url, headers, is_attempt_read, synchronize, request)

    statuses = [response.status_code for _, response in results]
    assert statuses == [201] * WORKERS, [(response.status_code, response.text) for _, response in results]
    bodies = [response.json() for _, response in results]
    assert [body['status'] for body in bodies].count('recorded') == 1
    assert [body['status'] for body in bodies].count('already_recorded') == WORKERS - 1
    assert len({body['id'] for body in bodies}) == 1
    assert all(body['earned_points'] == 2 for body in bodies)

    assert_connection_spread(pids, synchronize)

    assert fetch_rows(postgres_engine, m.Question) == questions_before
    assert fetch_rows(postgres_engine, m.QuestionVersion) == versions_before
    assert fetch_rows(postgres_engine, m.Exposure) == exposures_before
    attempts_after = fetch_rows(postgres_engine, m.AnswerAttempt)
    assert len(attempts_after) == len(attempts_before) + 1
    new_rows = [row for row in attempts_after if row['id'] not in {old['id'] for old in attempts_before}]
    assert len(new_rows) == 1
    assert new_rows[0]['answer'] == 'B'

    print_evidence(round_number, 'colliding' if synchronize else 'natural', pids, statuses,
                   f'attempts={len(attempts_after)}')


@pytest.mark.parametrize('synchronize', [False, True], ids=['natural', 'colliding'])
def test_concurrent_same_key_different_payloads(postgres_engine, practice_server, synchronize):
    """同键异载荷并发：恰一条 201，其余 409 幂等键冲突，只落一行。"""
    base_url, headers = practice_server
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        source_id = make_source(client)
        make_published_question(client, source_id, '虚构测试数据：同键异载荷竞争题')
        exposure = client.get('/api/practice/next?subject=math&purpose=training').json()
        payload = {'client_attempt_id': 'race-key', 'exposure_id': exposure['exposure_id'],
                   'answer': 'B', 'hints_used': False}

    def request(client, index):
        return client.post('/api/practice/attempts', json={**payload, 'answer': str(index)})

    pids, results = run_concurrent_race(postgres_engine, base_url, headers, is_attempt_read, synchronize, request)

    statuses = [response.status_code for _, response in results]
    succeeded = [response for _, response in results if response.status_code == 201]
    rejected = [response for _, response in results if response.status_code == 409]
    assert len(succeeded) == 1 and len(rejected) == WORKERS - 1, [
        (response.status_code, response.text) for _, response in results]
    for response in rejected:
        assert response.json()['detail'] == 'IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD'

    assert_connection_spread(pids, synchronize)

    attempts_after = fetch_rows(postgres_engine, m.AnswerAttempt)
    assert len(attempts_after) == 1
    assert attempts_after[0]['answer'] in {str(index) for index in range(WORKERS)}

    print_evidence(1, 'colliding' if synchronize else 'natural', pids, statuses,
                   f'attempts={len(attempts_after)}')


@pytest.mark.parametrize('synchronize', [False, True], ids=['natural', 'colliding'])
def test_concurrent_same_exposure_different_keys(postgres_engine, practice_server, synchronize):
    """同曝光异键并发：一个曝光只落一条作答，其余 409 曝光已提交。"""
    base_url, headers = practice_server
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        source_id = make_source(client)
        make_published_question(client, source_id, '虚构测试数据：同曝光异键竞争题')
        exposure_id = client.get('/api/practice/next?subject=math&purpose=training').json()['exposure_id']

    def request(client, index):
        return client.post('/api/practice/attempts', json={
            'client_attempt_id': f'k-{index}', 'exposure_id': exposure_id,
            'answer': 'B', 'hints_used': False})

    pids, results = run_concurrent_race(postgres_engine, base_url, headers, is_attempt_read, synchronize, request)

    statuses = [response.status_code for _, response in results]
    succeeded = [(index, response) for index, response in results if response.status_code == 201]
    rejected = [response for _, response in results if response.status_code == 409]
    assert len(succeeded) == 1 and len(rejected) == WORKERS - 1, [
        (response.status_code, response.text) for _, response in results]
    assert succeeded[0][1].json()['status'] == 'recorded'
    for response in rejected:
        assert response.json()['detail'] == 'EXPOSURE_ALREADY_SUBMITTED'

    assert_connection_spread(pids, synchronize)

    attempts_after = fetch_rows(postgres_engine, m.AnswerAttempt)
    assert len(attempts_after) == 1
    assert attempts_after[0]['client_attempt_id'] == f'k-{succeeded[0][0]}'

    print_evidence(1, 'colliding' if synchronize else 'natural', pids, statuses,
                   f'attempts={len(attempts_after)}')


def test_cross_version_seen_blocks_evaluation_concurrency(postgres_engine, practice_server):
    """跨版本已见：v1 练过并作答后发布 v2，evaluation 仍无可用题，不落新曝光。"""
    base_url, headers = practice_server
    with httpx.Client(base_url=base_url, headers=headers, timeout=45, trust_env=False) as client:
        source_id = make_source(client)
        _, v1_id = make_published_question(client, source_id, '虚构测试数据：跨版本已见原题')
        exposure = client.get('/api/practice/next?subject=math&purpose=training').json()
        attempt = client.post('/api/practice/attempts', json={
            'exposure_id': exposure['exposure_id'], 'client_attempt_id': 'original-attempt', 'answer': 'B'})
        assert attempt.status_code == 201 and attempt.json()['earned_points'] == 2
        revision = client.post(f'/api/admin/questions/{v1_id}/revisions', json={
            'source_document_id': source_id, 'stem': '虚构测试数据：跨版本已见修订',
            'options': ['A. 1', 'B. 2'], 'correct_answer': 'A',
            'knowledge_ids': ['math.number_sense'], 'max_points': 2})
        assert revision.status_code == 201
        v2_id = revision.json()['id']
        assert client.post(f'/api/admin/questions/{v2_id}/review').status_code == 200
        assert client.post(f'/api/admin/questions/{v2_id}/publish').status_code == 200

    exposures_before = fetch_rows(postgres_engine, m.Exposure)
    attempts_before = fetch_rows(postgres_engine, m.AnswerAttempt)

    def request(client, index):
        return client.get('/api/practice/next?subject=math&purpose=evaluation')

    pids, results = run_concurrent_race(postgres_engine, base_url, headers, is_exposure_read, False, request)

    statuses = [response.status_code for _, response in results]
    assert statuses == [404] * WORKERS, [(response.status_code, response.text) for _, response in results]
    for _, response in results:
        assert response.json()['detail'] == 'NO_ELIGIBLE_QUESTION'

    assert_connection_spread(pids, False)
    assert fetch_rows(postgres_engine, m.Exposure) == exposures_before
    assert fetch_rows(postgres_engine, m.AnswerAttempt) == attempts_before

    print_evidence(1, 'natural', pids, statuses,
                   f'exposures={len(exposures_before)},attempts={len(attempts_before)}')
