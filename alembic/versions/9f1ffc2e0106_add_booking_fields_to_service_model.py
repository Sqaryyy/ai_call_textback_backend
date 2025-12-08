"""add booking fields to service model

Revision ID: 9f1ffc2e0106
Revises: eb01c101cac6
Create Date: 2025-12-08 01:01:33.526696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision: str = '9f1ffc2e0106'
down_revision: Union[str, Sequence[str], None] = 'eb01c101cac6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the enum type first
    op.execute("CREATE TYPE bookingtype AS ENUM ('DIRECT', 'CONSULTATION_REQUIRED', 'LEAD_ONLY')")

    # Add booking-related columns to services table
    op.add_column('services',
                  sa.Column('booking_type', sa.Enum('DIRECT', 'CONSULTATION_REQUIRED', 'LEAD_ONLY', name='bookingtype'),
                            server_default='DIRECT', nullable=False))
    op.add_column('services', sa.Column('consultation_duration', sa.Integer(), nullable=True))
    op.add_column('services', sa.Column('consultation_price', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('services', sa.Column('required_fields', postgresql.JSON(astext_type=sa.Text()), server_default='[]',
                                        nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove booking-related columns from services table
    op.drop_column('services', 'required_fields')
    op.drop_column('services', 'consultation_price')
    op.drop_column('services', 'consultation_duration')
    op.drop_column('services', 'booking_type')

    # Drop the enum type
    op.execute("DROP TYPE bookingtype")