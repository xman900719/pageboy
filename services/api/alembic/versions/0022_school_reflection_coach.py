"""校考失分题「书童陪你想」苏格拉底对话持久化表（0022）。"""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "school_reflection_coach_sessions" not in tables:
        op.create_table(
            "school_reflection_coach_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("learner_id", sa.String(40), nullable=False, index=True, server_default="owner"),
            sa.Column(
                "school_exam_item_id",
                sa.String(36),
                sa.ForeignKey("school_exam_items.id"),
                nullable=False,
                unique=True,
            ),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("draft_summary", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if "school_reflection_coach_turns" not in tables:
        op.create_table(
            "school_reflection_coach_turns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "session_id",
                sa.String(36),
                sa.ForeignKey("school_reflection_coach_sessions.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("turn_index", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("model_used", sa.String(80), nullable=True),
            sa.Column("sanitized_guard_triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("session_id", "turn_index", name="uq_school_coach_session_turn"),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "school_reflection_coach_turns" in tables:
        op.drop_table("school_reflection_coach_turns")
    if "school_reflection_coach_sessions" in tables:
        op.drop_table("school_reflection_coach_sessions")
