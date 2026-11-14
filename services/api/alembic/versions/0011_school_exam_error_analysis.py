"""为学校考试逐题明细新增结构化错因分类与复盘备注字段（支持错题分析与跨场次对比）。

- school_exam_items 新增可空列 error_category（VARCHAR(32)）与 error_note（TEXT）；
- 满分题与仅总分考试均保持为空；事后补充复盘不改写已核对得分与确认状态（INV-04）。
"""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    """在 SQLite 与 PostgreSQL 上为 school_exam_items 添加错因分类与复盘备注列。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("school_exam_items")}
    with op.batch_alter_table("school_exam_items") as b:
        if "error_category" not in cols:
            b.add_column(sa.Column("error_category", sa.String(32), nullable=True))
        if "error_note" not in cols:
            b.add_column(sa.Column("error_note", sa.Text(), nullable=True))


def downgrade():
    """仅用于隔离测试库回退；生产库含复盘数据时禁止直接降级。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("school_exam_items")}
    with op.batch_alter_table("school_exam_items") as b:
        if "error_note" in cols:
            b.drop_column("error_note")
        if "error_category" in cols:
            b.drop_column("error_category")
