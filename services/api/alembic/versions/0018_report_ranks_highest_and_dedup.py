"""ST-EXAM-AutoSync：排名最高分字段与报告平台场次唯一索引。"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    exam_cols = {item["name"] for item in inspector.get_columns("school_exams")}
    with op.batch_alter_table("school_exams") as batch:
        if "class_highest" not in exam_cols:
            batch.add_column(sa.Column("class_highest", sa.Float(), nullable=True))
        if "grade_highest" not in exam_cols:
            batch.add_column(sa.Column("grade_highest", sa.Float(), nullable=True))

    rank_cols = {item["name"] for item in inspector.get_columns("school_exam_rank_snapshots")}
    with op.batch_alter_table("school_exam_rank_snapshots") as batch:
        if "highest_score" not in rank_cols:
            batch.add_column(sa.Column("highest_score", sa.Float(), nullable=True))

    report_cols = {item["name"] for item in inspector.get_columns("school_exam_reports")}
    report_indexes = {item["name"] for item in inspector.get_indexes("school_exam_reports")}
    with op.batch_alter_table("school_exam_reports") as batch:
        if "total_class_highest" not in report_cols:
            batch.add_column(sa.Column("total_class_highest", sa.Float(), nullable=True))
        if "total_grade_highest" not in report_cols:
            batch.add_column(sa.Column("total_grade_highest", sa.Float(), nullable=True))
        if "uq_school_exam_report_owner_ext_id" not in report_indexes:
            batch.create_index(
                "uq_school_exam_report_owner_ext_id",
                ["learner_id", "external_exam_id"],
                unique=True,
                sqlite_where=sa.text("external_exam_id IS NOT NULL"),
                postgresql_where=sa.text("external_exam_id IS NOT NULL"),
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    report_cols = {item["name"] for item in inspector.get_columns("school_exam_reports")}
    report_indexes = {item["name"] for item in inspector.get_indexes("school_exam_reports")}
    with op.batch_alter_table("school_exam_reports") as batch:
        if "uq_school_exam_report_owner_ext_id" in report_indexes:
            batch.drop_index("uq_school_exam_report_owner_ext_id")
        if "total_grade_highest" in report_cols:
            batch.drop_column("total_grade_highest")
        if "total_class_highest" in report_cols:
            batch.drop_column("total_class_highest")

    rank_cols = {item["name"] for item in inspector.get_columns("school_exam_rank_snapshots")}
    with op.batch_alter_table("school_exam_rank_snapshots") as batch:
        if "highest_score" in rank_cols:
            batch.drop_column("highest_score")

    exam_cols = {item["name"] for item in inspector.get_columns("school_exams")}
    with op.batch_alter_table("school_exams") as batch:
        if "grade_highest" in exam_cols:
            batch.drop_column("grade_highest")
        if "class_highest" in exam_cols:
            batch.drop_column("class_highest")
