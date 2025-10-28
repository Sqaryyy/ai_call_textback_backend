"""add_missing_user_and_api_tables

Revision ID: 3e6122b18d51
Revises: 77ac24ed6689
Create Date: 2025-10-28 16:06:24.779001

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3e6122b18d51'
down_revision: Union[str, Sequence[str], None] = '77ac24ed6689'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums with proper handling
    conn = op.get_bind()

    # Check and create platformrole
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'platformrole'"))
    if not result.scalar():
        op.execute("CREATE TYPE platformrole AS ENUM ('admin', 'user')")

    # Check and create businessrole
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'businessrole'"))
    if not result.scalar():
        op.execute("CREATE TYPE businessrole AS ENUM ('owner', 'member')")

    # Check and create invitetype
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'invitetype'"))
    if not result.scalar():
        op.execute("CREATE TYPE invitetype AS ENUM ('business', 'platform')")

    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('role', sa.Enum('admin', 'user', name='platformrole'), nullable=False),
        sa.Column('active_business_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['active_business_id'], ['businesses.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # Create user_businesses association table
    op.create_table('user_businesses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.Enum('owner', 'member', name='businessrole'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create invites table
    op.create_table('invites',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('invite_type', sa.Enum('business', 'platform', name='invitetype'), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('used_count', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(invite_type = 'platform' AND business_id IS NULL) OR (invite_type = 'business' AND business_id IS NOT NULL)", name='check_business_invite_has_business_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invites_invite_type'), 'invites', ['invite_type'], unique=False)
    op.create_index(op.f('ix_invites_token'), 'invites', ['token'], unique=True)

    # Create email_verifications table
    op.create_table('email_verifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_verifications_token'), 'email_verifications', ['token'], unique=True)

    # Create password_resets table
    op.create_table('password_resets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_password_resets_token'), 'password_resets', ['token'], unique=True)

    # Create refresh_tokens table
    op.create_table('refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refresh_tokens_token'), 'refresh_tokens', ['token'], unique=True)

    # Create api_keys table
    op.create_table('api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_prefix', sa.String(length=12), nullable=False),
        sa.Column('key_hash', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('scopes', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=True),
        sa.Column('rate_limit', sa.Integer(), nullable=True),
        sa.Column('allowed_ips', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_api_keys_business_active', 'api_keys', ['business_id', 'is_active'], unique=False)
    op.create_index(op.f('ix_api_keys_key_hash'), 'api_keys', ['key_hash'], unique=True)

    # Create api_request_logs table
    op.create_table('api_request_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('api_key_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=500), nullable=False),
        sa.Column('query_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_api_logs_business_created', 'api_request_logs', ['business_id', 'created_at'], unique=False)
    op.create_index('ix_api_logs_key_created', 'api_request_logs', ['api_key_id', 'created_at'], unique=False)

    # Create webhook_endpoints table
    op.create_table('webhook_endpoints',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('enabled_events', sa.JSON(), nullable=True),
        sa.Column('secret', sa.String(length=128), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failure_reason', sa.String(length=500), nullable=True),
        sa.Column('max_consecutive_failures', sa.Integer(), nullable=True),
        sa.Column('auto_disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_webhook_endpoints_business_active', 'webhook_endpoints', ['business_id', 'is_active'], unique=False)

    # Create webhook_events table
    op.create_table('webhook_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('webhook_endpoint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('event_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=True),
        sa.Column('max_attempts', sa.Integer(), nullable=True),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
        sa.ForeignKeyConstraint(['webhook_endpoint_id'], ['webhook_endpoints.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_webhook_events_business_created', 'webhook_events', ['business_id', 'created_at'], unique=False)
    op.create_index('ix_webhook_events_endpoint_status', 'webhook_events', ['webhook_endpoint_id', 'status'], unique=False)
    op.create_index('ix_webhook_events_status', 'webhook_events', ['status', 'next_retry_at'], unique=False)


def downgrade() -> None:
    op.drop_table('webhook_events')
    op.drop_table('webhook_endpoints')
    op.drop_table('api_request_logs')
    op.drop_table('api_keys')
    op.drop_table('refresh_tokens')
    op.drop_table('password_resets')
    op.drop_table('email_verifications')
    op.drop_table('invites')
    op.drop_table('user_businesses')
    op.drop_table('users')
    op.execute('DROP TYPE businessrole')
    op.execute('DROP TYPE platformrole')
    op.execute('DROP TYPE invitetype')