"""phase 5 guideline lint, policy sandbox and governance intelligence

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24 19:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. guideline_rules
    op.create_table(
        'guideline_rules',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('rule_text', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=50), server_default='general', nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='medium', nullable=False),
        sa.Column('scope', sa.String(length=50), server_default='all', nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('examples', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='proposed', nullable=False),
        sa.Column('source_document_id', sa.UUID(), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_excerpt', sa.Text(), nullable=True),
        sa.Column('owner', sa.String(length=200), nullable=True),
        sa.Column('created_by', sa.String(length=200), nullable=False),
        sa.Column('current_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('proposed', 'active', 'retired')", name=op.f('ck_guideline_rules_status')),
        sa.CheckConstraint("severity IN ('low', 'medium', 'high')", name=op.f('ck_guideline_rules_severity')),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f('ck_guideline_rules_title_not_blank')),
        sa.CheckConstraint("length(btrim(rule_text)) > 0", name=op.f('ck_guideline_rules_text_not_blank')),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], name=op.f('fk_guideline_rules_brand'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['source_document_id', 'brand_id'],
            ['source_documents.id', 'source_documents.brand_id'],
            name=op.f('fk_guideline_rules_source_doc_same_brand'),
            ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_guideline_rules')),
        sa.UniqueConstraint('id', 'brand_id', name='uq_guideline_rules_id_brand_id')
    )
    op.create_index('ix_guideline_rules_brand_id', 'guideline_rules', ['brand_id'], unique=False)
    op.create_index('ix_guideline_rules_brand_status', 'guideline_rules', ['brand_id', 'status'], unique=False)
    op.create_index('ix_guideline_rules_category', 'guideline_rules', ['brand_id', 'category'], unique=False)

    # 2. guideline_rule_versions
    op.create_table(
        'guideline_rule_versions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('rule_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('rule_text', sa.Text(), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('examples', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('source_reference', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('change_reason', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['rule_id'], ['guideline_rules.id'], name=op.f('fk_guideline_rule_versions_rule'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_guideline_rule_versions')),
        sa.UniqueConstraint('rule_id', 'version_number', name='uq_guideline_rule_versions_rule_ver')
    )
    op.create_index('ix_guideline_rule_versions_rule_id', 'guideline_rule_versions', ['rule_id'], unique=False)

    # 3. guideline_lint_results
    op.create_table(
        'guideline_lint_results',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('rule_id', sa.UUID(), nullable=False),
        sa.Column('rule_version', sa.Integer(), nullable=False),
        sa.Column('issue_category', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='medium', nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('related_rule_id', sa.UUID(), nullable=True),
        sa.Column('suggested_action', sa.Text(), nullable=False),
        sa.Column('requires_human_review', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("severity IN ('low', 'medium', 'high')", name=op.f('ck_guideline_lint_results_severity')),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], name=op.f('fk_guideline_lint_results_brand'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rule_id'], ['guideline_rules.id'], name=op.f('fk_guideline_lint_results_rule'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['related_rule_id'], ['guideline_rules.id'], name=op.f('fk_guideline_lint_results_rel_rule'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_guideline_lint_results'))
    )
    op.create_index('ix_guideline_lint_results_brand_id', 'guideline_lint_results', ['brand_id'], unique=False)
    op.create_index('ix_guideline_lint_results_rule_id', 'guideline_lint_results', ['rule_id'], unique=False)

    # 4. policy_simulations
    op.create_table(
        'policy_simulations',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('rule_id', sa.UUID(), nullable=False),
        sa.Column('base_rule_version', sa.Integer(), nullable=False),
        sa.Column('proposed_rule_version', sa.Integer(), nullable=True),
        sa.Column('proposed_rule_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='completed', nullable=False),
        sa.Column('created_by', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.CheckConstraint("status IN ('completed', 'failed')", name=op.f('ck_policy_simulations_status')),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], name=op.f('fk_policy_simulations_brand'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rule_id'], ['guideline_rules.id'], name=op.f('fk_policy_simulations_rule'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_policy_simulations'))
    )
    op.create_index('ix_policy_simulations_brand_id', 'policy_simulations', ['brand_id'], unique=False)
    op.create_index('ix_policy_simulations_rule_id', 'policy_simulations', ['rule_id'], unique=False)

    # 5. policy_simulation_results
    op.create_table(
        'policy_simulation_results',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('simulation_id', sa.UUID(), nullable=False),
        sa.Column('content_submission_id', sa.UUID(), nullable=False),
        sa.Column('historical_review_run_id', sa.UUID(), nullable=True),
        sa.Column('baseline_outcome', sa.String(length=20), nullable=False),
        sa.Column('simulated_outcome', sa.String(length=20), nullable=False),
        sa.Column('changed_findings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('evaluation_status', sa.String(length=20), server_default='evaluated', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("baseline_outcome IN ('pass', 'flagged', 'not_evaluable')", name=op.f('ck_sim_res_baseline_outcome')),
        sa.CheckConstraint("simulated_outcome IN ('pass', 'flagged', 'not_evaluable')", name=op.f('ck_sim_res_simulated_outcome')),
        sa.CheckConstraint("evaluation_status IN ('evaluated', 'not_evaluable')", name=op.f('ck_sim_res_eval_status')),
        sa.ForeignKeyConstraint(['simulation_id'], ['policy_simulations.id'], name=op.f('fk_sim_res_simulation'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['content_submission_id'], ['content_submissions.id'], name=op.f('fk_sim_res_submission'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['historical_review_run_id'], ['review_runs.id'], name=op.f('fk_sim_res_run'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_policy_simulation_results'))
    )
    op.create_index('ix_policy_sim_results_sim_id', 'policy_simulation_results', ['simulation_id'], unique=False)
    op.create_index('ix_policy_sim_results_submission_id', 'policy_simulation_results', ['content_submission_id'], unique=False)


def downgrade() -> None:
    op.drop_table('policy_simulation_results')
    op.drop_table('policy_simulations')
    op.drop_table('guideline_lint_results')
    op.drop_table('guideline_rule_versions')
    op.drop_table('guideline_rules')
