from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional


@dataclass(frozen=True)
class PeopleAuditFields:
    request_id: Optional[str]
    operator: str


class PeopleAuditService:
    @classmethod
    def resolve_batch_fields(
        cls,
        *,
        headers: Mapping[str, str],
        context_request_id: Optional[str],
        body_request_id: Optional[str],
        body_operator: Optional[str],
        header_operator: Optional[str],
    ) -> PeopleAuditFields:
        request_id = cls._normalize_optional(
            cls._first_present(
                [
                    body_request_id,
                    headers.get("x-request-id"),
                    context_request_id,
                ]
            )
        )
        operator = cls._normalize_required(
            cls._first_present(
                [
                    body_operator,
                    header_operator,
                    headers.get("x-operator"),
                ]
            ),
            default="unknown",
        )
        return PeopleAuditFields(request_id=request_id, operator=operator)

    @staticmethod
    def _first_present(values: Iterable[Optional[str]]) -> Optional[str]:
        for value in values:
            if value:
                return value
        return None

    @classmethod
    def _normalize_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return cls._trim(value) or None

    @classmethod
    def _normalize_required(cls, value: Optional[str], *, default: str) -> str:
        if value is None:
            return default
        return cls._trim(value) or default

    @staticmethod
    def _trim(value: str) -> str:
        return value.strip()[:128]
