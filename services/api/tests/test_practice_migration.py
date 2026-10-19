"""ST-004：仅在隔离临时 SQLite 库验证 0003 约束迁移、回填与回退。"""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, inspect, text


def test_practice_constraints_migration(tmp_path):
    api = Path(__file__).resolve().parents[1]
    url = f'sqlite+pysqlite:///{tmp_path}/migration.sqlite3'
    env = dict(os.environ, DATABASE_URL=url)

    def alembic(*args):
        subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=api, env=env, check=True, capture_output=True)

    alembic('upgrade', '0001')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO source_documents (id,title,subject,rights_status,verified,created_at) VALUES ('src-m3','虚构测试数据：迁移','math','unknown',0,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO questions (id,source_document_id,subject) VALUES ('q-m3','src-m3','math')"))
        connection.execute(text("INSERT INTO question_versions (id,question_id,version,status,stem,kind,options,correct_answer,knowledge_ids,max_points,reviewed_by_human,created_at) VALUES ('v1-m3','q-m3',1,'published','虚构测试数据：1+1=?','single_choice','[\"A. 1\", \"B. 2\"]','B','[\"math.arithmetic\"]',2.0,1,CURRENT_TIMESTAMP)"))
    alembic('upgrade', 'head')
    alembic('check')

    inspector = inspect(engine)
    assert 'question_id' in {column['name'] for column in inspector.get_columns('exposures')}
    assert 'uq_exposure_first_unseen' in {index['name'] for index in inspector.get_indexes('exposures')}
    assert 'uq_attempt_exposure' in {index['name'] for index in inspector.get_indexes('answer_attempts')}

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO exposures (id,learner_id,question_version_id,question_id,purpose,is_unseen_at_exposure,shown_at) VALUES ('exp-m3','owner','v1-m3','q-m3','training',1,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO answer_attempts (id,learner_id,client_attempt_id,exposure_id,question_version_id,answer,earned_points,max_points,scoring_origin,hints_used,created_at) VALUES ('att-m3','owner','k-m3','exp-m3','v1-m3','B',2.0,2.0,'reviewed_answer_key',0,CURRENT_TIMESTAMP)"))

    def duplicate_unseen_exposure_raises():
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO exposures (id,learner_id,question_version_id,question_id,purpose,is_unseen_at_exposure,shown_at) VALUES ('exp-m3-dup','owner','v1-m3','q-m3','training',1,CURRENT_TIMESTAMP)"))

    def duplicate_attempt_for_exposure_raises():
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO answer_attempts (id,learner_id,client_attempt_id,exposure_id,question_version_id,answer,earned_points,max_points,scoring_origin,hints_used,created_at) VALUES ('att-m3-dup','owner','k-m3-dup','exp-m3','v1-m3','A',0.0,2.0,'reviewed_answer_key',0,CURRENT_TIMESTAMP)"))

    duplicate_unseen_exposure_raises()
    duplicate_attempt_for_exposure_raises()

    alembic('downgrade', '0002')
    inspector = inspect(engine)
    assert 'question_id' not in {column['name'] for column in inspector.get_columns('exposures')}
    assert 'uq_exposure_first_unseen' not in {index['name'] for index in inspector.get_indexes('exposures')}
    assert 'uq_attempt_exposure' not in {index['name'] for index in inspector.get_indexes('answer_attempts')}
    with engine.connect() as connection:
        for table in ('source_documents', 'questions', 'question_versions', 'exposures', 'answer_attempts'):
            assert connection.scalar(text(f'SELECT count(*) FROM {table}')) == 1

    alembic('upgrade', 'head')
    alembic('check')
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT question_id FROM exposures WHERE id='exp-m3'")) == 'q-m3'
        assert connection.scalar(text('SELECT count(*) FROM exposures WHERE question_id IS NULL')) == 0

    duplicate_unseen_exposure_raises()
    duplicate_attempt_for_exposure_raises()
    engine.dispose()
