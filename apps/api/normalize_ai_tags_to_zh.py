from __future__ import annotations

from app.database import SessionLocal
from app.models.ai import PhotoAIAnalysis
from app.models.photo import Photo  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.services.json_parser import validate_image_analysis_result


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.query(PhotoAIAnalysis).all()
        updated = 0

        for row in rows:
            payload = validate_image_analysis_result(
                {
                    "caption": row.caption or "",
                    "scene_tags": row.scene_tags or [],
                    "object_tags": row.object_tags or [],
                    "activity_tags": row.activity_tags or [],
                    "people_count": row.people_count or 0,
                    "ocr_text": (row.ocr_text or "").splitlines() if row.ocr_text else [],
                    "location_clues": row.location_clues or [],
                    "quality_tags": row.quality_tags or [],
                    "search_keywords": row.search_keywords or [],
                    "confidence": row.confidence or 0.0,
                }
            )

            changed = (
                payload["scene_tags"] != (row.scene_tags or [])
                or payload["object_tags"] != (row.object_tags or [])
                or payload["activity_tags"] != (row.activity_tags or [])
                or payload["quality_tags"] != (row.quality_tags or [])
                or payload["location_clues"] != (row.location_clues or [])
                or payload["search_keywords"] != (row.search_keywords or [])
            )
            if not changed:
                continue

            row.scene_tags = payload["scene_tags"]
            row.object_tags = payload["object_tags"]
            row.activity_tags = payload["activity_tags"]
            row.quality_tags = payload["quality_tags"]
            row.location_clues = payload["location_clues"]
            row.search_keywords = payload["search_keywords"]

            if isinstance(row.raw_result, dict):
                raw_result = dict(row.raw_result)
                raw_result.update(
                    {
                        "scene_tags": payload["scene_tags"],
                        "object_tags": payload["object_tags"],
                        "activity_tags": payload["activity_tags"],
                        "quality_tags": payload["quality_tags"],
                        "location_clues": payload["location_clues"],
                        "search_keywords": payload["search_keywords"],
                    }
                )
                row.raw_result = raw_result

            updated += 1

        db.commit()
        print(f"normalized_rows={updated}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
