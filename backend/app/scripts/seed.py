"""Repeatable demo seed: the fictional Nova Systems brand, three source documents and sample facts.

Usage (from backend/):
  python -m app.scripts.seed            # create demo data if the brand does not exist
  python -m app.scripts.seed --reset    # remove existing Nova Systems data first, then recreate

Seeded data is fictional. Documents go through the same upload and extraction pipeline as real uploads,
and every document-backed fact carries a real page reference and an excerpt verified against extracted text.
"""
import argparse
import io
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_db, get_engine
from app.models import (
    ApprovedFact, Brand, ContentAsset, ContentSubmission, DocumentSection, FactChangeImpact, FactChangeImpactFinding, FactChangeImpactResolution,
    FactRevision, FindingEvidence, ReviewFinding, ReviewRun, RevisionCorrection, RiskOverride, SourceDocument, WorkflowEvent,
)

# Phase 4 history tables are append-only (a trigger rejects DELETE). This development-only reset lifts that inside its own
# transaction, for this brand's rows only; the triggers are re-enabled before the commit.
APPEND_ONLY_TRIGGERS = {
    "workflow_events": "trg_workflow_events_append_only", "risk_overrides": "trg_risk_overrides_append_only",
    "revision_corrections": "trg_revision_corrections_append_only", "fact_change_impact_resolutions": "trg_impact_resolutions_append_only",
}
from app.schemas.brand import BrandCreate
from app.schemas.fact import FactCreate, FactStatusUpdate, FactUpdate
from app.scripts.make_test_data import TEST_DATA, main as make_test_data
from app.services import documents, facts, storage
from app.services.brands import create_brand

BRAND_NAME = "Nova Systems"
ACTOR = "seed script"


def reset(db: Session) -> None:
    brand = db.scalar(select(Brand).where(Brand.name == BRAND_NAME))
    if brand is None:
        return
    keys = [d.storage_path for d in db.scalars(select(SourceDocument).where(SourceDocument.brand_id == brand.id))]
    for table, trigger in APPEND_ONLY_TRIGGERS.items():
        db.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
    # Impacts, decisions and review data reference facts and documents, so they go first.
    for model in (
        FactChangeImpactResolution, RiskOverride, RevisionCorrection, FactChangeImpactFinding, FactChangeImpact, WorkflowEvent,
        FindingEvidence, ReviewFinding, ReviewRun,
    ):
        db.execute(delete(model).where(model.brand_id == brand.id))
    # Revisions form a chain (parent_submission_id): delete newest first.
    while db.execute(text(
        "DELETE FROM content_submissions s WHERE s.brand_id = :b AND NOT EXISTS (SELECT 1 FROM content_submissions c WHERE c.parent_submission_id = s.id)"
    ), {"b": brand.id}).rowcount:
        pass
    db.execute(delete(ContentAsset).where(ContentAsset.brand_id == brand.id))
    for table, trigger in APPEND_ONLY_TRIGGERS.items():
        db.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))
    fact_ids = select(ApprovedFact.id).where(ApprovedFact.brand_id == brand.id)
    db.execute(delete(FactRevision).where(FactRevision.fact_id.in_(fact_ids)))
    db.execute(delete(ApprovedFact).where(ApprovedFact.brand_id == brand.id))
    doc_ids = select(SourceDocument.id).where(SourceDocument.brand_id == brand.id)
    db.execute(delete(DocumentSection).where(DocumentSection.document_id.in_(doc_ids)))
    db.execute(delete(SourceDocument).where(SourceDocument.brand_id == brand.id))
    db.execute(delete(Brand).where(Brand.id == brand.id))
    db.commit()
    for key in keys:
        storage.delete(key)


def upload(db: Session, brand_id, path: Path, title: str) -> SourceDocument:
    doc = documents.upload_document(db, brand_id, filename=path.name, title=title, stream=io.BytesIO(path.read_bytes()))
    if doc.processing_status != "processed":
        raise RuntimeError(f"Seed document {path.name} failed to process: {doc.error_message}")
    return doc


def page_of(db: Session, doc: SourceDocument, excerpt: str) -> int:
    """Locate the page whose extracted text contains the excerpt; fail loudly if it is not there."""
    target = " ".join(excerpt.split()).casefold()
    for s in db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id)):
        if s.page_number and target in " ".join(s.text.split()).casefold():
            return s.page_number
    raise RuntimeError(f"Seed excerpt not found in {doc.filename}: {excerpt!r}")


def seed(db: Session) -> None:
    today = clock.today()
    make_test_data()
    brand = create_brand(db, BrandCreate(
        name=BRAND_NAME,
        description="Fictional demonstration brand. All products, figures and documents are invented for testing.",
    ))
    pdf = upload(db, brand.id, TEST_DATA / "nova_product_specification.pdf", "Nova product specification v3.2")
    txt = upload(db, brand.id, TEST_DATA / "nova_terminology_guide.txt", "Nova terminology guide")
    csv_doc = upload(db, brand.id, TEST_DATA / "nova_spec_table.csv", "Nova specification table")

    def fact(**kw) -> ApprovedFact:
        status = kw.pop("status", "active")
        return facts.create_fact(db, brand.id, FactCreate(actor=ACTOR, status=status, **kw))

    ex_battery = "Battery life: up to 18 hours under specified test conditions."
    battery = fact(
        name="Battery life", value="Up to 18 hours", category="product_spec",
        qualifications="Under specified test conditions: 1080p local video playback, 50 percent brightness, wireless on.",
        owner="Product team", valid_from=today - timedelta(days=60), review_date=today + timedelta(days=45),
        expires_at=today + timedelta(days=200), source_document_id=pdf.id,
        source_page=page_of(db, pdf, ex_battery), source_excerpt=ex_battery,
    )
    ex_perf = "Performance improvement: 25 percent faster multi-core processing"
    fact(
        name="Performance improvement", value="25", unit="%", category="approved_claim",
        qualifications="Under the approved comparison methodology (Benchmark Method NS-BM-4), versus the previous generation.",
        owner="Performance engineering", review_date=today + timedelta(days=12), expires_at=today + timedelta(days=120),
        source_document_id=pdf.id, source_page=page_of(db, pdf, ex_perf), source_excerpt=ex_perf,
    )
    ex_name = "Product name: Nova. The exact approved product name is Nova."
    fact(
        name="Product name", value="Nova", category="terminology", qualifications="Exact approved name. Do not abbreviate or prefix.",
        owner="Brand team", source_document_id=pdf.id, source_page=page_of(db, pdf, ex_name), source_excerpt=ex_name,
    )
    ex_warranty = "Limited warranty: 2 years from the date of purchase."
    fact(
        name="Warranty period", value="2 years", category="legal_disclaimer", qualifications="Limited warranty; see warranty terms for exclusions.",
        owner="Legal", status="proposed", review_date=today + timedelta(days=90),
        source_document_id=pdf.id, source_page=page_of(db, pdf, ex_warranty), source_excerpt=ex_warranty,
    )
    fact(
        name="Avoided words", value="fastest, best ever, unbeatable", category="terminology",
        qualifications="Never use these words in claims about Nova.", owner="Brand team",
        review_date=today + timedelta(days=150), expires_at=today + timedelta(days=365), source_document_id=txt.id,
        source_excerpt="Do not use the words fastest, best ever or unbeatable in any claim about Nova.",
    )
    fact(
        name="Weight", value="1.24", unit="kg", category="product_spec", qualifications="Measured without charger.",
        owner="Product team", review_date=today + timedelta(days=100), expires_at=today + timedelta(days=300),
        source_document_id=csv_doc.id, source_excerpt="Specification = Weight; Value = 1.24; Unit = kg",
    )
    fact(
        name="Launch price", value="From 999 USD", category="pricing", qualifications="Launch promotion only.",
        owner="Marketing", valid_from=today - timedelta(days=90), expires_at=today + timedelta(days=20),
        source_note="Confirmed by the Nova marketing lead for the launch promotion (fictional).",
    )
    # Demonstrate an explicit status change and a date that has lapsed.
    promo = facts.get_fact(db, facts.list_facts(db, brand.id, limit=1, offset=0, q="Launch price")[0][0].id)
    facts.update_fact(db, promo.id, FactUpdate(expires_at=today - timedelta(days=3), actor=ACTOR,
                                               change_reason="Promotion window ended."))
    legacy = fact(
        name="Legacy battery claim", value="Up to 14 hours", category="approved_claim",
        qualifications="Previous generation only.", owner="Product team", expires_at=today + timedelta(days=5),
        source_note="Carried over from the previous generation datasheet (fictional).",
    )
    facts.change_status(db, legacy.id, FactStatusUpdate(
        status="expired", actor=ACTOR, reason="Superseded by the Nova 3.2 specification."))
    # An edited, previously approved fact: shows revision history and re-approval semantics.
    facts.update_fact(db, battery.id, FactUpdate(owner="Product marketing", actor=ACTOR, change_reason="Ownership moved."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="remove existing Nova Systems data first")
    args = parser.parse_args()
    get_engine()
    db = next(get_db())
    try:
        if args.reset:
            reset(db)
        if db.scalar(select(Brand).where(Brand.name == BRAND_NAME)):
            print(f"{BRAND_NAME} already exists; nothing to do (use --reset to recreate).")
            return 0
        seed(db)
        brand = db.scalar(select(Brand).where(Brand.name == BRAND_NAME))
        print(f"Seeded {BRAND_NAME} (id={brand.id}).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
