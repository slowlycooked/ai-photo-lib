# Project Guardrails

## Storage layout and approval

- Do not change storage locations, folder structure, runtime paths, mount points, or database path references without Martin's explicit approval for the exact proposed change.
- Before proposing a storage-path change, explain the cause, affected paths, migration impact, rollback plan, and expected disk usage; wait for approval before editing configuration or data.
- Thumbnail files must remain on the NAS under `/Users/martinclaw/nas/ai-photo-data/thumbs`. Do not place thumbnail caches on the Mac mini's local disk unless Martin explicitly approves that exception.
- An interactive shell or SSH session being able to write the NAS path does not prove that a `launchd` service can write it. Diagnose the actual service process identity, execution context, mount visibility, macOS privacy permissions, and logs before changing storage design.
- Never use a storage relocation as an implicit workaround for a permissions failure.
