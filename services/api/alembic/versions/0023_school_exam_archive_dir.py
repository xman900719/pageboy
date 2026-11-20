"""校考统一目录 school-exams 档案路径与附件分类列（0023）。"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def _existing_columns(inspector, table_name: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "school_exams" in tables:
        cols = _existing_columns(inspector, "school_exams")
        if "archive_dir" not in cols:
            op.add_column("school_exams", sa.Column("archive_dir", sa.String(255), nullable=True))

    if "school_paper_attachments" in tables:
        cols = _existing_columns(inspector, "school_paper_attachments")
        if "category" not in cols:
            op.add_column(
                "school_paper_attachments",
                sa.Column("category", sa.String(24), nullable=False, server_default="exam_paper"),
            )
        if "relative_path" not in cols:
            op.add_column("school_paper_attachments", sa.Column("relative_path", sa.String(512), nullable=True))

    if "school_exam_papers" in tables:
        cols = _existing_columns(inspector, "school_exam_papers")
        if "relative_path" not in cols:
            op.add_column("school_exam_papers", sa.Column("relative_path", sa.String(512), nullable=True))

    if "school_exam_reports" in tables:
        cols = _existing_columns(inspector, "school_exam_reports")
        if "relative_path" not in cols:
            op.add_column("school_exam_reports", sa.Column("relative_path", sa.String(512), nullable=True))

    if "school_exam_report_attachments" in tables:
        cols = _existing_columns(inspector, "school_exam_report_attachments")
        if "relative_path" not in cols:
            op.add_column("school_exam_report_attachments", sa.Column("relative_path", sa.String(512), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table_name, col_names in (
        ("school_exam_report_attachments", ("relative_path",)),
        ("school_exam_reports", ("relative_path",)),
        ("school_exam_papers", ("relative_path",)),
        ("school_paper_attachments", ("relative_path", "category")),
        ("school_exams", ("archive_dir",)),
    ):
        if table_name not in tables:
            continue
        cols = _existing_columns(inspector, table_name)
        for col_name in col_names:
            if col_name in cols:
                op.drop_column(table_name, col_name)
