"""ST-002：使用虚构测试数据验证修订发布和历史不可变。"""
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
        'title': '虚构测试数据：修订题源', 'subject': 'math',
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


def test_revision_preserves_history_and_uses_each_versions_answer_key(client, auth, student_auth, db, question):
    original, body = question
    old_id = original['id']
    publish(client, auth, old_id)
    old_item = client.get('/api/practice/next?subject=math', headers=student_auth).json()
    attempt_body = {'exposure_id': old_item['exposure_id'], 'client_attempt_id': 'before-revision', 'answer': 'B'}
    before = client.post('/api/practice/attempts', headers=student_auth, json=attempt_body)
    assert before.status_code == 201 and before.json()['earned_points'] == 2
    pending_item = client.get('/api/practice/next?subject=math', headers=student_auth).json()
    records = [db.get(m.QuestionVersion, old_id), db.get(m.AnswerAttempt, before.json()['id']),
               db.get(m.Exposure, old_item['exposure_id']), db.get(m.Exposure, pending_item['exposure_id'])]
    history = [snapshot(record) for record in records]
    corrected = {**body, 'stem': '虚构测试数据：1+0=?', 'correct_answer': 'A',
                 'knowledge_ids': ['math.addition'], 'max_points': 3}
    revision = client.post(f'/api/admin/questions/{old_id}/revisions', headers=auth, json=corrected)
    assert revision.status_code == 201
    revised = revision.json()
    assert revised['id'] != old_id
    assert revised['question_id'] == original['question_id']
    assert revised['version'] == 2 and revised['status'] == 'draft'
    # 新草稿不能直接发布；审核期间旧发布版继续可用。
    assert client.post(f"/api/admin/questions/{revised['id']}/publish", headers=auth).status_code == 409
    assert client.get('/api/practice/next?subject=math', headers=student_auth).json()['question_version_id'] == old_id
    db.expire_all()
    draft = db.get(m.QuestionVersion, revised['id'])
    assert draft.reviewed_by_human is False and draft.published_at is None
    assert draft.stem == corrected['stem'] and draft.correct_answer == 'A'
    assert draft.options == body['options'] and draft.knowledge_ids == ['math.addition']
    publish(client, auth, revised['id'])
    newest = client.get('/api/practice/next?subject=math', headers=student_auth).json()
    assert newest['question_version_id'] == revised['id']
    assert newest['stem'] == corrected['stem'] and newest['max_points'] == 3
    assert 'knowledge_ids' not in newest
    assert client.get('/api/practice/next?subject=math&knowledge_id=math.arithmetic', headers=student_auth).status_code == 404
    # 同一道逻辑题的更正不能恢复独立未见资格。
    assert newest['unseen_at_exposure'] is False
    assert client.get('/api/practice/next?subject=math&purpose=evaluation', headers=student_auth).status_code == 404
    after = client.post('/api/practice/attempts', headers=student_auth, json={
        'exposure_id': newest['exposure_id'], 'client_attempt_id': 'after-revision', 'answer': 'A',
    })
    assert after.status_code == 201 and after.json()['earned_points'] == 3
    # 发布新版本之后才提交的旧曝光，仍按原版答案和原版满分判分。
    late = client.post('/api/practice/attempts', headers=student_auth, json={
        'exposure_id': pending_item['exposure_id'], 'client_attempt_id': 'late-old-version', 'answer': 'B',
    })
    assert late.status_code == 201 and late.json()['earned_points'] == 2
    replay = client.post('/api/practice/attempts', headers=student_auth, json=attempt_body)
    assert replay.json()['id'] == before.json()['id'] and replay.json()['earned_points'] == 2
    assert client.post(f'/api/admin/questions/{old_id}/review', headers=auth).status_code == 409
    assert client.post(f'/api/admin/questions/{old_id}/publish', headers=auth).status_code == 409
    db.expire_all()
    assert [snapshot(record) for record in records] == history
    assert db.get(m.AnswerAttempt, after.json()['id']).question_version_id == revised['id']
    assert db.get(m.AnswerAttempt, late.json()['id']).question_version_id == old_id


def test_revision_numbers_increase_even_when_revising_an_older_publication(client, auth, student_auth, db, question):
    original, body = question
    publish(client, auth, original['id'])
    ids = [original['id']]
    for expected_version in (2, 3):
        response = client.post(f"/api/admin/questions/{original['id']}/revisions", headers=auth, json=body)
        assert response.status_code == 201
        assert response.json()['version'] == expected_version
        ids.append(response.json()['id'])
    assert len(set(ids)) == 3
    # 按版本号选最新发布版，而非草稿、发布时间或来源版本号。
    publish(client, auth, ids[2])
    publish(client, auth, ids[1])
    fresh = client.get('/api/practice/next?subject=math&purpose=evaluation', headers=student_auth).json()
    assert fresh['question_version_id'] == ids[2] and fresh['unseen_at_exposure'] is True
    db.expire_all()
    assert db.scalars(select(m.QuestionVersion.version).order_by(m.QuestionVersion.version)).all() == [1, 2, 3]


@pytest.mark.parametrize('state', ['draft', 'reviewed'])
def test_revision_requires_published_version(client, auth, db, question, state):
    original, body = question
    if state == 'reviewed':
        assert client.post(f"/api/admin/questions/{original['id']}/review", headers=auth).status_code == 200
    response = client.post(f"/api/admin/questions/{original['id']}/revisions", headers=auth, json=body)
    assert response.status_code == 409
    assert len(db.scalars(select(m.QuestionVersion)).all()) == 1


def test_revision_must_pass_source_gate_again(client, auth, db, question):
    original, body = question
    publish(client, auth, original['id'])
    response = client.post(f"/api/admin/questions/{original['id']}/revisions", headers=auth, json=body)
    assert response.status_code == 201
    new_id = response.json()['id']
    assert client.post(f'/api/admin/questions/{new_id}/review', headers=auth).status_code == 200
    source = db.get(m.SourceDocument, body['source_document_id'])
    source.verified = False
    db.commit()
    assert client.post(f'/api/admin/questions/{new_id}/publish', headers=auth).status_code == 409
    db.expire_all()
    assert db.get(m.QuestionVersion, new_id).status == 'reviewed'
    assert db.get(m.QuestionVersion, original['id']).status == 'published'


def test_revision_number_collision_rolls_back_without_overwriting(client, auth, db, question, monkeypatch):
    original, body = question
    publish(client, auth, original['id'])
    path = f"/api/admin/questions/{original['id']}/revisions"
    first = client.post(path, headers=auth, json=body)
    assert first.status_code == 201
    # 模拟并行请求读到过期的最大版本号；真实数据库唯一约束必须拒绝重号。
    monkeypatch.setattr(db, 'scalar', lambda *args, **kwargs: 1)
    def stale_read_db():
        yield db
    monkeypatch.setitem(app.dependency_overrides, get_db, stale_read_db)
    assert client.post(path, headers=auth, json={**body, 'correct_answer': 'A'}).status_code == 409
    db.expire_all()
    assert len(db.scalars(select(m.QuestionVersion)).all()) == 2
    assert db.get(m.QuestionVersion, first.json()['id']).correct_answer == 'B'


@pytest.mark.parametrize('case, expected', [('unauthorized', 401), ('missing', 404), ('different_source', 409),
                                           ('invalid_options', 422), ('invalid_points', 422), ('missing_stem', 422)])
def test_revision_rejects_invalid_requests_without_writes(client, auth, db, question, case, expected):
    original, body = question
    publish(client, auth, original['id'])
    path = f"/api/admin/questions/{original['id']}/revisions"
    headers = auth
    if case == 'unauthorized':
        headers = {}
    elif case == 'missing':
        path = '/api/admin/questions/not-found/revisions'
    elif case == 'different_source':
        body = {**body, 'source_document_id': 'different-source'}
    elif case == 'invalid_options':
        body = {**body, 'options': ['A']}
    elif case == 'invalid_points':
        body = {**body, 'max_points': 0}
    elif case == 'missing_stem':
        body = {key: value for key, value in body.items() if key != 'stem'}
    assert client.post(path, headers=headers, json=body).status_code == expected
    assert len(db.scalars(select(m.QuestionVersion)).all()) == 1
