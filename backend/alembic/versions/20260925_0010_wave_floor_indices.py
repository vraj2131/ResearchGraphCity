"""Allow original decompositions with more than 32767 waves."""
from alembic import op
import sqlalchemy as sa

revision = '20260925_0010'
down_revision = '20260924_0009'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('floors', 'floor_index', existing_type=sa.SmallInteger(), type_=sa.Integer(), existing_nullable=False)


def downgrade():
    # PostgreSQL rejects out-of-range existing values, rather than truncating
    # wave identities or deleting data during downgrade.
    op.alter_column('floors', 'floor_index', existing_type=sa.Integer(), type_=sa.SmallInteger(), existing_nullable=False)
