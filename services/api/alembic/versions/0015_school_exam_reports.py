"""ST-EXAM-AutoSync-R2：本地分析报告册解析结果（多学科、待人工核对）。"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "school_exam_reports" in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        "school_exam_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learner_id", sa.String(40), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("academic_year", sa.String(20), nullable=True),
        sa.Column("grade", sa.String(20), nullable=True),
        sa.Column("exam_type", sa.String(40), nullable=True),
        sa.Column("exam_sequence", sa.Integer(), nullable=True),
        sa.Column("report_time", sa.String(80), nullable=True),
        sa.Column("report_total_score", sa.Float(), nullable=True),
        sa.Column("report_total_max", sa.Float(), nullable=True),
        sa.Column("total_class_rank", sa.Integer(), nullable=True),
        sa.Column("total_grade_rank", sa.Integer(), nullable=True),
        sa.Column("total_participants", sa.Integer(), nullable=True),
        sa.Column("listed_subject_score", sa.Float(), nullable=True),
        sa.Column("listed_subject_max", sa.Float(), nullable=True),
        sa.Column("scope_status", sa.String(32), nullable=False, server_default="NEEDS_REVIEW"),
        sa.Column("pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="low"),
        sa.Column("status", sa.String(24), nullable=False, server_default="needs_review"),
        sa.Column("match_state", sa.String(24), nullable=False, server_default="NEEDS_REVIEW"),
        sa.Column("linked_exam_ids", sa.JSON(), nullable=True),
        sa.Column("subjects", sa.JSON(), nullable=True),
        sa.Column("questions", sa.JSON(), nullable=True),
        sa.Column("answer_card_pages", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("learner_id", "sha256", name="uq_school_exam_report_owner_sha"),
    )
    op.create_index("ix_school_exam_reports_learner_id", "school_exam_reports", ["learner_id"])


def downgrade():
    op.drop_index("ix_school_exam_reports_learner_id", table_name="school_exam_reports")
    op.drop_table("school_exam_reports")
