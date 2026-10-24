"""Phase 6 campaign management service."""
from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.campaign import Campaign, CampaignAsset, CampaignAudit
from app.models.review import ContentAsset, ContentSubmission
from app.schemas.campaign import CampaignAssetAdd, CampaignCreate, CampaignUpdate


class CampaignError(AppError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message, code=code)
        self.status_code = status_code



def create_campaign(db: Session, brand_id: uuid.UUID, data: CampaignCreate, actor_name: Optional[str] = None) -> Campaign:
    from app.models.brand import Brand
    brand = db.execute(select(Brand).where(Brand.id == brand_id)).scalars().first()
    if not brand:
        raise CampaignError("brand_not_found", "Brand not found", 404)

    campaign = Campaign(
        brand_id=brand_id,
        title=data.title.strip(),
        description=data.description.strip() if data.description else None,
        external_reference=data.external_reference.strip() if data.external_reference else None,
        owner=data.owner.strip() if data.owner else actor_name,
        status="draft",
    )

    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def get_campaign(db: Session, campaign_id: uuid.UUID) -> Optional[Campaign]:
    return db.execute(select(Campaign).where(Campaign.id == campaign_id)).scalars().first()


def list_campaigns(db: Session, brand_id: uuid.UUID, status: Optional[str] = None) -> list[Campaign]:
    query = select(Campaign).where(Campaign.brand_id == brand_id)
    if status:
        query = query.where(Campaign.status == status)
    query = query.order_by(Campaign.created_at.desc())
    return list(db.execute(query).scalars().all())


def update_campaign(db: Session, campaign_id: uuid.UUID, data: CampaignUpdate, actor_name: Optional[str] = None) -> Campaign:
    campaign = get_campaign(db, campaign_id)
    if not campaign:
        raise CampaignError("campaign_not_found", "Campaign not found", 404)

    if data.title is not None:
        campaign.title = data.title.strip()
    if data.description is not None:
        campaign.description = data.description.strip() if data.description else None
    if data.external_reference is not None:
        campaign.external_reference = data.external_reference.strip() if data.external_reference else None
    if data.owner is not None:
        campaign.owner = data.owner.strip() if data.owner else None
    if data.status is not None:
        campaign.status = data.status

    campaign.updated_at = datetime.now()
    db.commit()
    db.refresh(campaign)
    return campaign


def add_campaign_asset(db: Session, campaign_id: uuid.UUID, data: CampaignAssetAdd, actor_name: Optional[str] = None) -> CampaignAsset:
    campaign = get_campaign(db, campaign_id)
    if not campaign:
        raise CampaignError("campaign_not_found", "Campaign not found", 404)

    # 1. Verify content asset exists and belongs to the same brand
    content_asset = db.execute(select(ContentAsset).where(ContentAsset.id == data.asset_id)).scalars().first()
    if not content_asset:
        raise CampaignError("asset_not_found", "Content asset not found", 404)
    if content_asset.brand_id != campaign.brand_id:
        raise CampaignError("cross_brand_asset", "Asset belongs to another brand", 422)

    # 2. Check for duplicate membership
    existing = db.execute(
        select(CampaignAsset).where(CampaignAsset.campaign_id == campaign_id, CampaignAsset.asset_id == data.asset_id)
    ).scalars().first()
    if existing:
        if data.submission_id and data.submission_id != existing.selected_submission_id:
            # Replacing selected revision of existing asset
            submission = db.execute(select(ContentSubmission).where(ContentSubmission.id == data.submission_id)).scalars().first()
            if not submission or submission.asset_id != data.asset_id:
                raise CampaignError("invalid_submission", "Specified submission does not belong to this asset", 422)
            existing.selected_submission_id = submission.id
            if data.channel_role:
                existing.channel_role = data.channel_role
            if data.notes:
                existing.notes = data.notes
            existing.updated_at = datetime.now()
            # Invalidate existing audits
            db.execute(
                update(CampaignAudit)
                .where(CampaignAudit.campaign_id == campaign_id, CampaignAudit.is_stale == False)
                .values(is_stale=True, stale_reason="Asset revision replaced in campaign")
            )
            if campaign.status in ("ready_for_release", "needs_review", "blocked"):
                campaign.status = "draft"
            db.commit()
            db.refresh(existing)
            return existing
        raise CampaignError("duplicate_membership", "Asset is already a member of this campaign", 409)

    # 3. Resolve selected revision
    if data.submission_id:
        submission = db.execute(select(ContentSubmission).where(ContentSubmission.id == data.submission_id)).scalars().first()
        if not submission or submission.asset_id != data.asset_id:
            raise CampaignError("invalid_submission", "Specified submission does not belong to this asset", 422)
    else:
        # Pick the latest revision
        submission = db.execute(
            select(ContentSubmission)
            .where(ContentSubmission.asset_id == data.asset_id)
            .order_by(ContentSubmission.revision_number.desc())
        ).scalars().first()
        if not submission:
            raise CampaignError("submission_not_found", "Asset has no revisions", 422)

    # 4. Insert CampaignAsset
    campaign_asset = CampaignAsset(
        campaign_id=campaign_id,
        brand_id=campaign.brand_id,
        asset_id=data.asset_id,
        selected_submission_id=submission.id,
        channel_role=data.channel_role or "landing_page",
        display_order=data.display_order or 0,
        notes=data.notes,
        added_by=actor_name,
    )
    db.add(campaign_asset)

    # 5. Invalidate existing audits
    db.execute(
        update(CampaignAudit)
        .where(CampaignAudit.campaign_id == campaign_id, CampaignAudit.is_stale == False)
        .values(is_stale=True, stale_reason="Asset added to campaign")
    )
    if campaign.status in ("ready_for_release", "needs_review", "blocked"):
        campaign.status = "draft"

    db.commit()
    db.refresh(campaign_asset)
    return campaign_asset


def remove_campaign_asset(db: Session, campaign_id: uuid.UUID, asset_id: uuid.UUID, actor_name: Optional[str] = None) -> bool:
    campaign = get_campaign(db, campaign_id)
    if not campaign:
        raise CampaignError("campaign_not_found", "Campaign not found", 404)

    item = db.execute(
        select(CampaignAsset).where(CampaignAsset.campaign_id == campaign_id, CampaignAsset.asset_id == asset_id)
    ).scalars().first()
    if not item:
        raise CampaignError("asset_not_in_campaign", "Asset is not in this campaign", 404)

    db.delete(item)

    # Invalidate existing audits
    db.execute(
        update(CampaignAudit)
        .where(CampaignAudit.campaign_id == campaign_id, CampaignAudit.is_stale == False)
        .values(is_stale=True, stale_reason="Asset removed from campaign")
    )
    if campaign.status in ("ready_for_release", "needs_review", "blocked"):
        campaign.status = "draft"

    db.commit()
    return True


def update_campaign_asset_revision(
    db: Session, campaign_id: uuid.UUID, asset_id: uuid.UUID, submission_id: uuid.UUID, actor_name: Optional[str] = None
) -> CampaignAsset:
    campaign = get_campaign(db, campaign_id)
    if not campaign:
        raise CampaignError("campaign_not_found", "Campaign not found", 404)

    item = db.execute(
        select(CampaignAsset).where(CampaignAsset.campaign_id == campaign_id, CampaignAsset.asset_id == asset_id)
    ).scalars().first()
    if not item:
        raise CampaignError("asset_not_in_campaign", "Asset is not in this campaign", 404)

    submission = db.execute(select(ContentSubmission).where(ContentSubmission.id == submission_id)).scalars().first()
    if not submission or submission.asset_id != asset_id:
        raise CampaignError("invalid_submission", "Specified submission does not belong to this asset", 422)

    item.selected_submission_id = submission_id

    # Invalidate existing audits
    db.execute(
        update(CampaignAudit)
        .where(CampaignAudit.campaign_id == campaign_id, CampaignAudit.is_stale == False)
        .values(is_stale=True, stale_reason="Asset revision selection changed")
    )
    if campaign.status in ("ready_for_release", "needs_review", "blocked"):
        campaign.status = "draft"

    db.commit()
    db.refresh(item)
    return item


def list_campaign_assets(db: Session, campaign_id: uuid.UUID) -> list[dict[str, Any]]:
    stmt = (
        select(
            CampaignAsset,
            ContentAsset.title.label("asset_title"),
            ContentSubmission.revision_number,
            ContentSubmission.content_hash,
            ContentSubmission.workflow_status,
        )
        .join(ContentAsset, ContentAsset.id == CampaignAsset.asset_id)
        .join(ContentSubmission, ContentSubmission.id == CampaignAsset.selected_submission_id)
        .where(CampaignAsset.campaign_id == campaign_id)
        .order_by(CampaignAsset.display_order.asc(), CampaignAsset.added_at.asc())
    )
    rows = db.execute(stmt).all()
    results = []
    for asset, asset_title, revision_number, content_hash, workflow_status in rows:
        results.append({
            "id": asset.id,
            "campaign_id": asset.campaign_id,
            "brand_id": asset.brand_id,
            "asset_id": asset.asset_id,
            "asset_title": asset_title,
            "selected_submission_id": asset.selected_submission_id,
            "revision_number": revision_number,
            "content_hash": content_hash,
            "workflow_status": workflow_status,
            "channel_role": asset.channel_role,
            "display_order": asset.display_order,
            "notes": asset.notes,
            "added_by": asset.added_by,
            "added_at": asset.added_at,
        })
    return results
