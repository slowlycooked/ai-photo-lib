---
name: db-schema-drift-guard
description: 'Prevent and fix database schema drift after code changes. Use when API or worker fails with missing table or column, alembic version looks correct but runtime SQL fails, or after pull/rebase/release to verify code-schema alignment.'
argument-hint: 'Service path and symptom, for example: apps/api, search returns internal error, relation does not exist'
user-invocable: true
disable-model-invocation: false
---

# Database Schema Drift Guard

## Outcome
This skill verifies that code migrations and the real database schema are aligned, repairs common drift safely, and confirms runtime paths no longer fail.

## When to Use
- Internal error appears after backend code upgrade.
- Log contains relation does not exist, column does not exist, current transaction is aborted, or InFailedSqlTransaction.
- Alembic current shows head but runtime still reports missing table or column.
- After merge or deploy, you want a fast schema consistency gate.

## Inputs
- Backend service directory, usually apps/api.
- Error symptom from logs or API response.
- Target feature path, for example search, tasks, ai, face.

## Procedure
1. Capture the exact runtime failure
- Read recent API logs and stack trace.
- Extract failing SQL object names: table, column, index.
- Identify first error in chain, not only the final 500.

2. Confirm migration state and physical schema
- Run alembic current in backend directory.
- Query database catalog to verify object existence.
- Compare expected objects from migration files with actual objects in database.

3. Branch by mismatch type
- Case A: alembic behind head.
  Action: run alembic upgrade head.
- Case B: alembic at head but object missing.
  Action: treat as schema drift.
  Action: stamp to previous revision that should create the missing object, then upgrade head.
- Case C: object exists but app still fails.
  Action: check transaction poisoning pattern, ensure exception path rolls back session before next query.
- Case D: migration exists but is not idempotent for historical data.
  Action: add guarded SQL in migration or startup checks, then test on representative database.

4. Validate runtime behavior
- Re-check alembic current.
- Re-check catalog object existence.
- Re-run the failing API or workflow.
- Confirm original error signature is gone from logs.

5. Add regression guard
- Add or update test that reproduces the failure mode.
- Add runbook note with command pair used to recover.
- If startup schema self-check exists, include the newly required object.

## Safe Repair Rules
- Prefer migration-based recovery over manual one-off SQL.
- Keep project isolation intact for all queries and fixes.
- Do not add hidden fallback defaults to bypass missing schema.
- Fail explicitly when required schema is missing.

## Completion Checks
- Alembic revision matches intended head.
- Missing object now exists in catalog.
- Target endpoint or job path no longer returns internal error.
- No new schema-related errors in recent logs.
- At least one automated or documented regression check is added.

## Suggested Command Sequence
1. Change to backend folder.
2. Run alembic current.
3. Verify missing object using catalog query.
4. If drift, stamp to prior revision and upgrade head.
5. Verify object exists.
6. Replay failing request and inspect logs.

## Example Prompts
- Use db schema drift guard for apps/api: search returns internal error and log says relation project_query_planner_settings does not exist.
- Verify post-upgrade schema alignment for worker task tables before release.
- Diagnose missing column error after pull and repair with migration-safe steps.

## Related Next Customizations
- Create a release preflight prompt that runs schema alignment checks automatically.
- Add a hook to block release when alembic head and catalog checks are inconsistent.
- Add a project runbook template for common drift signatures and approved repair commands.
