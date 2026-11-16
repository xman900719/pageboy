"""ST-EXAM-AUTOSYNC-01：0013 迁移升级、降级、再升级与唯一约束验证（隔离 SQLite）。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, inspect, text


def _alembic(api: Path, url: str, *args: str):
    env = dict(os.environ, DATABASE_URL=url)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=api,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_school_exam_autosync_migration_roundtrip_and_identity_uniqueness(tmp_path):
    api = Path(__file__).resolve().parents[1]
    url = f"sqlite+pysqlite:///{tmp_path}/autosync.sqlite3"
    _alembic(api, url, "upgrade", "0012")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO school_exams "
                "(id,learner_id,subject,exam_date,title,earned_points,max_points,confirmed_by_user,created_at) "
                "VALUES ('exam-old','owner','math','2026-10-20','虚构测试数据：历史已确认卷',88,100,1,CURRENT_TIMESTAMP)"
            )
        )

    _alembic(api, url, "upgrade", "head")
    inspector = inspect(engine)
    assert {
        "school_exam_papers",
        "school_exam_scan_runs",
        "school_exam_rank_snapshots",
        "school_exam_reports",
        "school_exam_report_attachments",
    } <= set(inspector.get_table_names())
    exam_columns = {column["name"] for column in inspector.get_columns("school_exams")}
    assert {
        "school_name",
        "grade",
        "exam_type",
        "exam_type_label",
        "academic_year",
        "term",
        "series_title",
        "external_exam_id",
        "source_kind",
    } <= exam_columns
    rank_columns = {column["name"] for column in inspector.get_columns("school_exam_rank_snapshots")}
    assert {
        "rank_value",
        "participant_count",
        "source_field",
        "content_hash",
        "ownership_status",
        "ownership_basis",
        "review_status",
    } <= rank_columns

    with engine.begin() as connection:
        preserved = connection.execute(
            text("SELECT earned_points,max_points,confirmed_by_user FROM school_exams WHERE id='exam-old'")
        ).one()
        assert tuple(preserved) == (88, 100, 1)
        connection.execute(
            text("UPDATE school_exams SET external_exam_id='platform-001' WHERE id='exam-old'")
        )
        connection.execute(
            text(
                "INSERT INTO school_exams "
                "(id,learner_id,subject,exam_date,title,earned_points,max_points,confirmed_by_user,created_at,external_exam_id) "
                "VALUES ('exam-other-subject','owner','chinese','2026-10-20','虚构测试数据：语文',90,100,1,CURRENT_TIMESTAMP,'platform-001')"
            )
        )

    def duplicate_external_identity_raises():
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO school_exams "
                        "(id,learner_id,subject,exam_date,title,earned_points,max_points,confirmed_by_user,created_at,external_exam_id) "
                        "VALUES ('exam-duplicate','owner','math','2026-10-20','虚构测试数据：重复',90,100,1,CURRENT_TIMESTAMP,'platform-001')"
                    )
                )

    duplicate_external_identity_raises()

    # 降级回 0012：只移除 0013 新增结构，历史成绩行保留。
    _alembic(api, url, "downgrade", "0012")
    downgraded = inspect(engine)
    assert "school_exam_papers" not in set(downgraded.get_table_names())
    assert "school_exam_reports" not in set(downgraded.get_table_names())
    assert "school_exam_report_attachments" not in set(downgraded.get_table_names())
    downgraded_columns = {column["name"] for column in downgraded.get_columns("school_exams")}
    assert "external_exam_id" not in downgraded_columns and "source_kind" not in downgraded_columns
    assert "exam_type_label" not in downgraded_columns
    with engine.connect() as connection:
        preserved = connection.execute(
            text("SELECT earned_points,max_points,confirmed_by_user FROM school_exams WHERE id='exam-old'")
        ).one()
        assert tuple(preserved) == (88, 100, 1)

    _alembic(api, url, "upgrade", "head")
    _alembic(api, url, "check")
    assert {
        "school_exam_papers",
        "school_exam_scan_runs",
        "school_exam_rank_snapshots",
        "school_exam_reports",
        "school_exam_report_attachments",
    } <= set(inspect(engine).get_table_names())
    assert "exam_type_label" in {column["name"] for column in inspect(engine).get_columns("school_exams")}
    with engine.begin() as connection:
        connection.execute(text("UPDATE school_exams SET external_exam_id='platform-001' WHERE id='exam-old'"))
        connection.execute(text("UPDATE school_exams SET external_exam_id='platform-001' WHERE id='exam-other-subject'"))
    duplicate_external_identity_raises()
    engine.dispose()
