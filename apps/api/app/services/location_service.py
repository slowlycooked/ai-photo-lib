from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Optional

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..config import settings
from ..models.location_cache import PhotoLocationCache
from ..models.photo import Photo

logger = logging.getLogger(__name__)

_LOCATION_ATTRS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "admin1",
    "admin2",
    "city",
    "district",
    "formatted_address",
)


@dataclass(frozen=True)
class ResolvedPhotoLocation:
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    admin1: Optional[str] = None
    admin2: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    formatted_address: Optional[str] = None
    location_source: Optional[str] = None


class ReverseGeocodeProvider:
    name = "base"

    def resolve(self, latitude: float, longitude: float) -> Optional[ResolvedPhotoLocation]:
        raise NotImplementedError


class NominatimReverseGeocodeProvider(ReverseGeocodeProvider):
    name = "nominatim"

    def __init__(self, endpoint_url: str, *, timeout_seconds: int, user_agent: str) -> None:
        self._endpoint_url = endpoint_url
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    def resolve(self, latitude: float, longitude: float) -> Optional[ResolvedPhotoLocation]:
        try:
            response = httpx.get(
                self._endpoint_url,
                params={
                    "format": "jsonv2",
                    "lat": latitude,
                    "lon": longitude,
                    "zoom": 18,
                    "addressdetails": 1,
                },
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "application/json",
                },
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reverse geocode failed for lat=%s lon=%s via %s: %s",
                latitude,
                longitude,
                self.name,
                exc,
            )
            return None

        if not isinstance(payload, dict):
            return None

        address = payload.get("address")
        if not isinstance(address, dict):
            address = {}

        return ResolvedPhotoLocation(
            country_code=_clean_value((address.get("country_code") or "").upper()),
            country_name=_clean_value(address.get("country")),
            admin1=_clean_value(
                address.get("state")
                or address.get("province")
                or address.get("region")
            ),
            admin2=_clean_value(
                address.get("county")
                or address.get("state_district")
                or address.get("municipality")
            ),
            city=_clean_value(
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
            ),
            district=_clean_value(
                address.get("city_district")
                or address.get("district")
                or address.get("suburb")
                or address.get("borough")
            ),
            formatted_address=_clean_value(payload.get("display_name")),
            location_source=self.name,
        )


def _clean_value(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _round_coordinate(value: float) -> float:
    return round(float(value), settings.location_cache_rounding_decimals)


def _build_location_key(latitude: float, longitude: float) -> str:
    rounded_lat = _round_coordinate(latitude)
    rounded_lon = _round_coordinate(longitude)
    decimals = settings.location_cache_rounding_decimals
    return f"{rounded_lat:.{decimals}f},{rounded_lon:.{decimals}f}"


def _build_provider() -> Optional[ReverseGeocodeProvider]:
    provider = (settings.location_resolver_provider or "none").strip().lower()
    if provider in ("", "none", "disabled", "off"):
        return None
    if provider == "nominatim":
        return NominatimReverseGeocodeProvider(
            settings.location_resolver_endpoint,
            timeout_seconds=settings.location_resolver_timeout_seconds,
            user_agent=settings.location_resolver_user_agent,
        )

    logger.warning("Unsupported location resolver provider: %s", provider)
    return None


def _apply_resolved_location(
    photo: Photo,
    resolved: ResolvedPhotoLocation,
    *,
    resolved_at: Optional[datetime] = None,
) -> bool:
    changed = False
    for attr in _LOCATION_ATTRS:
        value = getattr(resolved, attr)
        if getattr(photo, attr) != value:
            setattr(photo, attr, value)
            changed = True

    source = resolved.location_source
    if photo.location_source != source:
        photo.location_source = source
        changed = True

    target_resolved_at = resolved_at or _now_utc_naive()
    if photo.location_resolved_at != target_resolved_at:
        photo.location_resolved_at = target_resolved_at
        changed = True

    return changed


def _cache_to_resolved(cache_row: PhotoLocationCache) -> ResolvedPhotoLocation:
    return ResolvedPhotoLocation(
        country_code=cache_row.country_code,
        country_name=cache_row.country_name,
        admin1=cache_row.admin1,
        admin2=cache_row.admin2,
        city=cache_row.city,
        district=cache_row.district,
        formatted_address=cache_row.formatted_address,
        location_source=cache_row.location_source,
    )


def _upsert_cache_row(
    db: Session,
    *,
    latitude: float,
    longitude: float,
    resolved: ResolvedPhotoLocation,
) -> PhotoLocationCache:
    location_key = _build_location_key(latitude, longitude)
    rounded_lat = _round_coordinate(latitude)
    rounded_lon = _round_coordinate(longitude)
    now = _now_utc_naive()

    values = {
        "location_key": location_key,
        "latitude_rounded": rounded_lat,
        "longitude_rounded": rounded_lon,
        "country_code": resolved.country_code,
        "country_name": resolved.country_name,
        "admin1": resolved.admin1,
        "admin2": resolved.admin2,
        "city": resolved.city,
        "district": resolved.district,
        "formatted_address": resolved.formatted_address,
        "location_source": resolved.location_source,
        "updated_at": now,
    }

    update_fields = {
        "latitude_rounded": rounded_lat,
        "longitude_rounded": rounded_lon,
        "country_code": resolved.country_code,
        "country_name": resolved.country_name,
        "admin1": resolved.admin1,
        "admin2": resolved.admin2,
        "city": resolved.city,
        "district": resolved.district,
        "formatted_address": resolved.formatted_address,
        "location_source": resolved.location_source,
        "updated_at": now,
    }

    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        stmt = (
            pg_insert(PhotoLocationCache.__table__)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[PhotoLocationCache.__table__.c.location_key],
                set_=update_fields,
            )
        )
        db.execute(stmt)
    elif dialect_name == "sqlite":
        stmt = (
            sqlite_insert(PhotoLocationCache.__table__)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[PhotoLocationCache.__table__.c.location_key],
                set_=update_fields,
            )
        )
        db.execute(stmt)
    else:
        row = (
            db.query(PhotoLocationCache)
            .filter(PhotoLocationCache.location_key == location_key)
            .first()
        )
        if row is None:
            row = PhotoLocationCache(**values)
            db.add(row)
        else:
            row.latitude_rounded = rounded_lat
            row.longitude_rounded = rounded_lon
            row.country_code = resolved.country_code
            row.country_name = resolved.country_name
            row.admin1 = resolved.admin1
            row.admin2 = resolved.admin2
            row.city = resolved.city
            row.district = resolved.district
            row.formatted_address = resolved.formatted_address
            row.location_source = resolved.location_source
            row.updated_at = now

    row = (
        db.query(PhotoLocationCache)
        .filter(PhotoLocationCache.location_key == location_key)
        .first()
    )
    if row is None:
        raise RuntimeError(f"location cache upsert failed for key={location_key}")
    return row


def photo_has_structured_location(photo: Photo) -> bool:
    return any(getattr(photo, attr, None) for attr in _LOCATION_ATTRS)


def resolve_photo_location(
    db: Session,
    photo: Photo,
    *,
    force: bool = False,
) -> bool:
    latitude = getattr(photo, "gps_latitude", None)
    longitude = getattr(photo, "gps_longitude", None)
    if latitude is None or longitude is None:
        return False

    if not force and photo.location_resolved_at and photo_has_structured_location(photo):
        return False

    location_key = _build_location_key(latitude, longitude)
    cached = (
        db.query(PhotoLocationCache)
        .filter(PhotoLocationCache.location_key == location_key)
        .first()
    )
    if cached is not None:
        changed = _apply_resolved_location(
            photo,
            _cache_to_resolved(cached),
            resolved_at=_now_utc_naive(),
        )
        return changed

    provider = _build_provider()
    if provider is None:
        return False

    resolved = provider.resolve(latitude, longitude)
    if resolved is None:
        return False

    _upsert_cache_row(
        db,
        latitude=latitude,
        longitude=longitude,
        resolved=resolved,
    )
    return _apply_resolved_location(photo, resolved)
