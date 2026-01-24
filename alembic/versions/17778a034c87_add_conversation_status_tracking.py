"""add_conversation_status_tracking

Revision ID: 17778a034c87
Revises: 6fa2ff1f54bb
Create Date: 2025-12-21 14:00:17.313792

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '17778a034c87'
down_revision: Union[str, Sequence[str], None] = '6fa2ff1f54bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enum type
    conversation_status = postgresql.ENUM(
        'active', 'soft_close', 'hard_close', 'dropped',
        name='conversationstatus',
        create_type=True
    )
    conversation_status.create(op.get_bind(), checkfirst=True)

    # Add new columns
    op.add_column('conversation_metrics',
        sa.Column('conversation_status',
                  conversation_status,
                  nullable=False,
                  server_default='active'))

    op.add_column('conversation_metrics',
        sa.Column('soft_close_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('conversation_metrics',
        sa.Column('hard_close_at', sa.DateTime(timezone=True), nullable=True))

    # Add index
    op.create_index('ix_metrics_conversation_status',
                    'conversation_metrics',
                    ['business_id', 'conversation_status'],
                    unique=False)

    # ============================================
    # DATA MIGRATION: Migrate existing conversations
    # ============================================
    # Migrate completed conversations to hard_close
    op.execute("""
        UPDATE conversation_metrics 
        SET conversation_status = 'hard_close',
            hard_close_at = conversation_ended_at
        WHERE conversation_completed = true AND dropped_off = false
    """)

    # Migrate dropped conversations to dropped status
    op.execute("""
        UPDATE conversation_metrics 
        SET conversation_status = 'dropped',
            hard_close_at = conversation_ended_at
        WHERE dropped_off = true
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index
    op.drop_index('ix_metrics_conversation_status', table_name='conversation_metrics')

    # Drop columns
    op.drop_column('conversation_metrics', 'hard_close_at')
    op.drop_column('conversation_metrics', 'soft_close_at')
    op.drop_column('conversation_metrics', 'conversation_status')

    # Drop enum type
    op.execute('DROP TYPE IF EXISTS conversationstatus')