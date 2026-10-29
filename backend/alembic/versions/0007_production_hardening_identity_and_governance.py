"""production hardening identity, memberships, and fact governance approval decisions

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-29 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('auth_provider', sa.String(length=50), server_default='local', nullable=False),
        sa.Column('provider_uid', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_index('ix_users_auth_provider_uid', 'users', ['auth_provider', 'provider_uid'], unique=False)

    # 2. brand_memberships
    op.create_table(
        'brand_memberships',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=50), server_default='creator', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('creator', 'reviewer', 'admin')", name=op.f('ck_brand_memberships_role')),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], name=op.f('fk_brand_memberships_brand'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_brand_memberships_user'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_brand_memberships')),
        sa.UniqueConstraint('user_id', 'brand_id', name=op.f('uq_brand_memberships_user_brand'))
    )
    op.create_index('ix_brand_memberships_brand_id', 'brand_id', ['brand_id'], unique=False)
    op.create_index('ix_brand_memberships_user_id', 'brand_id', ['user_id'], unique=False)

    # 3. membership_audit_logs
    op.create_table(
        'membership_audit_logs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('performed_by', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_membership_audit_logs'))
    )
    op.create_index('ix_membership_audit_logs_brand_id', 'membership_audit_logs', ['brand_id'], unique=False)
    op.create_index('ix_membership_audit_logs_user_id', 'membership_audit_logs', ['user_id'], unique=False)

    # 4. fact_approval_decisions
    op.create_table(
        'fact_approval_decisions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('fact_id', sa.UUID(), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('reviewer_name', sa.String(length=200), nullable=False),
        sa.Column('reviewer_email', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("decision IN ('approved', 'rejected')", name=op.f('ck_fact_approval_decision_type')),
        sa.ForeignKeyConstraint(['fact_id'], ['approved_facts.id'], name=op.f('fk_fact_approval_decisions_fact'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_fact_approval_decisions'))
    )
    op.create_index('ix_fact_approval_decisions_fact_id', 'fact_approval_decisions', ['fact_id'], unique=False)


def downgrade() -> None:
    op.drop_table('fact_approval_decisions')
    op.drop_table('membership_audit_logs')
    op.drop_table('brand_memberships')
    op.drop_table('users')
