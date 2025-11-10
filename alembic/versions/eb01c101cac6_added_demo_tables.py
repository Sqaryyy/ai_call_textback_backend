"""added demo tables

Revision ID: eb01c101cac6
Revises: eb7b90a6ba41
Create Date: 2025-11-10 00:51:08.123876

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eb01c101cac6'
down_revision: Union[str, Sequence[str], None] = 'eb7b90a6ba41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Create demo_conversations table
    op.create_table(
        'demo_conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', sa.String(50), nullable=False, unique=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id'), nullable=True),
        sa.Column('customer_phone', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False)
    )

    # Indexes for demo_conversations
    op.create_index('idx_demo_conversations_session', 'demo_conversations', ['session_id'])
    op.create_index('idx_demo_conversations_created', 'demo_conversations', ['created_at'])

    # 2. Create demo_messages table
    op.create_table(
        'demo_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('demo_conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('demo_conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)
    )

    # Indexes for demo_messages
    op.create_index('idx_demo_messages_conversation', 'demo_messages', ['demo_conversation_id'])
    op.create_index('idx_demo_messages_created', 'demo_messages', ['created_at'])

    # 3. Create demo_ai_context_log table
    op.create_table(
        'demo_ai_context_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('demo_conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('demo_conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('demo_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('demo_messages.id', ondelete='CASCADE'), nullable=True),
        sa.Column('business_context', postgresql.JSONB, nullable=False),
        sa.Column('conversation_context', postgresql.JSONB, nullable=False),
        sa.Column('rag_context', sa.Text, nullable=True),
        sa.Column('messages_sent_to_ai', postgresql.JSONB, nullable=False),
        sa.Column('function_calls', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('ai_response', sa.Text, nullable=True),
        sa.Column('finish_reason', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)
    )

    # Indexes for demo_ai_context_log
    op.create_index('idx_demo_ai_log_conversation', 'demo_ai_context_log', ['demo_conversation_id'])
    op.create_index('idx_demo_ai_log_message', 'demo_ai_context_log', ['demo_message_id'])
    op.create_index('idx_demo_ai_log_created', 'demo_ai_context_log', ['created_at'])

    # 4. Create cleanup function for old demo data
    op.execute("""
        CREATE OR REPLACE FUNCTION delete_old_demo_data()
        RETURNS void AS $$
        BEGIN
            DELETE FROM demo_conversations 
            WHERE created_at < NOW() - INTERVAL '90 days';
            -- CASCADE will automatically delete related messages and logs
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""

    # Drop cleanup function
    op.execute("DROP FUNCTION IF EXISTS delete_old_demo_data();")

    # Drop tables in reverse order (due to foreign keys)
    op.drop_index('idx_demo_ai_log_created', 'demo_ai_context_log')
    op.drop_index('idx_demo_ai_log_message', 'demo_ai_context_log')
    op.drop_index('idx_demo_ai_log_conversation', 'demo_ai_context_log')
    op.drop_table('demo_ai_context_log')

    op.drop_index('idx_demo_messages_created', 'demo_messages')
    op.drop_index('idx_demo_messages_conversation', 'demo_messages')
    op.drop_table('demo_messages')

    op.drop_index('idx_demo_conversations_created', 'demo_conversations')
    op.drop_index('idx_demo_conversations_session', 'demo_conversations')
    op.drop_table('demo_conversations')