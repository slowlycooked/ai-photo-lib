#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Iterable


def _iter_entries(manifest: Path) -> Iterable[dict]:
    with manifest.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"skip invalid JSON line {line_number}: {exc}")


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}.{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _source_path(entry: dict, source_root: Path | None) -> Path:
    relative_path = entry.get("relative_path")
    if source_root is not None and isinstance(relative_path, str) and relative_path:
        return source_root / relative_path

    absolute_path = entry.get("absolute_path")
    if isinstance(absolute_path, str) and absolute_path:
        return Path(absolute_path)

    raise ValueError("entry has neither relative_path nor absolute_path")


def _safe_destination(trash_root: Path, relative_path: str | Path) -> Path:
    destination = (trash_root / relative_path).resolve()
    try:
        destination.relative_to(trash_root)
    except ValueError as exc:
        raise ValueError(f"destination escapes trash root: {relative_path}") from exc
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Move originals listed by ai-photo-lib deletion manifest into a NAS trash folder. "
            "Runs as dry-run unless --apply is passed."
        )
    )
    parser.add_argument("manifest", type=Path, help="Path to pending-original-trash.jsonl")
    parser.add_argument("--trash-root", type=Path, required=True, help="NAS trash folder")
    parser.add_argument(
        "--source-root",
        type=Path,
        help="NAS photo library root. When set, relative_path is resolved under this root.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files. Without this flag, only prints planned moves.",
    )
    args = parser.parse_args()

    manifest = args.manifest.expanduser().resolve()
    trash_root = args.trash_root.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve() if args.source_root else None

    moved = 0
    missing = 0
    skipped = 0

    for entry in _iter_entries(manifest):
        try:
            source = _source_path(entry, source_root)
        except ValueError as exc:
            skipped += 1
            print(f"skip photo_id={entry.get('photo_id')}: {exc}")
            continue

        relative_path = entry.get("relative_path") or source.name
        try:
            destination = _unique_destination(_safe_destination(trash_root, relative_path))
        except ValueError as exc:
            skipped += 1
            print(f"skip photo_id={entry.get('photo_id')}: {exc}")
            continue

        if not source.exists():
            missing += 1
            print(f"missing: {source}")
            continue

        print(f"{'move' if args.apply else 'would move'}: {source} -> {destination}")
        if args.apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        moved += 1

    mode = "applied" if args.apply else "dry-run"
    print(f"{mode}: moved={moved} missing={missing} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
