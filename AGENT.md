# Agent Guide

This repository is a private AI photo library with a FastAPI backend, a React/Vite frontend, a Python worker, PostgreSQL, pgvector, and optional local llama.cpp services. The current default deployment path is macOS native scripts, not Docker.

## First Read

- `README.md` is the source of truth for current capabilities, local startup, and known boundaries.
- `Runbook/README.md` and `Runbook/release-checklist.md` cover operational checks and release gates.
- `Design-document/README.md` links architecture and domain notes, but older design prompts may describe target state rather than current implementation.

## Project Layout

- `apps/api`: FastAPI app, SQLAlchemy models, Alembic migrations, backend tests.
- `apps/web`: React 18 + Vite + TypeScript frontend, Tailwind styles, Vitest tests.
- `apps/worker`: background worker process that shares API code and dependencies.
- `scripts`: macOS native bootstrap, service control, DB schema, reset, and release-preflight helpers.
- `Runbook`: migration, backfill, release, and troubleshooting procedures.
- `Design-document`: architecture, People/Search domain design, and planning material.

## Runtime Model

- Managed services are `postgres`, `ai`, `embed`, `api`, `worker`, and `web`.
- Use `./scripts/dev-up.sh` for the core development path.
- Use `./scripts/svc.sh start` for the full local stack, subject to `.env` and model configuration.
- `./scripts/svc.sh start api` and `restart api` run Alembic migrations before starting the API.
- Direct `uvicorn app.main:app` startup only performs schema self-checks; it does not run migrations.
- Keep machine-specific values in `.env` / profile-specific env files. Do not hard-code local paths, ports, model URLs, project IDs, or prompts in code.

## Common Commands

From the repository root:

```bash
./scripts/bootstrap-macos.sh
./scripts/dev-up.sh
./scripts/svc.sh status
./scripts/svc.sh logs api
./scripts/init-db.sh
./scripts/db-schema.sh check
./scripts/db-schema.sh verify
./scripts/release-preflight.sh
```

Backend:

```bash
cd apps/api
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m pytest tests/test_project_photos_query_service.py -q
```

Frontend:

```bash
cd apps/web
npm test
npm run typecheck
npm run build
```

## Backend Conventions

- `apps/api/app/main.py` mounts project-scoped routers and applies auth, request context logging, runtime debug config, and startup schema checks.
- Prefer router code that handles HTTP concerns only: parameter parsing, auth/project scope, and HTTP error mapping.
- Put writes and workflow orchestration in application services.
- Put complex reads in query services.
- Reuse existing repositories, services, schemas, and value objects before adding new abstractions.
- New or changed project APIs must validate `project_id` scope.
- Worker task handling must carry and strictly use `project_id`.
- New config must be explicit, documented, and covered by managed-key checks when API-owned.
- Missing required config should fail loudly instead of falling back to hidden defaults.
- Health/status APIs must not leak secrets; return state and actionable hints only.

## Database And Migrations

- Use Alembic migrations under `apps/api/alembic/versions` for schema changes.
- Keep models, schemas, services, and tests aligned with migrations.
- Use `./scripts/init-db.sh` or `./scripts/db-schema.sh upgrade` to upgrade local DB state.
- Use `./scripts/db-schema.sh check` and `verify` after migration-sensitive changes.
- If startup fails with schema drift, resolve the migration/model mismatch rather than weakening startup checks.

## Search, People, And Tasks

- Search is organized under `apps/api/app/services/search`; preserve the separation between recall, planning, fusion, hydration, debug tracing, and policy.
- People Recognition has a working human-correction loop. Do not overwrite confirmed human assignments during automatic clustering/rematch work.
- Project tasks are the shared long-running workflow surface. Prefer extending `ProjectTask` flows over adding one-off job status mechanisms.
- Keep capability maturity labels in UI and docs aligned: `稳定`, `实验`, `待收敛`.

## Frontend Conventions

- The app entry is `apps/web/src/App.tsx`; routes cover Photos, Search, Tags, Tasks, Settings, AI settings, People, People Review, and Login.
- API access lives under `apps/web/src/api`; prefer typed API helpers and query keys over ad hoc fetches in components.
- Use existing hooks and view-model helpers before adding page-local data orchestration.
- Keep large pages/components moving toward smaller hooks, toolbars, panels, and focused components.
- The UI uses Tailwind and existing design tokens/classes; match the current quiet operational product style.
- Use `lucide-react` icons where appropriate.
- For frontend changes, run targeted Vitest tests plus `npm run typecheck`; run `npm run build` for broader UI/API type changes.

## Testing Expectations

- For narrow backend service changes, run the closest pytest file.
- For API/project isolation, task, People, Search, auth, or runtime settings changes, run the relevant backend regression tests listed in `scripts/release-preflight.sh`.
- For frontend components/hooks/pages, run the closest Vitest file and `npm run typecheck`.
- Before release-sensitive changes, run `./scripts/release-preflight.sh`.

## Safety Rules

- The original photo library is read-only from the application's perspective. Do not modify, move, or delete user photos.
- Generated thumbnails, AI analysis, indexes, and task state belong in app-managed storage/database locations.
- Avoid adding legacy endpoints or new unscoped project behavior.
- Do not treat Docker files as the primary runtime path unless the task specifically asks for Docker compatibility.
- Preserve unrelated user changes in the working tree. This repository often has active edits.
