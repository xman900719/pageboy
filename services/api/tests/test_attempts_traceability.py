"""ST-007：使用虚构测试数据验证作答评分来源的可追溯列表。"""
from contextlib import contextmanager

from sqlalchemy import select

from shutong import models as m
from shutong.database import get_db
from shutong.main import app


@contextmanager
def database():
    yield from app.dependency_overrides[get_db]()


def make_source(client, auth, subject, title):
    response = client.post('/api/admin/sources', headers=auth, json={
        'title': title, 'subject': subject, 'rights_status': 'personal_use_reviewed', 'verified': True,
    })
    assert response.status_code == 201
    return response.json()['id']


def publish_question(client, auth, source_id, **overrides):
    body = {
        'source_document_id': source_id, 'stem': '虚构测试数据：1+1=?', 'kind': 'single_choice',
        'options': ['A. 1', 'B. 2'], 'correct_answer': 'B',
        'knowledge_ids': ['math.arithmetic'], 'max_points': 2,
    }
    body.update(overrides)
    created = client.post('/api/admin/questions', headers=auth, json=body)
    assert created.status_code == 201
    version_id = created.json()['id']
    assert client.post(f'/api/admin/questions/{version_id}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 200
    return version_id


def practice_next(client, auth, subject='math'):
    response = client.get(f'/api/practice/next?subject={subject}', headers=auth)
    assert response.status_code == 200
    return response.json()


def submit_answer(client, auth, item, answer, key):
    response = client.post('/api/practice/attempts', headers=auth, json={
        'client_attempt_id': key, 'exposure_id': item['exposure_id'], 'answer': answer,
    })
    assert response.status_code == 201
    return response.json()


def test_attempts_list_reports_origins_and_self_assessment(client, admin_auth, student_auth):
    source = make_source(client, admin_auth, 'math', '虚构测试数据：溯源题源')
    single = publish_question(client, admin_auth, source, stem='虚构测试数据：1+1=?')
    short = publish_question(client, admin_auth, source,
                             stem='虚构测试数据：解方程 x^2+2x+1=0，写出 x 的值', kind='short_answer',
                             options=[], correct_answer='x=-1', knowledge_ids=['math.arithmetic'], max_points=2)
    subjective = publish_question(client, admin_auth, source, stem='虚构测试数据：解答并写出过程：计算 3+5×2',
                                  kind='subjective', options=[], correct_answer='先算乘法：5×2=10；再算加法：3+10=13',
                                  knowledge_ids=['math.arithmetic'], max_points=3)

    single_item = practice_next(client, student_auth)
    assert single_item['question_version_id'] == single
    single_attempt = submit_answer(client, student_auth, single_item, 'B', 'trace-single')
    short_item = practice_next(client, student_auth)
    assert short_item['question_version_id'] == short
    short_attempt = submit_answer(client, student_auth, short_item, '  X=-1  ', 'trace-short')
    subjective_item = practice_next(client, student_auth)
    assert subjective_item['question_version_id'] == subjective
    subjective_attempt = submit_answer(client, student_auth, subjective_item, '3+5×2=13', 'trace-subjective')

    assessed = client.post(f"/api/practice/attempts/{subjective_attempt['id']}/self-assessment",
                           headers=student_auth, json={'self_earned_points': 2})
    assert assessed.status_code == 201

    # 他者作答行用于 owner 范围断言：列表绝不混入非本人的评分来源记录。
    with database() as db:
        question_id = db.scalar(select(m.QuestionVersion.question_id).where(m.QuestionVersion.id == single))
        foreign_exposure = m.Exposure(learner_id='someone-else', question_id=question_id,
                                      question_version_id=single, purpose='training',
                                      is_unseen_at_exposure=True)
        db.add(foreign_exposure)
        db.commit()
        foreign = m.AnswerAttempt(learner_id='someone-else', client_attempt_id='foreign-trace',
                                  exposure_id=foreign_exposure.id, question_version_id=single,
                                  answer='B', earned_points=2.0, max_points=2.0,
                                  scoring_origin='reviewed_answer_key')
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id

    response = client.get('/api/practice/attempts?subject=math', headers=student_auth)
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 3
    assert [entry['question_version_id'] for entry in entries] == [subjective, short, single]
    expected_keys = {'id', 'question_version_id', 'purpose', 'kind', 'answer', 'earned_points',
                     'max_points', 'scoring_origin', 'hints_used', 'self_assessment', 'created_at'}
    for entry in entries:
        assert set(entry) == expected_keys
    by_version = {entry['question_version_id']: entry for entry in entries}
    assert by_version[single]['scoring_origin'] == 'reviewed_answer_key'
    assert by_version[single]['earned_points'] == 2
    assert by_version[single]['self_assessment'] is None
    assert by_version[short]['scoring_origin'] == 'reviewed_answer_key'
    assert by_version[short]['earned_points'] == 2
    assert by_version[short]['self_assessment'] is None
    subjective_entry = by_version[subjective]
    assert subjective_entry['scoring_origin'] == 'ungraded_subjective'
    assert subjective_entry['earned_points'] is None
    self_record = subjective_entry['self_assessment']
    assert self_record['id'] == assessed.json()['id']
    assert self_record['self_earned_points'] == 2
    assert self_record['max_points'] == 3
    assert self_record['scoring_origin'] == 'self_assessment'
    own_ids = {single_attempt['id'], short_attempt['id'], subjective_attempt['id']}
    assert {entry['id'] for entry in entries} == own_ids
    assert foreign_id not in {entry['id'] for entry in entries}


def test_attempts_list_requires_auth_and_subject(client, student_auth):
    assert client.get('/api/practice/attempts?subject=math').status_code == 401
    assert client.get('/api/practice/attempts', headers=student_auth).status_code == 422
