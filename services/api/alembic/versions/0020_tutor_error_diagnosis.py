"""完善 AI 引导对话防泄题标记字段并新增管理端 AI 错因诊断与三选一对策表。"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "ai_tutor_turns" in tables:
        cols = {c["name"] for c in inspector.get_columns("ai_tutor_turns")}
        if "sanitized_guard_triggered" not in cols:
            with op.batch_alter_table("ai_tutor_turns") as b:
                b.add_column(
                    sa.Column(
                        "sanitized_guard_triggered",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )

    if "ai_error_diagnoses" not in tables:
        op.create_table(
            "ai_error_diagnoses",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("learner_id", sa.String(40), nullable=False, index=True),
            sa.Column(
                "attempt_id",
                sa.String(36),
                sa.ForeignKey("answer_attempts.id"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "tutor_session_id",
                sa.String(36),
                sa.ForeignKey("ai_tutor_sessions.id"),
                nullable=True,
            ),
            sa.Column(
                "question_version_id",
                sa.String(36),
                sa.ForeignKey("question_versions.id"),
                nullable=False,
            ),
            sa.Column("subject", sa.String(20), nullable=False, index=True),
            sa.Column("root_cause_summary", sa.Text(), nullable=False),
            sa.Column("cognitive_gap_type", sa.String(40), nullable=False),
            sa.Column("evidence_from_dialogue", sa.Text(), nullable=False),
            sa.Column("solutions", sa.JSON(), nullable=False),
            sa.Column("selected_option_id", sa.String(20), nullable=True),
            sa.Column("admin_note", sa.Text(), nullable=True),
            sa.Column("model_used", sa.String(80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "ai_error_diagnoses" in tables:
        op.drop_table("ai_error_diagnoses")

    if "ai_tutor_turns" in tables:
        cols = {c["name"] for c in inspector.get_columns("ai_tutor_turns")}
        if "sanitized_guard_triggered" in cols:
            with op.batch_alter_table("ai_tutor_turns") as b:
                b.drop_column("sanitized_guard_triggered")
