"""知识点版本快照历史父级列扩展：新增 parent_node_id 与 parent_code 列。

- knowledge_node_versions 新增 parent_node_id 与 parent_code 列；
- 对历史已存在旧版本记录，若未记录父级信息，诚实记录为 UNKNOWN，绝不伪造历史事实；
- 支撑层级变更追溯与审核状态重置。
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

NEW_COLUMNS = ("parent_node_id", "parent_code")


def upgrade():
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("knowledge_node_versions")]
    with op.batch_alter_table("knowledge_node_versions") as b:
        if "parent_node_id" not in cols:
            b.add_column(sa.Column("parent_node_id", sa.String(36), sa.ForeignKey("knowledge_nodes.id", name="fk_knv_parent_node_id"), nullable=True))
        if "parent_code" not in cols:
            b.add_column(sa.Column("parent_code", sa.String(80), nullable=True))

    # 对历史存量旧版本数据，诚实记录为 UNKNOWN，绝不伪造过去层级事实
    bind.execute(
        sa.text("UPDATE knowledge_node_versions SET parent_code = 'UNKNOWN' WHERE parent_code IS NULL")
    )


def downgrade():
    with op.batch_alter_table("knowledge_node_versions") as b:
        for c in NEW_COLUMNS:
            b.drop_column(c)
