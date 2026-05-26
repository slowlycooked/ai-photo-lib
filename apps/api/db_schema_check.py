#!/usr/bin/env python3
"""
db_schema_check.py — database schema check and update tool for ai-photo-lib.

Usage:
    python db_schema_check.py check        # inspect current state, report issues
    python db_schema_check.py upgrade      # run alembic upgrade head
    python db_schema_check.py verify       # deep column/constraint verification
    python db_schema_check.py all          # check + verify (no upgrade)
    python db_schema_check.py fix-version  # deduplicate multiple rows in alembic_version
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.config import settings

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"

OK = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"
WARN = f"{YELLOW}!{RESET}"
INFO = f"{CYAN}·{RESET}"

# ── Expected schema definition ────────────────────────────────────────────────
# Each entry: (table_name, column_name, nullable_allowed, notes)
REQUIRED_COLUMNS: list[tuple[str, str, bool, str]] = [
    # photos
    ("photos", "id", False, "PK"),
    ("photos", "project_id", False, "project isolation"),
    ("photos", "file_path", False, ""),
    ("photos", "status", False, ""),
    ("photos", "taken_at", True, ""),
    ("photos", "folder_id", True, ""),
    # projects
    ("projects", "id", False, "PK"),
    ("projects", "name", False, ""),
    ("projects", "photo_library_path", False, ""),
    ("projects", "is_default", False, ""),
    # ai_jobs
    ("ai_jobs", "id", False, "PK"),
    ("ai_jobs", "project_id", False, "project isolation"),
    ("ai_jobs", "photo_id", False, ""),
    ("ai_jobs", "status", False, ""),
    # photo_ai_analysis
    ("photo_ai_analysis", "id", False, "PK"),
    ("photo_ai_analysis", "project_id", False, "project isolation"),
    ("photo_ai_analysis", "photo_id", False, ""),
    ("photo_ai_analysis", "semantic_concepts", True, "added by migration 026"),
    # photo_embeddings
    ("photo_embeddings", "id", False, "must exist — used by embedding service"),
    ("photo_embeddings", "project_id", False, "project isolation"),
    ("photo_embeddings", "photo_id", False, ""),
    ("photo_embeddings", "embedding_status", False, ""),
    ("photo_embeddings", "caption_text_hash", True, ""),
    ("photo_embeddings", "tag_text_hash", True, ""),
    ("photo_embeddings", "ocr_text_hash", True, ""),
    # project_ai_settings
    ("project_ai_settings", "id", False, "PK"),
    ("project_ai_settings", "project_id", False, "project isolation"),
    # project_search_settings
    ("project_search_settings", "id", False, "PK"),
    ("project_search_settings", "project_id", False, "project isolation"),
    ("project_search_settings", "search_quality_settings", True, "added by migration 018"),
    # app_settings  (PK is 'key'; value column is 'value_json')
    ("app_settings", "key", False, "PK — varchar(64)"),
    ("app_settings", "value_json", False, "JSONB"),
    ("app_settings", "updated_at", False, ""),
]

# Tables that must exist at all
REQUIRED_TABLES = {
    "photos",
    "projects",
    "ai_jobs",
    "photo_ai_analysis",
    "photo_embeddings",
    "project_ai_settings",
    "project_prompt_templates",
    "project_folders",
    "project_search_settings",
    "app_settings",
    "alembic_version",
}

# Expected unique constraints: (table, constraint_name)
REQUIRED_UNIQUE_CONSTRAINTS: list[tuple[str, str]] = [
    ("photos", "uq_photos_project_file_path"),
    ("photo_ai_analysis", "uq_photo_ai_analysis_project_photo"),
    ("photo_embeddings", "uq_photo_embeddings_project_photo"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _alembic_config() -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def _section(title: str) -> None:
    width = 60
    print(f"\n{BOLD}{CYAN}{'─' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * width}{RESET}")


# ── Sub-commands ──────────────────────────────────────────────────────────────

def cmd_check(engine) -> list[str]:
    """
    Inspect alembic_version table and compare current revision with head.
    Returns a list of problem strings (empty = all clear).
    """
    _section("Schema Version Check")
    problems: list[str] = []

    cfg = _alembic_config()
    script = ScriptDirectory.from_config(cfg)

    with engine.connect() as conn:
        # ── 1. alembic_version rows ──────────────────────────────────────────
        try:
            rows = conn.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).fetchall()
        except Exception:
            rows = []

        if not rows:
            msg = "alembic_version table is empty — schema has never been migrated"
            print(f"  {FAIL} {msg}")
            problems.append(msg)
        elif len(rows) > 1:
            versions = [r[0] for r in rows]
            msg = (
                f"alembic_version has {len(rows)} rows: {versions}  "
                f"(should be exactly 1 — run fix-version)"
            )
            print(f"  {FAIL} {msg}")
            problems.append(msg)
        else:
            current = rows[0][0]
            print(f"  {INFO} Current revision : {BOLD}{current}{RESET}")

        # ── 2. Head revision ────────────────────────────────────────────────
        heads = [s.revision for s in script.get_revisions("heads")]
        head = heads[0] if len(heads) == 1 else str(heads)
        print(f"  {INFO} Head   revision : {BOLD}{head}{RESET}")

        # ── 3. Pending migrations ───────────────────────────────────────────
        ctx = MigrationContext.configure(conn)
        current_revs = set(ctx.get_current_heads())

        # Build the complete set of applied revisions:
        # the current heads PLUS all their ancestors.
        # Checking only against current_revs would incorrectly mark every
        # older ancestor (001-017) as "pending".
        applied: set[str] = set(current_revs)
        for crev in list(current_revs):
            try:
                for s in script.iterate_revisions(crev, "base"):
                    applied.add(s.revision)
            except Exception:
                pass

        pending = [
            s
            for s in script.iterate_revisions("heads", "base")
            if s.revision not in applied
        ]
        if pending:
            msg = f"{len(pending)} pending migration(s)"
            print(f"  {WARN} {msg}:")
            for rev in reversed(pending):
                print(f"       {YELLOW}▸{RESET} {rev.revision}  {rev.doc}")
            problems.append(msg)
        else:
            print(f"  {OK} Schema is up-to-date (no pending migrations)")

    return problems


def cmd_upgrade() -> None:
    """Run alembic upgrade head."""
    _section("Running alembic upgrade head")
    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
        print(f"\n  {OK} Upgrade complete")
    except Exception as exc:
        print(f"\n  {FAIL} Upgrade failed: {exc}")
        sys.exit(1)


def cmd_fix_version(engine) -> None:
    """
    Fix the common 'multiple rows in alembic_version' problem by keeping
    only the lexicographically latest version_num.
    """
    _section("Fix alembic_version duplicates")
    cfg = _alembic_config()
    script = ScriptDirectory.from_config(cfg)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num")
        ).fetchall()
        if len(rows) <= 1:
            print(f"  {OK} alembic_version already has exactly {len(rows)} row(s) — nothing to do")
            return

        versions = [r[0] for r in rows]
        print(f"  {WARN} Found {len(versions)} rows: {versions}")

        # Determine the single correct head
        heads = [s.revision for s in script.get_revisions("heads")]
        if len(heads) != 1:
            print(
                f"  {WARN} Cannot auto-resolve: alembic reports multiple heads {heads}. "
                "Resolve the migration branch first."
            )
            sys.exit(1)

        keep = heads[0]
        print(f"  {INFO} Will keep head revision: {BOLD}{keep}{RESET}")

        with conn.begin():
            conn.execute(text("DELETE FROM alembic_version"))
            conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": keep},
            )
        print(f"  {OK} alembic_version now contains exactly one row: {keep}")


def cmd_verify(engine) -> list[str]:
    """
    Deep verification: tables, columns, nullable constraints, unique constraints.
    Returns a list of problem strings.
    """
    _section("Schema Verification")
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    problems: list[str] = []

    # ── 1. Required tables ───────────────────────────────────────────────────
    print(f"\n{BOLD}  Tables{RESET}")
    for tbl in sorted(REQUIRED_TABLES):
        if tbl in existing_tables:
            print(f"  {OK}  {tbl}")
        else:
            msg = f"Missing table: {tbl}"
            print(f"  {FAIL}  {tbl}  ← {RED}MISSING{RESET}")
            problems.append(msg)

    # ── 2. Required columns ──────────────────────────────────────────────────
    print(f"\n{BOLD}  Columns{RESET}")
    _col_cache: dict[str, dict[str, dict]] = {}

    def _cols(table: str) -> dict[str, dict]:
        if table not in _col_cache:
            if table in existing_tables:
                _col_cache[table] = {
                    c["name"]: c for c in insp.get_columns(table)
                }
            else:
                _col_cache[table] = {}
        return _col_cache[table]

    prev_table = ""
    for tbl, col, nullable_ok, note in REQUIRED_COLUMNS:
        cols = _cols(tbl)
        prefix = f"  {tbl}.{col}"
        hint = f"  [{note}]" if note else ""

        if tbl not in existing_tables:
            # Already reported above
            continue

        if col not in cols:
            msg = f"Missing column: {tbl}.{col}{hint}"
            if tbl != prev_table:
                print()
            print(f"  {FAIL}  {prefix}{RED} ← MISSING{RESET}{hint}")
            problems.append(msg)
        else:
            col_info = cols[col]
            actual_nullable = col_info.get("nullable", True)
            if not nullable_ok and actual_nullable:
                msg = f"Column {tbl}.{col} should be NOT NULL but is nullable"
                print(f"  {WARN}  {prefix}  {YELLOW}(nullable — expected NOT NULL){RESET}{hint}")
                problems.append(msg)
            else:
                print(f"  {OK}  {prefix}{hint}")
        prev_table = tbl

    # ── 3. Unique constraints ────────────────────────────────────────────────
    print(f"\n{BOLD}  Unique constraints{RESET}")
    for tbl, cname in REQUIRED_UNIQUE_CONSTRAINTS:
        if tbl not in existing_tables:
            continue
        try:
            uqs = {u["name"] for u in insp.get_unique_constraints(tbl)}
            # Also check indexes (some unique constraints show up as indexes)
            ixs = {i["name"] for i in insp.get_indexes(tbl) if i.get("unique")}
            all_constraints = uqs | ixs
        except Exception:
            all_constraints = set()

        if cname in all_constraints:
            print(f"  {OK}  {tbl}: {cname}")
        else:
            msg = f"Missing unique constraint: {tbl}.{cname}"
            print(f"  {FAIL}  {tbl}: {RED}{cname} ← MISSING{RESET}")
            problems.append(msg)

    # ── 4. alembic_version varchar(32) length check ──────────────────────────
    print(f"\n{BOLD}  alembic_version column length{RESET}")
    if "alembic_version" in existing_tables:
        av_cols = _cols("alembic_version")
        if "version_num" in av_cols:
            col_type = str(av_cols["version_num"]["type"])
            print(f"  {INFO}  version_num type: {col_type}")
            # varchar(32) can silently truncate long revision IDs
            if "32" in col_type:
                print(
                    f"  {WARN}  varchar(32) detected — ensure all revision IDs are ≤ 32 chars"
                )

    return problems


# ── Main ──────────────────────────────────────────────────────────────────────

def _summary(problems: list[str]) -> None:
    _section("Summary")
    if not problems:
        print(f"  {OK} {BOLD}All checks passed — schema looks healthy{RESET}")
    else:
        print(f"  {FAIL} {BOLD}{RED}{len(problems)} problem(s) found:{RESET}")
        for i, p in enumerate(problems, 1):
            print(f"    {i}. {p}")
        print()
        print(
            f"  {WARN} Run  {BOLD}python db_schema_check.py upgrade{RESET}  "
            "to apply pending migrations."
        )
        print(
            f"  {WARN} Run  {BOLD}python db_schema_check.py fix-version{RESET}  "
            "if multiple alembic_version rows were reported."
        )


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd not in {"check", "upgrade", "verify", "all", "fix-version"}:
        print(__doc__)
        sys.exit(1)

    engine = create_engine(settings.database_url)

    if cmd == "upgrade":
        cmd_upgrade()
        return

    if cmd == "fix-version":
        cmd_fix_version(engine)
        return

    problems: list[str] = []

    if cmd in {"check", "all"}:
        problems += cmd_check(engine)

    if cmd in {"verify", "all"}:
        problems += cmd_verify(engine)

    _summary(problems)
    sys.exit(0 if not problems else 2)


if __name__ == "__main__":
    main()
