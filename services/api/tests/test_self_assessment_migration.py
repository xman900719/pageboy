"""ST-007：仅在隔离临时 SQLite 库验证 0005 主观自评迁移与条件式增列。"""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, inspect, text


def test_self_assessment_migration(tmp_path):
    api = Path(__file__).resolve().parents[1]
    url = f'sqlite+pysqlite:///{tmp_path}/migration.sqlite3'
    env = dict(os.environ, DATABASE_URL=url)

    def alembic(*args):
        subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=api, env=env, check=True, capture_output=True)

    # 新库路径：0001 按当前 models 建表（question_versions 两新列已存在且可空），插入不引用新列即可。
    alembic('upgrade', '0001')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO source_documents (id,title,subject,rights_status,verified,created_at) VALUES ('src-m5','虚构测试数据：自评迁移','math','unknown',0,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO questions (id,source_document_id,subject) VALUES ('q-m5','src-m5','math')"))
        connection.execute(text("INSERT INTO question_versions (id,question_id,version,status,stem,kind,options,correct_answer,knowledge_ids,max_points,reviewed_by_human,created_at) VALUES ('v1-m5','q-m5',1,'published','虚构测试数据：1+1=?','single_choice','[\"A. 1\", \"B. 2\"]','B','[\"math.arithmetic\"]',2.0,1,CURRENT_TIMESTAMP)"))

    alembic('upgrade', 'head')
    alembic('check')
    inspector = inspect(engine)
    question_columns = {column['name'] for column in inspector.get_columns('question_versions')}
    assert 'group_context' in question_columns
    assert 'media_attachment_id' in question_columns
    assert 'self_assessments' in inspector.get_table_names()

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO exposures (id,learner_id,question_version_id,question_id,purpose,is_unseen_at_exposure,shown_at) VALUES ('exp-m5','owner','v1-m5','q-m5','training',1,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO answer_attempts (id,learner_id,client_attempt_id,exposure_id,question_version_id,answer,earned_points,max_points,scoring_origin,hints_used,created_at) VALUES ('att-m5','owner','k-m5','exp-m5','v1-m5','B',2.0,2.0,'reviewed_answer_key',0,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO self_assessments (id,attempt_id,learner_id,self_earned_points,max_points,scoring_origin,created_at) VALUES ('sa-m5','att-m5','owner',2.0,2.0,'self_assessment',CURRENT_TIMESTAMP)"))

    def duplicate_self_assessment_raises():
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO self_assessments (id,attempt_id,learner_id,self_earned_points,max_points,scoring_origin,created_at) VALUES ('sa-m5-dup','att-m5','owner',1.0,2.0,'self_assessment',CURRENT_TIMESTAMP)"))

    duplicate_self_assessment_raises()

    # 0005 downgrade 仅隔离开发库：删 self_assessments、条件删两新列；既有作答行保留。
    alembic('downgrade', '0004')
    inspector = inspect(engine)
    assert 'self_assessments' not in inspector.get_table_names()
    question_columns = {column['name'] for column in inspector.get_columns('question_versions')}
    assert 'group_context' not in question_columns
    assert 'media_attachment_id' not in question_columns
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM answer_attempts')) == 1

    # 遗留库路径：upgrade head 条件增列（两列均无数据库级 FK——设计修订 2026-10-22：
    # source_attachments 属 0002 表，内联 FK 会让全新 PostgreSQL 库在 0001 即失败；
    # 引用合法性由 add_question/confirm_import/revise_question 三路径应用层校验）并重建 self_assessments。
    alembic('upgrade', 'head')
    alembic('check')
    inspector = inspect(engine)
    question_columns = {column['name'] for column in inspector.get_columns('question_versions')}
    assert {'group_context', 'media_attachment_id'} <= question_columns
    assert 'self_assessments' in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM answer_attempts')) == 1
        assert connection.scalar(text("SELECT group_context FROM question_versions WHERE id='v1-m5'")) is None
        assert connection.scalar(text("SELECT media_attachment_id FROM question_versions WHERE id='v1-m5'")) is None
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO self_assessments (id,attempt_id,learner_id,self_earned_points,max_points,scoring_origin,created_at) VALUES ('sa-m5','att-m5','owner',2.0,2.0,'self_assessment',CURRENT_TIMESTAMP)"))
    duplicate_self_assessment_raises()
    engine.dispose()
