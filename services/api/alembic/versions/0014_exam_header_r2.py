"""ST-EXAM-AutoSync R2：考试类型原标签与本人排名归属校验字段。

- school_exams.exam_type_label：保留“阶段检测”等真实非标准类型，避免折叠为 other 后误配。
- school_exam_rank_snapshots.ownership_status / ownership_basis：标明本人归属校验依据；
  历史排名快照无法追溯归属时统一标为 unverified，不伪造 verified。
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    exam_cols = {item["name"] for item in inspector.get_columns("school_exams")}
    with op.batch_alter_table("school_exams") as batch:
        if "exam_type_label" not in exam_cols:
            batch.add_column(sa.Column("exam_type_label", sa.String(40), nullable=True))

    inspector = sa.inspect(bind)
    rank_cols = {item["name"] for item in inspector.get_columns("school_exam_rank_snapshots")}
    with op.batch_alter_table("school_exam_rank_snapshots") as batch:
        if "ownership_status" not in rank_cols:
            batch.add_column(
                sa.Column("ownership_status", sa.String(20), nullable=False, server_default="unverified")
            )
        if "ownership_basis" not in rank_cols:
            batch.add_column(sa.Column("ownership_basis", sa.String(64), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    rank_cols = {item["name"] for item in inspector.get_columns("school_exam_rank_snapshots")}
    with op.batch_alter_table("school_exam_rank_snapshots") as batch:
        if "ownership_basis" in rank_cols:
            batch.drop_column("ownership_basis")
        if "ownership_status" in rank_cols:
            batch.drop_column("ownership_status")
    inspector = sa.inspect(bind)
    exam_cols = {item["name"] for item in inspector.get_columns("school_exams")}
    with op.batch_alter_table("school_exams") as batch:
        if "exam_type_label" in exam_cols:
            batch.drop_column("exam_type_label")
