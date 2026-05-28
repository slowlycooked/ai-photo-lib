"""Backfill GPS-derived location tokens into photo_ai_analysis.location_clues and search_keywords.

For photos that have already been AI-analyzed, this script reads the GPS location fields
(city, district, admin2, admin1, country_name) from the photos table and merges any
missing tokens into photo_ai_analysis.location_clues and search_keywords.

Usage (from apps/api directory, with venv active):
    python backfill_gps_location_clues.py [--project-id N] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
import os

# Allow running from apps/api dir
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.models import ai as _ai_models  # noqa: F401 - register all models with metadata
from app.models import photo as _photo_models  # noqa: F401
from app.models import project as _project_models  # noqa: F401
from app.models import face as _face_models  # noqa: F401
from app.models import folder as _folder_models  # noqa: F401
from app.models.ai import PhotoAIAnalysis
from app.models.photo import Photo
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _merge_tokens(existing: list[str], *new_vals: str | None) -> tuple[list[str], list[str]]:
    """Return (merged_list, added_tokens)."""
    seen = {t.strip() for t in existing if t.strip()}
    merged = list(existing)
    added: list[str] = []
    for val in new_vals:
        if val:
            token = val.strip()
            if token and token not in seen:
                merged.append(token)
                seen.add(token)
                added.append(token)
    return merged, added


def backfill(db: Session, project_id: int | None, dry_run: bool) -> None:
    query = (
        db.query(PhotoAIAnalysis, Photo)
        .join(Photo, (Photo.id == PhotoAIAnalysis.photo_id) & (Photo.project_id == PhotoAIAnalysis.project_id))
        .filter(Photo.gps_latitude.isnot(None))  # only photos with GPS
    )
    if project_id is not None:
        query = query.filter(PhotoAIAnalysis.project_id == project_id)

    rows = query.all()
    logger.info("Found %d analyzed photos with GPS data to check.", len(rows))

    updated = 0
    for analysis, photo in rows:
        gps_tokens = [
            photo.city,
            photo.district,
            photo.admin2,
            photo.admin1,
            photo.country_name,
        ]

        new_clues, added_clues = _merge_tokens(analysis.location_clues or [], *gps_tokens)
        new_keywords, added_kw = _merge_tokens(analysis.search_keywords or [], *new_clues)

        if not added_clues and not added_kw:
            continue

        logger.info(
            "project_id=%d photo_id=%d file=%s  +location_clues=%s +search_keywords=%s",
            photo.project_id,
            photo.id,
            photo.file_name,
            added_clues,
            [t for t in added_kw if t not in added_clues],
        )

        if not dry_run:
            analysis.location_clues = new_clues
            analysis.search_keywords = new_keywords
        updated += 1

    if dry_run:
        logger.info("[DRY RUN] Would update %d photo_ai_analysis rows.", updated)
    else:
        db.commit()
        logger.info("Updated %d photo_ai_analysis rows.", updated)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, default=None, help="Limit to one project")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        backfill(db, project_id=args.project_id, dry_run=args.dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    main()
