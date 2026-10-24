"""phase 4 revisions and approval workflow

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23 18:23:30.598425
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


TRIGGERS_SQL = """
CREATE FUNCTION brandpr_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP USING ERRCODE = 'integrity_constraint_violation';
END $$;

CREATE TRIGGER trg_workflow_events_append_only BEFORE UPDATE OR DELETE ON workflow_events FOR EACH ROW EXECUTE FUNCTION brandpr_append_only();
CREATE TRIGGER trg_risk_overrides_append_only BEFORE UPDATE OR DELETE ON risk_overrides FOR EACH ROW EXECUTE FUNCTION brandpr_append_only();
CREATE TRIGGER trg_revision_corrections_append_only BEFORE UPDATE OR DELETE ON revision_corrections FOR EACH ROW EXECUTE FUNCTION brandpr_append_only();
CREATE TRIGGER trg_impact_resolutions_append_only BEFORE UPDATE OR DELETE ON fact_change_impact_resolutions FOR EACH ROW EXECUTE FUNCTION brandpr_append_only();

-- A revision is immutable. Only its workflow status may change, and only along the permitted transitions.
CREATE FUNCTION brandpr_guard_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.brand_id IS DISTINCT FROM OLD.brand_id OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
       OR NEW.revision_number IS DISTINCT FROM OLD.revision_number OR NEW.parent_submission_id IS DISTINCT FROM OLD.parent_submission_id
       OR NEW.title IS DISTINCT FROM OLD.title OR NEW.content IS DISTINCT FROM OLD.content OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.submitted_by IS DISTINCT FROM OLD.submitted_by OR NEW.change_note IS DISTINCT FROM OLD.change_note
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'content revisions are immutable; create a new revision instead' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.workflow_status IS DISTINCT FROM OLD.workflow_status AND NOT (
        (OLD.workflow_status = 'draft' AND NEW.workflow_status = 'in_review')
        OR (OLD.workflow_status = 'in_review' AND NEW.workflow_status IN ('approved', 'changes_requested', 'rejected'))
    ) THEN
        RAISE EXCEPTION 'workflow transition % -> % is not permitted', OLD.workflow_status, NEW.workflow_status USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_content_submissions_guard BEFORE UPDATE ON content_submissions FOR EACH ROW EXECUTE FUNCTION brandpr_guard_revision();

-- A Phase 3 impact keeps its triggering information forever. Its status may change only to the value recorded in a resolution row.
CREATE FUNCTION brandpr_guard_impact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.brand_id IS DISTINCT FROM OLD.brand_id OR NEW.fact_id IS DISTINCT FROM OLD.fact_id
       OR NEW.content_submission_id IS DISTINCT FROM OLD.content_submission_id OR NEW.fact_revision_id IS DISTINCT FROM OLD.fact_revision_id
       OR NEW.trigger_type IS DISTINCT FROM OLD.trigger_type OR NEW.trigger_key IS DISTINCT FROM OLD.trigger_key
       OR NEW.change_type IS DISTINCT FROM OLD.change_type OR NEW.previous_fact_version IS DISTINCT FROM OLD.previous_fact_version
       OR NEW.current_fact_version IS DISTINCT FROM OLD.current_fact_version OR NEW.source_review_run_id IS DISTINCT FROM OLD.source_review_run_id
       OR NEW.change_summary IS DISTINCT FROM OLD.change_summary OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'a fact-change impact keeps its original triggering record; only its status may change' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        OLD.status = 'needs_review' AND NEW.status IN ('resolved', 'dismissed')
        AND EXISTS (SELECT 1 FROM fact_change_impact_resolutions r WHERE r.impact_id = NEW.id AND r.to_status = NEW.status)
    ) THEN
        RAISE EXCEPTION 'impact status change % -> % requires a recorded resolution decision', OLD.status, NEW.status USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_fact_change_impacts_guard BEFORE UPDATE ON fact_change_impacts FOR EACH ROW EXECUTE FUNCTION brandpr_guard_impact();
"""

DROP_TRIGGERS_SQL = """
DROP TRIGGER IF EXISTS trg_fact_change_impacts_guard ON fact_change_impacts;
DROP TRIGGER IF EXISTS trg_content_submissions_guard ON content_submissions;
DROP FUNCTION IF EXISTS brandpr_guard_impact();
DROP FUNCTION IF EXISTS brandpr_guard_revision();
DROP TRIGGER IF EXISTS trg_impact_resolutions_append_only ON fact_change_impact_resolutions;
DROP TRIGGER IF EXISTS trg_revision_corrections_append_only ON revision_corrections;
DROP TRIGGER IF EXISTS trg_risk_overrides_append_only ON risk_overrides;
DROP TRIGGER IF EXISTS trg_workflow_events_append_only ON workflow_events;
DROP FUNCTION IF EXISTS brandpr_append_only();
"""


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('content_assets',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(btrim(title)) > 0', name=op.f('ck_content_assets_title_not_blank')),
    sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], name=op.f('fk_content_assets_brand_id_brands'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_assets')),
    sa.UniqueConstraint('id', 'brand_id', name='uq_content_assets_id_brand_id')
    )
    op.create_index('ix_content_assets_brand_created', 'content_assets', ['brand_id', 'created_at'], unique=False)
    op.add_column('content_submissions', sa.Column('asset_id', sa.UUID(), nullable=True))
    op.add_column('content_submissions', sa.Column('revision_number', sa.Integer(), server_default='1', nullable=False))
    op.add_column('content_submissions', sa.Column('parent_submission_id', sa.UUID(), nullable=True))
    op.add_column('content_submissions', sa.Column('workflow_status', sa.String(length=20), server_default='draft', nullable=False))
    op.add_column('content_submissions', sa.Column('change_note', sa.Text(), nullable=True))
    # --- Backfill: every legacy submission becomes revision 1 of its own new logical asset. Nothing is moved or rewritten.
    op.execute("UPDATE content_submissions SET asset_id = gen_random_uuid()")
    op.execute(
        "INSERT INTO content_assets (id, brand_id, title, created_by, created_at, updated_at) "
        "SELECT asset_id, brand_id, title, submitted_by, created_at, created_at FROM content_submissions"
    )
    op.alter_column('content_submissions', 'asset_id', nullable=False)
    op.create_index('ix_content_submissions_asset', 'content_submissions', ['asset_id'], unique=False)
    op.create_unique_constraint('uq_content_submissions_asset_revision', 'content_submissions', ['asset_id', 'revision_number'])
    op.create_unique_constraint('uq_content_submissions_id_asset_id', 'content_submissions', ['id', 'asset_id'])
    op.create_unique_constraint('uq_content_submissions_parent', 'content_submissions', ['parent_submission_id'])
    op.create_foreign_key('fk_content_submissions_parent_same_asset', 'content_submissions', 'content_submissions', ['parent_submission_id', 'asset_id'], ['id', 'asset_id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_content_submissions_asset_same_brand', 'content_submissions', 'content_assets', ['asset_id', 'brand_id'], ['id', 'brand_id'], ondelete='RESTRICT')
    op.create_check_constraint(op.f('ck_content_submissions_revision_positive'), 'content_submissions', 'revision_number >= 1')
    op.create_check_constraint(op.f('ck_content_submissions_parent_matches_revision'), 'content_submissions', '(parent_submission_id IS NULL) = (revision_number = 1)')
    op.create_check_constraint(op.f('ck_content_submissions_workflow_status'), 'content_submissions', "workflow_status IN ('draft','in_review','changes_requested','approved','rejected')")
    op.create_check_constraint(
        op.f('ck_content_submissions_content_hash_matches'), 'content_submissions', "content_hash = encode(sha256(convert_to(content, 'UTF8')), 'hex')"
    )
    # --- Phase 3 impacts may now be closed (resolved / dismissed), but only together with a resolution row (see trigger below).
    op.drop_constraint(op.f('ck_fact_change_impacts_status'), 'fact_change_impacts', type_='check')
    op.create_check_constraint(op.f('ck_fact_change_impacts_status'), 'fact_change_impacts', "status IN ('needs_review','resolved','dismissed')")
    op.create_unique_constraint('uq_review_findings_id_review_run_id', 'review_findings', ['id', 'review_run_id'])
    op.create_table('workflow_events',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('asset_id', sa.UUID(), nullable=False),
    sa.Column('submission_id', sa.UUID(), nullable=False),
    sa.Column('review_run_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=True),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('actor', sa.String(length=200), nullable=False),
    sa.Column('actor_role', sa.String(length=20), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("action IN ('created','submitted','approved','changes_requested','rejected')", name=op.f('ck_workflow_events_action')),
    sa.CheckConstraint("action NOT IN ('approved','changes_requested','rejected') OR actor_role = 'reviewer'", name=op.f('ck_workflow_events_decisions_by_reviewers')),
    sa.CheckConstraint("action NOT IN ('changes_requested','rejected') OR length(btrim(coalesce(rationale, ''))) > 0", name=op.f('ck_workflow_events_reason_required')),
    sa.CheckConstraint("actor_role IN ('creator','reviewer')", name=op.f('ck_workflow_events_actor_role')),
    sa.CheckConstraint('length(btrim(actor)) > 0', name=op.f('ck_workflow_events_actor_not_blank')),
    sa.ForeignKeyConstraint(['review_run_id', 'brand_id'], ['review_runs.id', 'review_runs.brand_id'], name='fk_workflow_events_run_same_brand', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['submission_id', 'asset_id'], ['content_submissions.id', 'content_submissions.asset_id'], name='fk_workflow_events_submission_same_asset', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['submission_id', 'brand_id'], ['content_submissions.id', 'content_submissions.brand_id'], name='fk_workflow_events_submission_same_brand', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workflow_events')),
    sa.UniqueConstraint('id', 'brand_id', name='uq_workflow_events_id_brand_id'),
    sa.UniqueConstraint('id', 'submission_id', name='uq_workflow_events_id_submission_id'),
    sa.UniqueConstraint('submission_id', 'action', name='uq_workflow_events_submission_action')
    )
    op.create_index('ix_workflow_events_asset_created', 'workflow_events', ['asset_id', 'created_at'], unique=False)
    op.create_index('uq_workflow_events_one_final_decision', 'workflow_events', ['submission_id'], unique=True, postgresql_where=sa.text("action IN ('approved','changes_requested','rejected')"))
    op.create_table('fact_change_impact_resolutions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('impact_id', sa.UUID(), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=False),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('actor', sa.String(length=200), nullable=False),
    sa.Column('actor_role', sa.String(length=20), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('resolving_submission_id', sa.UUID(), nullable=True),
    sa.Column('resolving_review_run_id', sa.UUID(), nullable=True),
    sa.Column('decision_event_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(action = 'resolved') = (resolving_submission_id IS NOT NULL AND resolving_review_run_id IS NOT NULL AND decision_event_id IS NOT NULL)", name=op.f('ck_fact_change_impact_resolutions_resolved_has_evidence')),
    sa.CheckConstraint("action = to_status AND from_status = 'needs_review'", name=op.f('ck_fact_change_impact_resolutions_transition_consistent')),
    sa.CheckConstraint("action IN ('resolved','dismissed')", name=op.f('ck_fact_change_impact_resolutions_action')),
    sa.CheckConstraint("actor_role = 'reviewer'", name=op.f('ck_fact_change_impact_resolutions_reviewer_only')),
    sa.CheckConstraint('length(btrim(rationale)) > 0', name=op.f('ck_fact_change_impact_resolutions_rationale_not_blank')),
    sa.ForeignKeyConstraint(['decision_event_id', 'resolving_submission_id'], ['workflow_events.id', 'workflow_events.submission_id'], name='fk_impact_resolutions_event_for_submission', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['impact_id', 'brand_id'], ['fact_change_impacts.id', 'fact_change_impacts.brand_id'], name='fk_impact_resolutions_impact_same_brand', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['resolving_review_run_id', 'brand_id'], ['review_runs.id', 'review_runs.brand_id'], name='fk_impact_resolutions_run_same_brand', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['resolving_submission_id', 'brand_id'], ['content_submissions.id', 'content_submissions.brand_id'], name='fk_impact_resolutions_submission_same_brand', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fact_change_impact_resolutions')),
    sa.UniqueConstraint('impact_id', name='uq_impact_resolutions_impact')
    )
    op.create_table('revision_corrections',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('submission_id', sa.UUID(), nullable=False),
    sa.Column('finding_id', sa.UUID(), nullable=False),
    sa.Column('decision', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('original_text', sa.Text(), nullable=False),
    sa.Column('replacement_text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("decision IN ('accepted','rejected','modified','manual')", name=op.f('ck_revision_corrections_decision')),
    sa.CheckConstraint("source <> 'ai' OR decision <> 'manual'", name=op.f('ck_revision_corrections_ai_not_manual')),
    sa.CheckConstraint("source IN ('ai','manual')", name=op.f('ck_revision_corrections_source')),
    sa.ForeignKeyConstraint(['finding_id', 'brand_id'], ['review_findings.id', 'review_findings.brand_id'], name='fk_revision_corrections_finding_same_brand', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['submission_id', 'brand_id'], ['content_submissions.id', 'content_submissions.brand_id'], name='fk_revision_corrections_submission_same_brand', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_revision_corrections')),
    sa.UniqueConstraint('submission_id', 'finding_id', name='uq_revision_corrections_submission_finding')
    )
    op.create_table('risk_overrides',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('review_run_id', sa.UUID(), nullable=False),
    sa.Column('finding_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('actor', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(btrim(reason)) > 0', name=op.f('ck_risk_overrides_reason_not_blank')),
    sa.ForeignKeyConstraint(['event_id', 'brand_id'], ['workflow_events.id', 'workflow_events.brand_id'], name='fk_risk_overrides_event_same_brand', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['finding_id', 'review_run_id'], ['review_findings.id', 'review_findings.review_run_id'], name='fk_risk_overrides_finding_in_run', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['review_run_id', 'brand_id'], ['review_runs.id', 'review_runs.brand_id'], name='fk_risk_overrides_run_same_brand', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_overrides')),
    sa.UniqueConstraint('event_id', 'finding_id', name='uq_risk_overrides_event_finding')
    )
    op.execute(TRIGGERS_SQL)
    # ### end Alembic commands ###


def downgrade() -> None:
    # Lossy by nature: revisions become independent legacy-style submissions, and closed impacts return to needs_review
    # (their resolution history is dropped with the Phase 4 tables).
    op.execute(DROP_TRIGGERS_SQL)
    op.execute("UPDATE fact_change_impacts SET status = 'needs_review' WHERE status <> 'needs_review'")
    op.drop_constraint(op.f('ck_fact_change_impacts_status'), 'fact_change_impacts', type_='check')
    op.create_check_constraint(op.f('ck_fact_change_impacts_status'), 'fact_change_impacts', "status IN ('needs_review')")
    op.drop_table('risk_overrides')
    op.drop_table('revision_corrections')
    op.drop_table('fact_change_impact_resolutions')
    op.drop_index('uq_workflow_events_one_final_decision', table_name='workflow_events', postgresql_where=sa.text("action IN ('approved','changes_requested','rejected')"))
    op.drop_index('ix_workflow_events_asset_created', table_name='workflow_events')
    op.drop_table('workflow_events')
    op.drop_constraint('uq_review_findings_id_review_run_id', 'review_findings', type_='unique')
    for name in ('content_hash_matches', 'workflow_status', 'parent_matches_revision', 'revision_positive'):
        op.drop_constraint(op.f(f'ck_content_submissions_{name}'), 'content_submissions', type_='check')
    op.drop_constraint('fk_content_submissions_asset_same_brand', 'content_submissions', type_='foreignkey')
    op.drop_constraint('fk_content_submissions_parent_same_asset', 'content_submissions', type_='foreignkey')
    op.drop_constraint('uq_content_submissions_parent', 'content_submissions', type_='unique')
    op.drop_constraint('uq_content_submissions_id_asset_id', 'content_submissions', type_='unique')
    op.drop_constraint('uq_content_submissions_asset_revision', 'content_submissions', type_='unique')
    op.drop_index('ix_content_submissions_asset', table_name='content_submissions')
    for column in ('change_note', 'workflow_status', 'parent_submission_id', 'revision_number', 'asset_id'):
        op.drop_column('content_submissions', column)
    op.drop_index('ix_content_assets_brand_created', table_name='content_assets')
    op.drop_table('content_assets')
