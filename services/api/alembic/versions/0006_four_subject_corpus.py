"""四科语料增量：来源类别/哈希/状态列 + 勘误、题源区域、知识点版本化、题-知识点关联、研究记录。

- source_documents 新增 5 个带默认值的列（既有行回填为 unclassified/recorded/pending，不改内容）；
- 其余均为新表，不触碰既有数据；
- 回退仅用于隔离开发库。
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

NEW_TABLES = ("errata", "question_source_regions", "knowledge_nodes", "knowledge_node_versions", "question_knowledge_links", "research_runs")
NEW_COLUMNS = ("source_class", "sha256", "ingest_status", "review_status", "paper_key")


def upgrade():
    from shutong.database import Base
    from shutong import models  # noqa: F401
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns("source_documents")]
    if "source_class" not in cols:
        op.add_column("source_documents", sa.Column("source_class", sa.String(20), nullable=False, server_default="unclassified"))
    if "sha256" not in cols:
        op.add_column("source_documents", sa.Column("sha256", sa.String(64), nullable=True))
    if "ingest_status" not in cols:
        op.add_column("source_documents", sa.Column("ingest_status", sa.String(20), nullable=False, server_default="recorded"))
    if "review_status" not in cols:
        op.add_column("source_documents", sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"))
    if "paper_key" not in cols:
        op.add_column("source_documents", sa.Column("paper_key", sa.String(40), nullable=True))
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[n] for n in NEW_TABLES])


def downgrade():
    # 仅用于隔离开发库；不对真实库执行。
    from shutong.database import Base
    from shutong import models  # noqa: F401
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[n] for n in reversed(NEW_TABLES)])
    with op.batch_alter_table("source_documents") as b:
        for c in NEW_COLUMNS:
            b.drop_column(c)
