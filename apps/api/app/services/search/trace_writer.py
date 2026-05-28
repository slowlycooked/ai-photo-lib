"""Search debug trace writer used by search orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SearchDebugTraceWriter:
    trace: list[dict]

    def write(self, event: dict) -> None:
        self.trace.append(event)

    def write_stage(self, stage: str, **fields) -> None:
        event = {"stage": stage}
        event.update(fields)
        self.trace.append(event)

    def extend(self, events: list[dict]) -> None:
        if not events:
            return
        self.trace.extend(events)

    def write_result(
        self,
        *,
        path: str,
        total: int,
        items_in_page: int,
        page: int,
    ) -> None:
        self.write_stage(
            "result",
            path=path,
            total=total,
            items_in_page=items_in_page,
            page=page,
        )


def compact_filter_dict(filters: Optional[dict]) -> dict:
    payload = filters or {}
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, [], False, {})
    }
