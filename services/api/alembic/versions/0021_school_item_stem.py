"""校考失分题新增题干与学生作答字段及防重复解析状态机列（0021）。"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_NEW_COLS = (
    ("stem_text", sa.Text()),
    ("student_answer_text", sa.Text()),
    ("stem_state", sa.String(24)),
    ("stem_source", sa.String(24)),
    ("stem_state_at", sa.DateTime(timezone=True)),
)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "school_exam_items" not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns("school_exam_items")}
    with op.batch_alter_table("school_exam_items") as b:
        for col_name, col_type in _NEW_COLS:
            if col_name not in existing:
                b.add_column(sa.Column(col_name, col_type, nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "school_exam_items" not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns("school_exam_items")}
    with op.batch_alter_table("school_exam_items") as b:
        for col_name, _ in reversed(_NEW_COLS):
            if col_name in existing:
                b.drop_column(col_name)
