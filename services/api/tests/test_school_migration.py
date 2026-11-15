"""ST-006：仅在隔离临时 SQLite 库验证 0004 学校私卷表迁移与回退。"""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, inspect, text


def test_school_tables_migration(tmp_path):
    api = Path(__file__).resolve().parents[1]
    url = f'sqlite+pysqlite:///{tmp_path}/migration.sqlite3'
    env = dict(os.environ, DATABASE_URL=url)

    def alembic(*args):
        subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=api, env=env, check=True, capture_output=True)

    alembic('upgrade', '0001')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO source_documents (id,title,subject,rights_status,verified,created_at) VALUES ('src-m4','虚构测试数据：迁移题源','math','unknown',0,CURRENT_TIMESTAMP)"))
    alembic('upgrade', 'head')
    alembic('check')

    inspector = inspect(engine)
    assert {'school_exam_items', 'school_paper_attachments'} <= set(inspector.get_table_names())
    item_cols = {col['name'] for col in inspector.get_columns('school_exam_items')}
    assert {
        'error_category',
        'error_note',
        'draft_source_attachment_id',
        'draft_confidence',
        'draft_reason',
        'draft_knowledge_candidates',
    } <= item_cols
    # 唯一性可由 UNIQUE 约束或唯一索引任一形态承载（SQLite 反射两者皆可查）。
    constraints = inspector.get_unique_constraints('school_exam_items')
    unique_indexes = [index for index in inspector.get_indexes('school_exam_items') if index.get('unique')]
    enforcers = [dict(name=c['name'], column_names=c['column_names']) for c in constraints] + unique_indexes
    assert any(sorted(spec['column_names']) == ['question_label', 'school_exam_id'] for spec in enforcers)
    assert 'uq_school_exam_item_label' in {spec['name'] for spec in enforcers}

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO school_exams (id,learner_id,subject,exam_date,title,earned_points,max_points,confirmed_by_user,created_at) VALUES ('exam-m4','owner','math','2026-10-20','虚构测试数据：迁移卷',10,10,1,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO school_exam_items (id,school_exam_id,question_label,knowledge_id,earned_points,max_points,scoring_origin,confirmed_by_user,error_category,error_note,created_at) VALUES ('item-m4','exam-m4','第1题','math.arithmetic',1.0,2.0,'ocr_draft',0,'calculation','虚构测试数据：移项符号抄错',CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO school_paper_attachments (id,school_exam_id,owner_id,filename,media_type,sha256,byte_size,storage_key,created_at) VALUES ('att-m4','exam-m4','owner','虚构测试数据.png','image/png','" + '0' * 64 + "',10,'" + '1' * 32 + "',CURRENT_TIMESTAMP)"))

    def duplicate_label_raises():
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            with engine.begin() as connection:
                for suffix in ('a', 'b'):
                    connection.execute(text(
                        "INSERT INTO school_exam_items (id,school_exam_id,question_label,knowledge_id,earned_points,max_points,scoring_origin,confirmed_by_user,created_at) "
                        f"VALUES ('probe-{suffix}','exam-m4','探重题','math.arithmetic',1.0,1.0,'manual_entry',1,CURRENT_TIMESTAMP)"))

    duplicate_label_raises()

    # 校验 0012 -> 0011 及 0011 -> 0010 降级后再升回 head，字段增删与既往数据约束均完好。
    alembic('downgrade', '0011')
    cols_0011 = {col['name'] for col in inspect(engine).get_columns('school_exam_items')}
    assert 'draft_reason' not in cols_0011 and 'error_category' in cols_0011
    alembic('downgrade', '0010')
    cols_0010 = {col['name'] for col in inspect(engine).get_columns('school_exam_items')}
    assert 'error_category' not in cols_0010 and 'error_note' not in cols_0010
    alembic('upgrade', 'head')
    cols_head = {col['name'] for col in inspect(engine).get_columns('school_exam_items')}
    assert {'error_category', 'error_note', 'draft_source_attachment_id', 'draft_confidence', 'draft_reason', 'draft_knowledge_candidates'} <= cols_head

    alembic('downgrade', '0003')
    names = set(inspect(engine).get_table_names())
    assert 'school_exam_items' not in names and 'school_paper_attachments' not in names
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM source_documents')) == 1  # 基础数据保留
        assert connection.scalar(text('SELECT count(*) FROM school_exams')) == 1  # 0001 基础表行保留，仅 0004 新表被删

    alembic('upgrade', 'head')
    alembic('check')
    duplicate_label_raises()
    engine.dispose()
