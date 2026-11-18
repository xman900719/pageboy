"""ST-EXAM-AutoSync：报告规范场次唯一键与附件同考同哈希唯一约束。"""

from alembic import op
import sqlalchemy as sa

from shutong.school_exam_matcher import build_canonical_exam_key

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. 清理 school_paper_attachments 中极早期可能存在的 (school_exam_id, sha256) 重复行
    att_rows = bind.execute(
        sa.text(
            "SELECT id, school_exam_id, sha256, filename, created_at "
            "FROM school_paper_attachments ORDER BY created_at ASC, id ASC"
        )
    ).mappings().all()
    seen_exam_sha: set[tuple[str, str]] = set()
    dup_att_ids: list[str] = []
    for row in att_rows:
        key = (str(row["school_exam_id"]), str(row["sha256"]))
        if key in seen_exam_sha:
            dup_att_ids.append(str(row["id"]))
        else:
            seen_exam_sha.add(key)
    for dup_id in dup_att_ids:
        bind.execute(sa.text("DELETE FROM school_paper_attachments WHERE id = :id"), {"id": dup_id})

    att_uqs = {item["name"] for item in inspector.get_unique_constraints("school_paper_attachments")}
    with op.batch_alter_table("school_paper_attachments") as batch:
        if "uq_school_paper_attachment_exam_sha" not in att_uqs:
            batch.create_unique_constraint(
                "uq_school_paper_attachment_exam_sha",
                ["school_exam_id", "sha256"],
            )

    # 2. school_exam_reports 增加 canonical_exam_key 并去重后建立部分唯一索引
    report_cols = {item["name"] for item in inspector.get_columns("school_exam_reports")}
    if "canonical_exam_key" not in report_cols:
        with op.batch_alter_table("school_exam_reports") as batch:
            batch.add_column(sa.Column("canonical_exam_key", sa.String(120), nullable=True))

    rep_rows = bind.execute(
        sa.text(
            "SELECT id, learner_id, external_exam_id, academic_year, grade, exam_type, "
            "exam_sequence, title, exam_date, pages "
            "FROM school_exam_reports ORDER BY created_at DESC, id DESC"
        )
    ).mappings().all()
    by_owner_key: dict[tuple[str, str], list[dict]] = {}
    for row in rep_rows:
        ckey = build_canonical_exam_key(
            academic_year=row["academic_year"],
            grade=row["grade"],
            exam_type=row["exam_type"],
            exam_sequence=row["exam_sequence"],
            title=row["title"],
            exam_date=row["exam_date"],
        )
        if not ckey:
            continue
        by_owner_key.setdefault((str(row["learner_id"]), ckey), []).append(dict(row))

    for (learner_id, ckey), grp in by_owner_key.items():
        grp.sort(
            key=lambda r: (
                bool(r["external_exam_id"]),
                int(r["pages"] or 0),
                bool(r["exam_date"]),
                str(r["id"]),
            ),
            reverse=True,
        )
        winner = grp[0]
        for loser in grp[1:]:
            bind.execute(
                sa.text("DELETE FROM school_exam_report_attachments WHERE report_id = :rid"),
                {"rid": loser["id"]},
            )
            bind.execute(
                sa.text("DELETE FROM school_exam_reports WHERE id = :rid"),
                {"rid": loser["id"]},
            )
        bind.execute(
            sa.text("UPDATE school_exam_reports SET canonical_exam_key = :ckey WHERE id = :rid"),
            {"ckey": ckey, "rid": winner["id"]},
        )

    report_indexes = {item["name"] for item in inspector.get_indexes("school_exam_reports")}
    with op.batch_alter_table("school_exam_reports") as batch:
        if "uq_school_exam_report_owner_canonical_key" not in report_indexes:
            batch.create_index(
                "uq_school_exam_report_owner_canonical_key",
                ["learner_id", "canonical_exam_key"],
                unique=True,
                sqlite_where=sa.text("canonical_exam_key IS NOT NULL"),
                postgresql_where=sa.text("canonical_exam_key IS NOT NULL"),
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    report_cols = {item["name"] for item in inspector.get_columns("school_exam_reports")}
    report_indexes = {item["name"] for item in inspector.get_indexes("school_exam_reports")}
    with op.batch_alter_table("school_exam_reports") as batch:
        if "uq_school_exam_report_owner_canonical_key" in report_indexes:
            batch.drop_index("uq_school_exam_report_owner_canonical_key")
        if "canonical_exam_key" in report_cols:
            batch.drop_column("canonical_exam_key")

    att_uqs = {item["name"] for item in inspector.get_unique_constraints("school_paper_attachments")}
    with op.batch_alter_table("school_paper_attachments") as batch:
        if "uq_school_paper_attachment_exam_sha" in att_uqs:
            batch.drop_constraint("uq_school_paper_attachment_exam_sha", type_="unique")
