"""主观自评与题型扩展：question_versions 题组文段/听力引用两新列 + self_assessments 新表。

- question_versions 增加题组文段 group_context 与听力媒体引用 media_attachment_id
  （条件式，两列均无数据库级外键——source_attachments 属 0002 表，内联 FK 会使全新
  PostgreSQL 库在 0001 create_all 即失败（SQLite 容忍悬空 REFERENCES、PG 建表即校验，
  2026-10-22 docker 实测捕获）；引用合法性由应用层校验兜底：存在/同源/owner）；
- 新表 self_assessments 为主观自评独立来源记录（attempt 唯一、一次自评不可更新、不进客观证据）；
- 回填需求：无（两列均可空；self_assessments 为新表）；
- 回退仅隔离开发库（条件删两列 + 删 self_assessments）。
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    question_columns = [c["name"] for c in insp.get_columns("question_versions")]
    if "group_context" not in question_columns:
        op.add_column("question_versions", sa.Column("group_context", sa.Text(), nullable=True))
    if "media_attachment_id" not in question_columns:
        op.add_column("question_versions", sa.Column("media_attachment_id", sa.String(36), nullable=True))
    op.create_table("self_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("answer_attempts.id"), nullable=False),
        sa.Column("learner_id", sa.String(40), nullable=False),
        sa.Column("self_earned_points", sa.Float(), nullable=False),
        sa.Column("max_points", sa.Float(), nullable=False),
        sa.Column("scoring_origin", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_self_assessments_learner_id", "self_assessments", ["learner_id"])
    op.create_index("uq_self_assessment_attempt", "self_assessments", ["attempt_id"], unique=True)


def downgrade():
    # 仅用于隔离开发库；不对真实库执行。
    op.drop_table("self_assessments")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    question_columns = [c["name"] for c in insp.get_columns("question_versions")]
    if "media_attachment_id" in question_columns:
        op.drop_column("question_versions", "media_attachment_id")
    if "group_context" in question_columns:
        op.drop_column("question_versions", "group_context")
