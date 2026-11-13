"""新增选学隔离字段、综合练习回合及 AI 引导讲解会话表。

- knowledge_nodes 新增 is_elective 列（关闭 TASK-ENG-ELEC-01）；
- 新增 practice_sessions / practice_session_items 表支撑智能综合编制与结算；
- 新增 ai_tutor_sessions / ai_tutor_turns 表支撑多轮引导式错题讲解。
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    kn_cols = {c["name"] for c in inspector.get_columns("knowledge_nodes")}
    if "is_elective" not in kn_cols:
        with op.batch_alter_table("knowledge_nodes") as b:
            b.add_column(
                sa.Column("is_elective", sa.Boolean(), nullable=False, server_default=sa.false())
            )

    if "practice_sessions" not in tables:
        op.create_table(
            "practice_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("learner_id", sa.String(40), nullable=False, index=True),
            sa.Column("subject", sa.String(20), nullable=False),
            sa.Column("purpose", sa.String(20), nullable=False, server_default="training"),
            sa.Column("target_count", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("composition_summary", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "practice_session_items" not in tables:
        op.create_table(
            "practice_session_items",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("practice_sessions.id"), nullable=False, index=True),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("question_id", sa.String(36), sa.ForeignKey("questions.id"), nullable=False),
            sa.Column("question_version_id", sa.String(36), sa.ForeignKey("question_versions.id"), nullable=False),
            sa.Column("exposure_id", sa.String(36), sa.ForeignKey("exposures.id"), nullable=True),
            sa.Column("target_knowledge_codes", sa.JSON(), nullable=False),
            sa.Column("selection_reason", sa.String(200), nullable=False),
            sa.UniqueConstraint("session_id", "seq", name="uq_practice_session_seq"),
        )

    if "ai_tutor_sessions" not in tables:
        op.create_table(
            "ai_tutor_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("learner_id", sa.String(40), nullable=False, index=True),
            sa.Column("attempt_id", sa.String(36), sa.ForeignKey("answer_attempts.id"), nullable=False, unique=True),
            sa.Column("question_version_id", sa.String(36), sa.ForeignKey("question_versions.id"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if "ai_tutor_turns" not in tables:
        op.create_table(
            "ai_tutor_turns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tutor_session_id", sa.String(36), sa.ForeignKey("ai_tutor_sessions.id"), nullable=False, index=True),
            sa.Column("turn_index", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("model_used", sa.String(80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("tutor_session_id", "turn_index", name="uq_tutor_session_turn"),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for tbl in ["ai_tutor_turns", "ai_tutor_sessions", "practice_session_items", "practice_sessions"]:
        if tbl in tables:
            op.drop_table(tbl)

    kn_cols = {c["name"] for c in inspector.get_columns("knowledge_nodes")}
    if "is_elective" in kn_cols:
        with op.batch_alter_table("knowledge_nodes") as b:
            b.drop_column("is_elective")
