"""为学校考试逐题明细补充 OCR/网页同步草稿溯源与推荐知识点候选元数据。

- school_exam_items 新增可空列：
  - draft_source_attachment_id VARCHAR(36)
  - draft_confidence VARCHAR(24)
  - draft_reason TEXT
  - draft_knowledge_candidates JSON
- 仅辅助待核对草稿审核展示，确认后得分与确认门禁语义（INV-04 / AC-EVI-02）保持不变。
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    """在 SQLite 与 PostgreSQL 上幂等添加草稿溯源元数据列。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("school_exam_items")}
    with op.batch_alter_table("school_exam_items") as b:
        if "draft_source_attachment_id" not in cols:
            b.add_column(sa.Column("draft_source_attachment_id", sa.String(36), nullable=True))
        if "draft_confidence" not in cols:
            b.add_column(sa.Column("draft_confidence", sa.String(24), nullable=True))
        if "draft_reason" not in cols:
            b.add_column(sa.Column("draft_reason", sa.Text(), nullable=True))
        if "draft_knowledge_candidates" not in cols:
            b.add_column(sa.Column("draft_knowledge_candidates", sa.JSON(), nullable=True))


def downgrade():
    """仅用于隔离测试库回退；生产库含草稿溯源数据时禁止直接降级。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("school_exam_items")}
    with op.batch_alter_table("school_exam_items") as b:
        for name in (
            "draft_knowledge_candidates",
            "draft_reason",
            "draft_confidence",
            "draft_source_attachment_id",
        ):
            if name in cols:
                b.drop_column(name)
