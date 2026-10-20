#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


Fingerprint = Tuple[int, int, int, int]


@dataclass(frozen=True)
class MovePlan:
    line_number: int
    photo_id: Any
    source: Path
    destination: Path
    expected_hash: str
    expected_size: Optional[int]
    source_fingerprint: Optional[Fingerprint]
    existing_destination: Optional[Path]
    state: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(path: Path) -> Fingerprint:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("source is not a regular file")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _parse_relative_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("relative_path is missing or invalid")
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"unsafe relative_path: {value!r}")
    return relative


def _ensure_no_source_symlink(source_root: Path, relative: PurePosixPath) -> None:
    current = source_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"source path contains a symlink: {current}")


def _source_path(source_root: Path, relative: PurePosixPath) -> Path:
    _ensure_no_source_symlink(source_root, relative)
    source = source_root.joinpath(*relative.parts)
    resolved = source.resolve(strict=False)
    try:
        resolved.relative_to(source_root)
    except ValueError as exc:
        raise ValueError(f"source escapes source root: {relative}") from exc
    if resolved != source:
        raise ValueError(f"source path does not resolve to itself: {relative}")
    return source


def _destination_path(trash_root: Path, relative: PurePosixPath) -> Path:
    destination = trash_root.joinpath(*relative.parts).resolve(strict=False)
    try:
        destination.relative_to(trash_root)
    except ValueError as exc:
        raise ValueError(f"destination escapes trash root: {relative}") from exc
    return destination


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _iter_manifest(manifest: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with manifest.open("r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
            if not isinstance(entry, dict):
                raise ValueError(f"line {line_number}: JSON entry is not an object")
            yield line_number, entry


def _nearest_existing_directory(path: Path) -> Path:
    current = path
    while not os.path.lexists(current):
        parent = current.parent
        if parent == current:
            raise ValueError(f"no existing ancestor for destination: {path}")
        current = parent
    if current.is_symlink() or not current.is_dir():
        raise ValueError(f"destination ancestor is not a real directory: {current}")
    return current


def _validate_destination_parent(destination: Path) -> Path:
    ancestor = _nearest_existing_directory(destination.parent)
    if not os.access(ancestor, os.W_OK | os.X_OK):
        raise ValueError(f"destination ancestor is not writable: {ancestor}")
    return ancestor


def _candidate(path: Path, index: int) -> Path:
    if index == 0:
        return path
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


def _candidate_index(path: Path, candidate: Path) -> Optional[int]:
    if candidate.name == path.name:
        return 0
    prefix = f"{path.stem}."
    suffix = path.suffix
    name = candidate.name
    if not name.startswith(prefix) or (suffix and not name.endswith(suffix)):
        return None
    end = len(name) - len(suffix) if suffix else len(name)
    number = name[len(prefix) : end]
    return int(number) if number.isdigit() and int(number) > 0 else None


def _destination_candidates(path: Path) -> List[Path]:
    if not path.parent.exists():
        return []
    indexed: List[Tuple[int, Path]] = []
    for candidate in path.parent.iterdir():
        index = _candidate_index(path, candidate)
        if index is not None:
            indexed.append((index, candidate))
    indexed.sort(key=lambda item: item[0])
    return [candidate for _, candidate in indexed]


def _matches_expected_file(
    path: Path, expected_hash: str, expected_size: Optional[int]
) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        return False
    if expected_size is not None and info.st_size != expected_size:
        return False
    return _sha256(path).lower() == expected_hash


def _find_matching_destination(
    destination: Path, expected_hash: str, expected_size: Optional[int]
) -> Optional[Path]:
    for candidate in _destination_candidates(destination):
        if _matches_expected_file(candidate, expected_hash, expected_size):
            return candidate
    return None


def _build_plans(
    manifest: Path,
    source_root: Path,
    trash_root: Path,
    expected_project_id: int,
    expected_project_name: str,
) -> List[MovePlan]:
    plans: List[MovePlan] = []
    errors: List[str] = []
    seen_sources: Set[Path] = set()
    seen_destinations: Set[Path] = set()
    seen_photo_ids: Set[int] = set()

    try:
        entries = list(_iter_manifest(manifest))
    except (OSError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    if not entries:
        raise ValueError("manifest has no entries")

    for line_number, entry in entries:
        try:
            if entry.get("version") != 1:
                raise ValueError("unsupported manifest version")
            if entry.get("action") != "move_original_to_trash":
                raise ValueError("unexpected action")
            if entry.get("project_id") != expected_project_id:
                raise ValueError("project_id does not match this batch")
            if entry.get("project_name") != expected_project_name:
                raise ValueError("project_name does not match this batch")

            photo_id = entry.get("photo_id")
            if (
                not isinstance(photo_id, int)
                or isinstance(photo_id, bool)
                or photo_id <= 0
            ):
                raise ValueError("photo_id must be a positive integer")
            if photo_id in seen_photo_ids:
                raise ValueError(f"duplicate photo_id: {photo_id}")

            relative = _parse_relative_path(entry.get("relative_path"))
            file_name = entry.get("file_name")
            if not isinstance(file_name, str) or not file_name:
                raise ValueError("file_name is missing or invalid")
            if relative.name != file_name:
                raise ValueError("file_name does not match relative_path")

            expected_hash_value = entry.get("file_hash")
            if not _valid_sha256(expected_hash_value):
                raise ValueError("file_hash must be a 64-character SHA-256")
            expected_hash = expected_hash_value.lower()

            expected_size = entry.get("file_size")
            if expected_size is not None and (
                not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or expected_size < 0
            ):
                raise ValueError("file_size must be a non-negative integer or null")

            source = _source_path(source_root, relative)
            destination = _destination_path(trash_root, relative)
            if source in seen_sources:
                raise ValueError(f"duplicate source: {source}")
            if destination in seen_destinations:
                raise ValueError(f"duplicate destination: {destination}")

            destination_ancestor = _validate_destination_parent(destination)
            existing_destination = _find_matching_destination(
                destination, expected_hash, expected_size
            )

            source_fingerprint: Optional[Fingerprint]
            if os.path.lexists(source):
                before = _fingerprint(source)
                actual_hash = _sha256(source)
                after = _fingerprint(source)
                if before != after:
                    raise ValueError("source changed while it was being validated")
                if expected_size is not None and after[2] != expected_size:
                    raise ValueError(
                        f"file size mismatch: expected={expected_size} actual={after[2]}"
                    )
                if actual_hash.lower() != expected_hash:
                    raise ValueError("file hash mismatch")
                source_fingerprint = after
                if existing_destination:
                    state = "finalize-existing"
                else:
                    if after[0] != destination_ancestor.stat().st_dev:
                        raise ValueError(
                            "source and shared-folder recycle bin must be on "
                            "the same filesystem"
                        )
                    state = "move"
            else:
                if existing_destination is None:
                    raise ValueError(
                        "source is missing and no verified copy exists in trash"
                    )
                source_fingerprint = None
                state = "already-done"

            seen_sources.add(source)
            seen_destinations.add(destination)
            seen_photo_ids.add(photo_id)
            plans.append(
                MovePlan(
                    line_number=line_number,
                    photo_id=photo_id,
                    source=source,
                    destination=destination,
                    expected_hash=expected_hash,
                    expected_size=expected_size,
                    source_fingerprint=source_fingerprint,
                    existing_destination=existing_destination,
                    state=state,
                )
            )
        except (OSError, ValueError) as exc:
            errors.append(f"line {line_number}: {exc}")

    if errors:
        raise ValueError("\n".join(errors))
    return plans


def _reserve_destination(path: Path) -> Tuple[Path, Tuple[int, int]]:
    index = 0
    while True:
        candidate = _candidate(path, index)
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            index += 1
            continue
        try:
            info = os.fstat(fd)
            return candidate, (info.st_dev, info.st_ino)
        finally:
            os.close(fd)


def _remove_if_identity(path: Path, identity: Tuple[int, int]) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (info.st_dev, info.st_ino) == identity and stat.S_ISREG(info.st_mode):
        path.unlink()


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_source(plan: MovePlan) -> Fingerprint:
    if plan.source_fingerprint is None:
        raise RuntimeError("source fingerprint is unavailable")
    before = _fingerprint(plan.source)
    actual_hash = _sha256(plan.source)
    after = _fingerprint(plan.source)
    if before != after or after != plan.source_fingerprint:
        raise RuntimeError("source changed after preflight")
    if plan.expected_size is not None and after[2] != plan.expected_size:
        raise RuntimeError("source size changed after preflight")
    if actual_hash.lower() != plan.expected_hash:
        raise RuntimeError("source hash changed after preflight")
    return after


def _move_same_filesystem(plan: MovePlan) -> Path:
    plan.destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination, reservation = _reserve_destination(plan.destination)
    try:
        _verify_source(plan)
        if plan.source.stat().st_dev != destination.parent.stat().st_dev:
            raise RuntimeError(
                "source and shared-folder recycle bin must be on the same filesystem"
            )
        os.replace(plan.source, destination)
        _fsync_directory(destination.parent)
    except Exception:
        _remove_if_identity(destination, reservation)
        raise
    return destination


def _finalize_existing(plan: MovePlan) -> Path:
    destination = plan.existing_destination
    if destination is None:
        raise RuntimeError("verified destination is unavailable")
    _verify_source(plan)
    if not _matches_expected_file(destination, plan.expected_hash, plan.expected_size):
        raise RuntimeError("existing destination changed after preflight")
    plan.source.unlink()
    _fsync_directory(plan.source.parent)
    return destination


def _move(plan: MovePlan) -> Path:
    if plan.state == "already-done":
        if plan.existing_destination is None:
            raise RuntimeError("verified destination is unavailable")
        return plan.existing_destination
    if plan.state == "finalize-existing":
        return _finalize_existing(plan)

    return _move_same_filesystem(plan)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely move ai-photo-lib originals into a NAS trash folder."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--trash-root", type=Path, required=True)
    parser.add_argument("--expected-project-id", type=int, required=True)
    parser.add_argument("--expected-project-name", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        manifest = args.manifest.expanduser().resolve(strict=True)
        source_root = args.source_root.expanduser().resolve(strict=True)
        trash_root = args.trash_root.expanduser().resolve(strict=False)
        if not manifest.is_file():
            raise ValueError(f"manifest is not a regular file: {manifest}")
        if not source_root.is_dir():
            raise ValueError(f"source root is not a directory: {source_root}")
        if trash_root == source_root or _is_below(trash_root, source_root):
            raise ValueError("trash root must not be inside source root")

        plans = _build_plans(
            manifest,
            source_root,
            trash_root,
            args.expected_project_id,
            args.expected_project_name,
        )
    except (OSError, ValueError) as exc:
        print("validation failed; no files were moved:", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2

    ready = sum(plan.state == "move" for plan in plans)
    recoverable = sum(plan.state == "finalize-existing" for plan in plans)
    already_done = sum(plan.state == "already-done" for plan in plans)

    if args.validate_only:
        print(
            f"validated: ready={ready} recoverable={recoverable} "
            f"already_done={already_done}"
        )
        return 0

    if not args.apply:
        for plan in plans:
            if plan.state == "move":
                print(f"would move: {plan.source} -> {plan.destination}")
            elif plan.state == "finalize-existing":
                print(
                    f"would finalize verified copy: {plan.source} -> "
                    f"{plan.existing_destination}"
                )
            else:
                print(f"already moved: {plan.existing_destination}")
        print(
            f"dry-run: ready={ready} recoverable={recoverable} "
            f"already_done={already_done}"
        )
        return 0

    moved = 0
    finalized = 0
    skipped_done = 0
    for plan in plans:
        try:
            destination = _move(plan)
        except (OSError, RuntimeError, ValueError) as exc:
            print(
                f"move failed after {moved} move(s), {finalized} recovery(s), "
                f"and {skipped_done} already-complete item(s); "
                f"photo_id={plan.photo_id!r}: {exc}",
                file=sys.stderr,
            )
            return 3

        if plan.state == "already-done":
            skipped_done += 1
            print(f"already moved: {destination}")
        elif plan.state == "finalize-existing":
            finalized += 1
            print(f"finalized verified copy: {plan.source} -> {destination}")
        else:
            moved += 1
            print(f"moved: {plan.source} -> {destination}")

    print(
        f"applied: moved={moved} recovered={finalized} "
        f"already_done={skipped_done}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
