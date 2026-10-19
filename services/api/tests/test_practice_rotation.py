"""ST-004：使用虚构测试数据验证最小练习会话、题目轮换与幂等边界（SQLite 单线程）。"""
import pytest
from sqlalchemy import inspect, select

from shutong import models as m
from shutong.database import get_db
from shutong.main import app


@pytest.fixture
def db(client):
    yield from app.dependency_overrides[get_db]()


@pytest.fixture
def question(client, auth):
    source = client.post('/api/admin/sources', headers=auth, json={
        'title': '虚构测试数据：轮换题源', 'subject': 'math',
        'rights_status': 'personal_use_reviewed', 'verified': True,
    }).json()['id']
    body = {
        'source_document_id': source, 'stem': '虚构测试数据：1+1=?',
        'options': ['A. 1', 'B. 2'], 'correct_answer': 'B',
        'knowledge_ids': ['math.arithmetic'], 'max_points': 2,
    }
    response = client.post('/api/admin/questions', json=body, headers=auth)
    assert response.status_code == 201
    return response.json(), body


def publish(client, auth, version_id):
    assert client.post(f'/api/admin/questions/{version_id}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 200


def snapshot(record):
    return {column.key: getattr(record, column.key) for column in inspect(record).mapper.column_attrs}


def test_training_rotates_through_pool(client, auth, published):
    responses = [client.get('/api/practice/next?subject=math', headers=auth) for _ in range(6)]
    assert all(response.status_code == 200 for response in responses)
    items = [response.json() for response in responses]
    assert len({item['question_version_id'] for item in items[:5]}) == 5
    assert {item['question_version_id'] for item in items[:5]} == set(published)
    assert items[5]['question_version_id'] == items[0]['question_version_id']
    assert all(item['unseen_at_exposure'] is True for item in items[:5])
    assert items[5]['unseen_at_exposure'] is False


def test_evaluation_serves_each_unseen_question_once(client, auth, published):
    served = []
    for _ in range(5):
        response = client.get('/api/practice/next?subject=math&purpose=evaluation', headers=auth)
        assert response.status_code == 200
        item = response.json()
        assert item['unseen_at_exposure'] is True
        served.append(item['question_version_id'])
    assert len(set(served)) == 5
    assert set(served) == set(published)
    exhausted = client.get('/api/practice/next?subject=math&purpose=evaluation', headers=auth)
    assert exhausted.status_code == 404
    assert exhausted.json()['detail'] == 'NO_ELIGIBLE_QUESTION'


def test_evaluation_excludes_question_seen_in_training(client, auth, published):
    training = client.get('/api/practice/next?subject=math', headers=auth)
    assert training.status_code == 200
    q_a = training.json()['question_version_id']
    served = []
    for _ in range(4):
        response = client.get('/api/practice/next?subject=math&purpose=evaluation', headers=auth)
        assert response.status_code == 200
        item = response.json()
        assert item['question_version_id'] != q_a
        served.append(item['question_version_id'])
    assert q_a not in served
    assert set(served) == set(published) - {q_a}
    exhausted = client.get('/api/practice/next?subject=math&purpose=evaluation', headers=auth)
    assert exhausted.status_code == 404
    assert exhausted.json()['detail'] == 'NO_ELIGIBLE_QUESTION'


def test_cross_version_exposure_keeps_question_seen(client, auth, db, question):
    original, body = question
    v1 = original['id']
    publish(client, auth, v1)
    first = client.get('/api/practice/next?subject=math', headers=auth)
    assert first.status_code == 200
    first_item = first.json()
    assert first_item['question_version_id'] == v1
    assert first_item['unseen_at_exposure'] is True
    attempt = client.post('/api/practice/attempts', headers=auth, json={
        'exposure_id': first_item['exposure_id'], 'client_attempt_id': 'v1-attempt', 'answer': 'B'})
    assert attempt.status_code == 201 and attempt.json()['earned_points'] == 2.0
    v1_exposure_snapshot = snapshot(db.get(m.Exposure, first_item['exposure_id']))
    v1_attempt_snapshot = snapshot(db.get(m.AnswerAttempt, attempt.json()['id']))
    corrected = {**body, 'stem': '虚构测试数据：2+3=?', 'correct_answer': 'A',
                 'knowledge_ids': ['math.addition'], 'max_points': 3}
    revision = client.post(f'/api/admin/questions/{v1}/revisions', headers=auth, json=corrected)
    assert revision.status_code == 201
    v2 = revision.json()['id']
    publish(client, auth, v2)
    assert client.get('/api/practice/next?subject=math&purpose=evaluation', headers=auth).status_code == 404
    second = client.get('/api/practice/next?subject=math', headers=auth)
    assert second.status_code == 200
    second_item = second.json()
    assert second_item['question_version_id'] == v2
    assert second_item['unseen_at_exposure'] is False
    graded = client.post('/api/practice/attempts', headers=auth, json={
        'exposure_id': second_item['exposure_id'], 'client_attempt_id': 'v2-attempt',
        'answer': corrected['correct_answer']})
    assert graded.status_code == 201
    assert graded.json()['earned_points'] == corrected['max_points']
    db.expire_all()
    assert snapshot(db.get(m.Exposure, first_item['exposure_id'])) == v1_exposure_snapshot
    assert snapshot(db.get(m.AnswerAttempt, attempt.json()['id'])) == v1_attempt_snapshot
    assert v1_exposure_snapshot['is_unseen_at_exposure'] is True
    assert v1_attempt_snapshot['earned_points'] == 2.0


def test_unpublished_questions_are_never_served(client, auth):
    source = client.post('/api/admin/sources', headers=auth, json={
        'title': '虚构测试数据：未发布题源', 'subject': 'math',
        'rights_status': 'personal_use_reviewed', 'verified': True,
    }).json()['id']
    version_id = client.post('/api/admin/questions', headers=auth, json={
        'source_document_id': source, 'stem': '虚构测试数据：3+3=?',
        'options': ['A. 5', 'B. 6'], 'correct_answer': 'B',
        'knowledge_ids': ['math.arithmetic'], 'max_points': 2,
    }).json()['id']
    assert client.post(f'/api/admin/questions/{version_id}/review', headers=auth).status_code == 200
    training = client.get('/api/practice/next?subject=math', headers=auth)
    assert training.status_code == 404
    assert training.json()['detail'] == 'NO_ELIGIBLE_QUESTION'
    evaluation = client.get('/api/practice/next?subject=math&purpose=evaluation', headers=auth)
    assert evaluation.status_code == 404
    assert evaluation.json()['detail'] == 'NO_ELIGIBLE_QUESTION'


def test_knowledge_id_filter(client, auth, published):
    source = client.post('/api/admin/sources', headers=auth, json={
        'title': '虚构测试数据：几何题源', 'subject': 'math',
        'rights_status': 'personal_use_reviewed', 'verified': True,
    }).json()['id']
    extra = client.post('/api/admin/questions', headers=auth, json={
        'source_document_id': source, 'stem': '虚构测试数据：三角形内角和=?',
        'options': ['A. 90', 'B. 180'], 'correct_answer': 'B',
        'knowledge_ids': ['math.geometry'], 'max_points': 2,
    }).json()['id']
    publish(client, auth, extra)
    # 顺序上先取 evaluation：唯一几何题被 training 曝光后即失去未见资格，两种 purpose 才都能返回该题。
    evaluation = client.get('/api/practice/next?subject=math&knowledge_id=math.geometry&purpose=evaluation', headers=auth)
    assert evaluation.status_code == 200
    assert evaluation.json()['question_version_id'] == extra
    training = client.get('/api/practice/next?subject=math&knowledge_id=math.geometry', headers=auth)
    assert training.status_code == 200
    assert training.json()['question_version_id'] == extra
    for purpose in ('training', 'evaluation'):
        missing = client.get(f'/api/practice/next?subject=math&knowledge_id=math.nonexistent&purpose={purpose}', headers=auth)
        assert missing.status_code == 404
        assert missing.json()['detail'] == 'NO_ELIGIBLE_QUESTION'


def test_non_owner_exposure_not_visible(client, auth, published, db):
    version_id = published[0]
    question_id = db.scalar(select(m.QuestionVersion.question_id).where(m.QuestionVersion.id == version_id))
    foreign = m.Exposure(learner_id='someone-else', question_id=question_id,
                         question_version_id=version_id, purpose='training',
                         is_unseen_at_exposure=True)
    db.add(foreign)
    db.commit()
    response = client.post('/api/practice/attempts', headers=auth, json={
        'client_attempt_id': 'foreign-exposure-attempt', 'exposure_id': foreign.id, 'answer': 'B'})
    assert response.status_code == 404


def test_practice_endpoints_require_auth(client):
    assert client.get('/api/practice/next?subject=math').status_code == 401
    assert client.post('/api/practice/attempts', json={
        'client_attempt_id': 'no-auth', 'exposure_id': 'missing', 'answer': 'B'}).status_code == 401


def test_second_key_for_same_exposure_rejected(client, auth, db, published):
    item = client.get('/api/practice/next?subject=math', headers=auth).json()
    first = client.post('/api/practice/attempts', headers=auth, json={
        'client_attempt_id': 'key-1', 'exposure_id': item['exposure_id'], 'answer': 'B'})
    assert first.status_code == 201
    second = client.post('/api/practice/attempts', headers=auth, json={
        'client_attempt_id': 'key-2', 'exposure_id': item['exposure_id'], 'answer': 'B'})
    assert second.status_code == 409
    assert second.json()['detail'] == 'EXPOSURE_ALREADY_SUBMITTED'
    db.expire_all()
    rows = db.scalars(select(m.AnswerAttempt).where(m.AnswerAttempt.exposure_id == item['exposure_id'])).all()
    assert len(rows) == 1
    assert rows[0].id == first.json()['id']


def test_hinted_evaluation_attempt_not_valid_unseen(client, auth, published):
    item = client.get('/api/practice/next?subject=math&purpose=evaluation', headers=auth).json()
    response = client.post('/api/practice/attempts', headers=auth, json={
        'client_attempt_id': 'hinted-1', 'exposure_id': item['exposure_id'],
        'answer': 'B', 'hints_used': True})
    assert response.status_code == 201
    assert response.json()['evaluation_valid_unseen'] is False
