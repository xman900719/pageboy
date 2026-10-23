"""Foundation tables (baseline). Revision ID: 0001"""
from alembic import op
from shutong.database import Base
from shutong import models  # ensure all tables registered
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
FOUNDATION_TABLES = ("source_documents", "questions", "question_versions", "exposures", "answer_attempts", "school_exams", "goals")

def upgrade():
    # First baseline only. Subsequent changes MUST use explicit Alembic migrations.
    # 限定原始七张表，避免新模型被提前建表而与后续显式迁移冲突。
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in FOUNDATION_TABLES])

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in FOUNDATION_TABLES])
