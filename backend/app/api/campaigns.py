"""Phase 6 FastAPI routes for campaigns, campaign assets, audits, comparisons, and release readiness."""
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import CurrentActor, DbSession, OptionalActor, ReviewerActor, verify_brand_access
from app.models.campaign import CampaignAudit
from app.schemas.campaign import (
    AuditComparisonOut, CampaignAssetAdd, CampaignAssetOut, CampaignAuditOut,
    CampaignCreate, CampaignOut, CampaignReleaseOut, CampaignReleaseRequest,
    CampaignUpdate, ReleaseEvaluationOut,
)
from app.services import campaign_audit as audit_svc
from app.services import campaigns as camp_svc

router = APIRouter(tags=["campaigns"])


@router.post(
    "/brands/{brand_id}/campaigns",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new marketing campaign",
)
def create_campaign(brand_id: uuid.UUID, data: CampaignCreate, db: DbSession, actor: OptionalActor = None):
    verify_brand_access(brand_id, actor)
    actor_name = actor.name if actor else None
    camp = camp_svc.create_campaign(db, brand_id, data, actor_name=actor_name)
    return CampaignOut.model_validate(camp)


@router.get(
    "/brands/{brand_id}/campaigns",
    response_model=list[CampaignOut],
    summary="List all campaigns for a brand",
)
def list_campaigns(brand_id: uuid.UUID, db: DbSession, status: Optional[str] = Query(None), actor: OptionalActor = None):
    verify_brand_access(brand_id, actor)
    campaigns = camp_svc.list_campaigns(db, brand_id, status=status)
    results = []
    for c in campaigns:
        assets = camp_svc.list_campaign_assets(db, c.id)
        latest_audit = audit_svc.list_campaign_audits(db, c.id)
        top_audit = latest_audit[0] if latest_audit else None

        results.append(CampaignOut(
            id=c.id,
            brand_id=c.brand_id,
            title=c.title,
            description=c.description,
            external_reference=c.external_reference,
            owner=c.owner,
            status=c.status,
            release_notes=c.release_notes,
            released_at=c.released_at,
            released_by=c.released_by,
            created_at=c.created_at,
            updated_at=c.updated_at,
            asset_count=len(assets),
            latest_audit_id=top_audit.id if top_audit else None,
            latest_readiness=top_audit.readiness_outcome if top_audit else None,
            latest_audit_stale=top_audit.is_stale if top_audit else False,
            blocker_count=top_audit.blocker_count if top_audit else 0,
            warning_count=top_audit.warning_count if top_audit else 0,
            assets=[CampaignAssetOut.model_validate(a) for a in assets],
        ))
    return results


@router.get(
    "/campaigns/{campaign_id}",
    response_model=CampaignOut,
    summary="Get campaign detail and selected assets",
)
def get_campaign(campaign_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    c = camp_svc.get_campaign(db, campaign_id)
    if not c:
        raise camp_svc.CampaignError("campaign_not_found", "Campaign not found", 404)
    verify_brand_access(c.brand_id, actor)

    assets = camp_svc.list_campaign_assets(db, c.id)
    latest_audits = audit_svc.list_campaign_audits(db, c.id)
    top_audit = latest_audits[0] if latest_audits else None

    return CampaignOut(
        id=c.id,
        brand_id=c.brand_id,
        title=c.title,
        description=c.description,
        external_reference=c.external_reference,
        owner=c.owner,
        status=c.status,
        release_notes=c.release_notes,
        released_at=c.released_at,
        released_by=c.released_by,
        created_at=c.created_at,
        updated_at=c.updated_at,
        asset_count=len(assets),
        latest_audit_id=top_audit.id if top_audit else None,
        latest_readiness=top_audit.readiness_outcome if top_audit else None,
        latest_audit_stale=top_audit.is_stale if top_audit else False,
        blocker_count=top_audit.blocker_count if top_audit else 0,
        warning_count=top_audit.warning_count if top_audit else 0,
        assets=[CampaignAssetOut.model_validate(a) for a in assets],
    )


@router.patch(
    "/campaigns/{campaign_id}",
    response_model=CampaignOut,
    summary="Update campaign metadata",
)
def update_campaign(campaign_id: uuid.UUID, data: CampaignUpdate, db: DbSession, actor: OptionalActor):
    actor_name = actor.name if actor else None
    c = camp_svc.update_campaign(db, campaign_id, data, actor_name=actor_name)
    assets = camp_svc.list_campaign_assets(db, c.id)
    latest_audits = audit_svc.list_campaign_audits(db, c.id)
    top_audit = latest_audits[0] if latest_audits else None

    return CampaignOut(
        id=c.id,
        brand_id=c.brand_id,
        title=c.title,
        description=c.description,
        external_reference=c.external_reference,
        owner=c.owner,
        status=c.status,
        release_notes=c.release_notes,
        released_at=c.released_at,
        released_by=c.released_by,
        created_at=c.created_at,
        updated_at=c.updated_at,
        asset_count=len(assets),
        latest_audit_id=top_audit.id if top_audit else None,
        latest_readiness=top_audit.readiness_outcome if top_audit else None,
        latest_audit_stale=top_audit.is_stale if top_audit else False,
        blocker_count=top_audit.blocker_count if top_audit else 0,
        warning_count=top_audit.warning_count if top_audit else 0,
        assets=[CampaignAssetOut.model_validate(a) for a in assets],
    )


@router.post(
    "/campaigns/{campaign_id}/assets",
    response_model=CampaignAssetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an asset to the campaign",
)
def add_campaign_asset(campaign_id: uuid.UUID, data: CampaignAssetAdd, db: DbSession, actor: OptionalActor):
    actor_name = actor.name if actor else None
    item = camp_svc.add_campaign_asset(db, campaign_id, data, actor_name=actor_name)
    # Fetch full view
    all_assets = camp_svc.list_campaign_assets(db, campaign_id)
    for a in all_assets:
        if a["id"] == item.id:
            return CampaignAssetOut.model_validate(a)
    return CampaignAssetOut.model_validate(item)


@router.get(
    "/campaigns/{campaign_id}/assets",
    response_model=list[CampaignAssetOut],
    summary="List all assets in a campaign",
)
def list_campaign_assets(campaign_id: uuid.UUID, db: DbSession):
    assets = camp_svc.list_campaign_assets(db, campaign_id)
    return [CampaignAssetOut.model_validate(a) for a in assets]


@router.delete(
    "/campaigns/{campaign_id}/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an asset from a campaign",
)
def remove_campaign_asset(campaign_id: uuid.UUID, asset_id: uuid.UUID, db: DbSession, actor: OptionalActor):
    actor_name = actor.name if actor else None
    camp_svc.remove_campaign_asset(db, campaign_id, asset_id, actor_name=actor_name)
    return None


@router.post(
    "/campaigns/{campaign_id}/audits",
    response_model=CampaignAuditOut,
    status_code=status.HTTP_201_CREATED,
    summary="Run a full consistency and readiness audit on the campaign",
)
def run_campaign_audit(campaign_id: uuid.UUID, db: DbSession, actor: OptionalActor):
    actor_name = actor.name if actor else None
    audit = audit_svc.run_campaign_audit(db, campaign_id, actor_name=actor_name)
    audit_data = audit_svc.get_campaign_audit(db, audit.id)
    return CampaignAuditOut.model_validate(audit_data)


@router.get(
    "/campaigns/{campaign_id}/audits",
    response_model=list[CampaignAuditOut],
    summary="List historical audits for a campaign",
)
def list_campaign_audits(campaign_id: uuid.UUID, db: DbSession):
    audits = audit_svc.list_campaign_audits(db, campaign_id)
    return [CampaignAuditOut.model_validate(a) for a in audits]


@router.get(
    "/campaign-audits/{audit_id}",
    response_model=CampaignAuditOut,
    summary="Get an audit with its full findings and evidence links",
)
def get_campaign_audit(audit_id: uuid.UUID, db: DbSession):
    audit_data = audit_svc.get_campaign_audit(db, audit_id)
    if not audit_data:
        raise camp_svc.CampaignError("audit_not_found", "Audit not found", 404)
    return CampaignAuditOut.model_validate(audit_data)


@router.get(
    "/campaign-audits/{audit_id}/comparison/{previous_audit_id}",
    response_model=AuditComparisonOut,
    summary="Compare findings between two campaign audits",
)
def compare_campaign_audits(audit_id: uuid.UUID, previous_audit_id: uuid.UUID, db: DbSession):
    return audit_svc.compare_campaign_audits(db, audit_id, previous_audit_id)


@router.get(
    "/campaigns/{campaign_id}/release-evaluation",
    response_model=ReleaseEvaluationOut,
    summary="Evaluate release readiness for a campaign",
)
def get_release_evaluation(campaign_id: uuid.UUID, db: DbSession):
    return audit_svc.evaluate_release_readiness(db, campaign_id)


@router.post(
    "/campaigns/{campaign_id}/release-evaluation",
    response_model=ReleaseEvaluationOut,
    summary="Evaluate release readiness for a campaign (POST support)",
)
def post_release_evaluation(campaign_id: uuid.UUID, db: DbSession):
    return audit_svc.evaluate_release_readiness(db, campaign_id)


@router.post(
    "/campaigns/{campaign_id}/release",
    response_model=CampaignReleaseOut,
    status_code=status.HTTP_200_OK,
    summary="Explicitly release a verified campaign (reviewer only)",
)
def release_campaign(
    campaign_id: uuid.UUID,
    data: CampaignReleaseRequest,
    db: DbSession,
    actor: ReviewerActor,
):
    decision = audit_svc.release_campaign(
        db,
        campaign_id,
        actor_name=actor.name,
        actor_role=actor.role,
        release_notes=data.release_notes,
    )
    return CampaignReleaseOut(
        decision_id=decision.id,
        campaign_id=decision.campaign_id,
        audit_id=decision.audit_id,
        decision=decision.decision,
        actor_name=decision.actor_name,
        actor_role=decision.actor_role,
        release_notes=decision.release_notes,
        released_at=decision.created_at,
    )
