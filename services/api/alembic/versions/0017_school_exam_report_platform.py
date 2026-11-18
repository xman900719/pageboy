"""ST-EXAM-AutoSync R3：分析报告册关联 k12100 平台场次 ID 与考试日期。"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {item["name"] for item in inspector.get_columns("school_exam_reports")}
    indexes = {item["name"] for item in inspector.get_indexes("school_exam_reports")}
    with op.batch_alter_table("school_exam_reports") as batch:
        if "external_exam_id" not in cols:
            batch.add_column(sa.Column("external_exam_id", sa.String(80), nullable=True))
        if "exam_date" not in cols:
            batch.add_column(sa.Column("exam_date", sa.String(10), nullable=True))
        if "ix_school_exam_reports_external_exam_id" not in indexes:
            batch.create_index("ix_school_exam_reports_external_exam_id", ["external_exam_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {item["name"] for item in inspector.get_columns("school_exam_reports")}
    indexes = {item["name"] for item in inspector.get_indexes("school_exam_reports")}
    with op.batch_alter_table("school_exam_reports") as batch:
        if "ix_school_exam_reports_external_exam_id" in indexes:
            batch.drop_index("ix_school_exam_reports_external_exam_id")
        if "exam_date" in cols:
            batch.drop_column("exam_date")
        if "external_exam_id" in cols:
            batch.drop_column("external_exam_id")
