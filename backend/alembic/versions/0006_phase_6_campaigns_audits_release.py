"""phase 6 campaigns, campaign assets, audits and release decisions

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24 20:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. campaigns
    op.create_table(
        'campaigns',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('external_reference', sa.String(length=100), nullable=True),
        sa.Column('owner', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='draft', nullable=False),
        sa.Column('release_notes', sa.Text(), nullable=True),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('released_by', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f('ck_campaigns_title_not_blank')),
        sa.CheckConstraint(
            "status IN ('draft', 'in_review', 'blocked', 'needs_review', 'ready_for_release', 'released', 'archived')",
            name=op.f('ck_campaigns_status')
        ),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], name=op.f('fk_campaigns_brand'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaigns')),
        sa.UniqueConstraint('id', 'brand_id', name='uq_campaigns_id_brand_id')
    )
    op.create_index('ix_campaigns_brand_created', 'campaigns', ['brand_id', 'created_at'], unique=False)
    op.create_index('ix_campaigns_brand_status', 'campaigns', ['brand_id', 'status'], unique=False)

    # 2. campaign_assets
    op.create_table(
        'campaign_assets',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('selected_submission_id', sa.UUID(), nullable=False),
        sa.Column('channel_role', sa.String(length=50), server_default='landing_page', nullable=False),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('added_by', sa.String(length=200), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "channel_role IN ('landing_page', 'advertisement', 'email', 'social_post', 'product_description', 'press_release', 'other')",
            name=op.f('ck_campaign_assets_channel_role')
        ),
        sa.ForeignKeyConstraint(
            ['campaign_id', 'brand_id'],
            ['campaigns.id', 'campaigns.brand_id'],
            name=op.f('fk_campaign_assets_campaign_same_brand'),
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['asset_id', 'brand_id'],
            ['content_assets.id', 'content_assets.brand_id'],
            name=op.f('fk_campaign_assets_asset_same_brand'),
            ondelete='RESTRICT'
        ),
        sa.ForeignKeyConstraint(
            ['selected_submission_id', 'asset_id'],
            ['content_submissions.id', 'content_submissions.asset_id'],
            name=op.f('fk_campaign_assets_submission_same_asset'),
            ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_assets')),
        sa.UniqueConstraint('campaign_id', 'asset_id', name='uq_campaign_assets_campaign_asset')
    )
    op.create_index('ix_campaign_assets_campaign_order', 'campaign_assets', ['campaign_id', 'display_order'], unique=False)
    op.create_index('ix_campaign_assets_asset', 'campaign_assets', ['asset_id'], unique=False)

    # 3. campaign_audits
    op.create_table(
        'campaign_audits',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('audit_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='completed', nullable=False),
        sa.Column('readiness_outcome', sa.String(length=30), nullable=False),
        sa.Column('is_stale', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stale_reason', sa.Text(), nullable=True),
        sa.Column('asset_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('blocker_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('warning_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('review_required_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('passed_checks_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('completed', 'failed')", name=op.f('ck_campaign_audits_status')),
        sa.CheckConstraint(
            "readiness_outcome IN ('blocked', 'needs_review', 'ready_for_release')",
            name=op.f('ck_campaign_audits_readiness_outcome')
        ),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name=op.f('fk_campaign_audits_campaign'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_audits')),
        sa.UniqueConstraint('campaign_id', 'audit_number', name='uq_campaign_audits_campaign_number')
    )
    op.create_index('ix_campaign_audits_campaign_created', 'campaign_audits', ['campaign_id', 'created_at'], unique=False)

    # 4. campaign_audit_findings
    op.create_table(
        'campaign_audit_findings',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('audit_id', sa.UUID(), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=True),
        sa.Column('submission_id', sa.UUID(), nullable=True),
        sa.Column('revision_number', sa.Integer(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('finding_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.String(length=20), nullable=False),
        sa.Column('claim_text', sa.String(length=500), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('recommended_action', sa.Text(), nullable=False),
        sa.Column('requires_human_review', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('related_asset_id', sa.UUID(), nullable=True),
        sa.Column('related_submission_id', sa.UUID(), nullable=True),
        sa.Column('related_fact_id', sa.UUID(), nullable=True),
        sa.Column('related_fact_version', sa.Integer(), nullable=True),
        sa.Column('related_rule_id', sa.UUID(), nullable=True),
        sa.Column('related_rule_version', sa.Integer(), nullable=True),
        sa.Column('related_impact_id', sa.UUID(), nullable=True),
        sa.Column('related_review_finding_id', sa.UUID(), nullable=True),
        sa.Column('source_document_id', sa.UUID(), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_excerpt', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "finding_type IN ('fact_contradiction', 'outdated_fact', 'open_impact', 'unreviewed_content', 'failed_review', 'incomplete_approval', 'guideline_violation', 'cross_asset_inconsistency', 'human_review_required', 'stale_review')",
            name=op.f('ck_campaign_audit_findings_type')
        ),
        sa.CheckConstraint("severity IN ('hard_blocker', 'warning', 'info')", name=op.f('ck_campaign_audit_findings_severity')),
        sa.CheckConstraint("confidence IN ('confirmed', 'potential', 'uncertain', 'not_evaluable')", name=op.f('ck_campaign_audit_findings_confidence')),
        sa.ForeignKeyConstraint(['audit_id'], ['campaign_audits.id'], name=op.f('fk_campaign_audit_findings_audit'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['content_assets.id'], name=op.f('fk_campaign_audit_findings_asset'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['submission_id'], ['content_submissions.id'], name=op.f('fk_campaign_audit_findings_submission'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_audit_findings'))
    )
    op.create_index('ix_campaign_audit_findings_audit_sev', 'campaign_audit_findings', ['audit_id', 'severity'], unique=False)
    op.create_index('ix_campaign_audit_findings_audit_type', 'campaign_audit_findings', ['audit_id', 'finding_type'], unique=False)

    # 5. campaign_release_decisions
    op.create_table(
        'campaign_release_decisions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('audit_id', sa.UUID(), nullable=False),
        sa.Column('decision', sa.String(length=20), server_default='released', nullable=False),
        sa.Column('actor_name', sa.String(length=200), nullable=False),
        sa.Column('actor_role', sa.String(length=50), nullable=False),
        sa.Column('release_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("decision IN ('released', 'revoked')", name=op.f('ck_campaign_release_decisions_decision')),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name=op.f('fk_campaign_release_decisions_campaign'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['audit_id'], ['campaign_audits.id'], name=op.f('fk_campaign_release_decisions_audit'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign_release_decisions'))
    )
    op.create_index('ix_campaign_release_decisions_campaign', 'campaign_release_decisions', ['campaign_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('campaign_release_decisions')
    op.drop_table('campaign_audit_findings')
    op.drop_table('campaign_audits')
    op.drop_table('campaign_assets')
    op.drop_table('campaigns')
