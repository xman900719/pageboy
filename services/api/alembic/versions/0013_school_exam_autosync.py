"""ST-EXAM-AUTOSYNC-01：校考试卷发现、严格身份匹配与本人排名快照。

- school_exams 增加可空考试身份元数据与来源标记；既有 title/exam_date/总分语义不变。
- 新增 school_exam_papers（私有原件索引与卷头/匹配证据）、school_exam_scan_runs（扫描审计）、
  school_exam_rank_snapshots（append-only 本人排名，独立于能力证据）。
- 所有新增字段均可空或有安全默认值；升级不覆盖既有已确认成绩、逐题记录或知识点发布版本。
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_EXAM_COLUMNS = (
    ("school_name", sa.String(160)),
    ("grade", sa.String(20)),
    ("exam_type", sa.String(20)),
    ("academic_year", sa.String(20)),
    ("term", sa.String(20)),
    ("series_title", sa.String(160)),
    ("external_exam_id", sa.String(80)),
)


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector, table: str) -> set[str]:
    return {item["name"] for item in inspector.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    exam_columns = {item["name"] for item in inspector.get_columns("school_exams")}
    with op.batch_alter_table("school_exams") as batch:
        for name, column_type in _EXAM_COLUMNS:
            if name not in exam_columns:
                batch.add_column(sa.Column(name, column_type, nullable=True))
        if "source_kind" not in exam_columns:
            batch.add_column(sa.Column("source_kind", sa.String(24), nullable=False, server_default="manual"))
        constraints = {item["name"] for item in inspector.get_unique_constraints("school_exams")}
        if "uq_school_exam_external_identity" not in constraints:
            batch.create_unique_constraint(
                "uq_school_exam_external_identity",
                ["learner_id", "subject", "external_exam_id"],
            )

    inspector = sa.inspect(bind)
    tables = _table_names(inspector)
    if "school_exam_papers" not in tables:
        op.create_table(
            "school_exam_papers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("learner_id", sa.String(40), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("media_type", sa.String(128), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("storage_key", sa.String(32), nullable=False),
            sa.Column("source_kind", sa.String(24), nullable=False, server_default="local_scan"),
            sa.Column("source_name", sa.String(80), nullable=False, server_default="inbox"),
            sa.Column("source_ref", sa.String(255), nullable=False),
            sa.Column("header_text", sa.Text(), nullable=True),
            sa.Column("header_fields", sa.JSON(), nullable=True),
            sa.Column("header_confidence", sa.String(16), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="needs_review"),
            sa.Column("match_state", sa.String(24), nullable=True),
            sa.Column("match_candidates", sa.JSON(), nullable=True),
            sa.Column("school_exam_id", sa.String(36), nullable=True),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["school_exam_id"], ["school_exams.id"]),
            sa.UniqueConstraint("learner_id", "sha256", name="uq_school_exam_paper_owner_sha"),
        )
        op.create_index("ix_school_exam_papers_learner_id", "school_exam_papers", ["learner_id"])
        op.create_index("ix_school_exam_papers_school_exam_id", "school_exam_papers", ["school_exam_id"])

    inspector = sa.inspect(bind)
    if "school_exam_scan_runs" not in _table_names(inspector):
        op.create_table(
            "school_exam_scan_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("learner_id", sa.String(40), nullable=False),
            sa.Column("source_kind", sa.String(24), nullable=False, server_default="local_scan"),
            sa.Column("source_label", sa.String(80), nullable=False, server_default="inbox"),
            sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
            sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("invalid_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("needs_review_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors", sa.JSON(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_school_exam_scan_runs_learner_id", "school_exam_scan_runs", ["learner_id"])

    inspector = sa.inspect(bind)
    if "school_exam_rank_snapshots" not in _table_names(inspector):
        op.create_table(
            "school_exam_rank_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("school_exam_id", sa.String(36), nullable=False),
            sa.Column("learner_id", sa.String(40), nullable=False),
            sa.Column("subject_scope", sa.String(20), nullable=False, server_default="total"),
            sa.Column("scope", sa.String(16), nullable=False),
            sa.Column("rank_value", sa.Integer(), nullable=False),
            sa.Column("participant_count", sa.Integer(), nullable=True),
            sa.Column("percentile", sa.Float(), nullable=True),
            sa.Column("source_name", sa.String(64), nullable=False, server_default="k12100"),
            sa.Column("source_field", sa.String(64), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["school_exam_id"], ["school_exams.id"]),
            sa.UniqueConstraint(
                "school_exam_id",
                "subject_scope",
                "scope",
                "source_field",
                "content_hash",
                name="uq_school_exam_rank_snapshot",
            ),
        )
        op.create_index("ix_school_exam_rank_snapshots_school_exam_id", "school_exam_rank_snapshots", ["school_exam_id"])
        op.create_index("ix_school_exam_rank_snapshots_learner_id", "school_exam_rank_snapshots", ["learner_id"])


def downgrade():
    """仅用于隔离测试库回退；生产如已有排名快照或卷宗索引须先独立备份。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _table_names(inspector)
    if "school_exam_rank_snapshots" in tables:
        op.drop_table("school_exam_rank_snapshots")
    if "school_exam_scan_runs" in tables:
        op.drop_table("school_exam_scan_runs")
    if "school_exam_papers" in tables:
        op.drop_table("school_exam_papers")

    inspector = sa.inspect(bind)
    exam_columns = {item["name"] for item in inspector.get_columns("school_exams")}
    constraints = {item["name"] for item in inspector.get_unique_constraints("school_exams")}
    with op.batch_alter_table("school_exams") as batch:
        if "uq_school_exam_external_identity" in constraints:
            batch.drop_constraint("uq_school_exam_external_identity", type_="unique")
        for name, _ in reversed(_EXAM_COLUMNS):
            if name in exam_columns:
                batch.drop_column(name)
        if "source_kind" in exam_columns:
            batch.drop_column("source_kind")
