"""扩展原件附件与校卷附件的 media_type 列宽度至 128 字符，兼容 DOCX 等完整 MIME 类型。"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

ATTACHMENT_TABLES = ("source_attachments", "school_paper_attachments")


def upgrade():
    """在 PostgreSQL 与 SQLite 上将附件表 media_type 列从 VARCHAR(32) 扩展到 VARCHAR(128)。"""
    for table in ATTACHMENT_TABLES:
        with op.batch_alter_table(table) as b:
            b.alter_column(
                "media_type",
                existing_type=sa.String(32),
                type_=sa.String(128),
                existing_nullable=False,
            )


def downgrade():
    """仅用于隔离测试库回退；生产库含 DOCX 记录时禁止直接降级。"""
    for table in reversed(ATTACHMENT_TABLES):
        with op.batch_alter_table(table) as b:
            b.alter_column(
                "media_type",
                existing_type=sa.String(128),
                type_=sa.String(32),
                existing_nullable=False,
            )
