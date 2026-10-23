"""私有原件、来源审核记录与导入追溯。"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("source_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("exam_year", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("acquired_at", sa.Date(), nullable=False),
        sa.Column("rights_status", sa.String(32), nullable=False),
        sa.Column("rights_basis", sa.Text(), nullable=False),
        sa.Column("applicable", sa.Boolean(), nullable=False),
        sa.Column("applicability_note", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_source_reviews_source_document_id", "source_reviews", ["source_document_id"])
    op.create_table("source_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("owner_id", sa.String(40), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(32), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("parser_version", sa.String(256)),
        sa.Column("parsed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_by", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_source_attachments_source_document_id", "source_attachments", ["source_document_id"])
    op.create_table("imported_questions",
        sa.Column("question_version_id", sa.String(36), sa.ForeignKey("question_versions.id"), primary_key=True),
        sa.Column("attachment_id", sa.String(36), sa.ForeignKey("source_attachments.id"), nullable=False))
    op.create_index("ix_imported_questions_attachment_id", "imported_questions", ["attachment_id"])


def downgrade():
    # 仅用于隔离开发库；实际导入数据应采用保留数据的应用回退。
    op.drop_table("imported_questions")
    op.drop_table("source_attachments")
    op.drop_table("source_reviews")
