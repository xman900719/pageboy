"""学校私卷逐题得分与附件记录（仅证据用途，不进题库/练习流）。

- school_exam_items：每卷每题一条（uq_school_exam_item_label 唯一约束），
  manual_entry 录入即人工确认；OCR 草稿（ocr_draft）须人工确认才产生证据（AC-EVI-02）；
- school_paper_attachments：私人校卷附件元数据与私有目录存储键，不与
  source_documents/source_attachments 关联，不进内容台账与练习流；
- 学校考试总分永不折算考点分（INV-05）：SchoolExam 总分行不进证据装配；
- 回退仅用于隔离开发库（删两表）。
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("school_exam_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("school_exam_id", sa.String(36), sa.ForeignKey("school_exams.id"), nullable=False),
        sa.Column("question_label", sa.String(160), nullable=False),
        sa.Column("knowledge_id", sa.String(100), nullable=False),
        sa.Column("earned_points", sa.Float(), nullable=False),
        sa.Column("max_points", sa.Float(), nullable=False),
        sa.Column("scoring_origin", sa.String(32), nullable=False),
        sa.Column("confirmed_by_user", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("school_exam_id", "question_label", name="uq_school_exam_item_label"))
    op.create_index("ix_school_exam_items_school_exam_id", "school_exam_items", ["school_exam_id"])
    op.create_table("school_paper_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("school_exam_id", sa.String(36), sa.ForeignKey("school_exams.id"), nullable=False),
        sa.Column("owner_id", sa.String(40), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_school_paper_attachments_school_exam_id", "school_paper_attachments", ["school_exam_id"])


def downgrade():
    # 仅用于隔离开发库（删两表）；实际校卷数据回退须保留数据的应用级处理。
    op.drop_table("school_paper_attachments")
    op.drop_table("school_exam_items")
