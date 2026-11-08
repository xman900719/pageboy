"""数学知识库与审核发布扩展：新增条款关联、审核详情列及版本发布快照表。

- knowledge_node_versions 新增 source_clause_ids, reviewer_id, review_opinion, reviewed_at 列；
- 新增 knowledge_taxonomy_releases 表，记录版本快照；
- 不触碰存量旧数据，回退仅用于隔离开发库。
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

NEW_TABLES = ("knowledge_taxonomy_releases",)
NEW_COLUMNS = ("source_clause_ids", "reviewer_id", "review_opinion", "reviewed_at")


def upgrade():
    from shutong.database import Base
    from shutong import models  # noqa: F401
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("knowledge_node_versions")]
    if "source_clause_ids" not in cols:
        op.add_column("knowledge_node_versions", sa.Column("source_clause_ids", sa.JSON(), nullable=True))
    if "reviewer_id" not in cols:
        op.add_column("knowledge_node_versions", sa.Column("reviewer_id", sa.String(40), nullable=True))
    if "review_opinion" not in cols:
        op.add_column("knowledge_node_versions", sa.Column("review_opinion", sa.Text(), nullable=True))
    if "reviewed_at" not in cols:
        op.add_column("knowledge_node_versions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[n] for n in NEW_TABLES])


def downgrade():
    from shutong.database import Base
    from shutong import models  # noqa: F401
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[n] for n in reversed(NEW_TABLES)])
    with op.batch_alter_table("knowledge_node_versions") as b:
        for c in NEW_COLUMNS:
            b.drop_column(c)
