"""ST-EXAM-AutoSync-R2：分析报告册答题卡页私有附件索引。"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "school_exam_report_attachments" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "school_exam_report_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("learner_id", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(20), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(64), nullable=False, server_default="image/png"),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("rotation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["school_exam_reports.id"]),
        sa.UniqueConstraint("report_id", "subject", "page_number", name="uq_school_exam_report_card_page"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_school_exam_report_attachments_report_id", "school_exam_report_attachments", ["report_id"])


def downgrade():
    op.drop_index("ix_school_exam_report_attachments_report_id", table_name="school_exam_report_attachments")
    op.drop_table("school_exam_report_attachments")
