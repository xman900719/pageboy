"""Foundation tables (baseline). Revision ID: 0001"""
from alembic import op
from shutong.database import Base
from shutong import models  # ensure all tables registered
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # First baseline only. Subsequent changes MUST use explicit Alembic migrations.
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
