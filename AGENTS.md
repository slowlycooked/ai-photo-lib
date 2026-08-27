# Project Guardrails

## Storage layout and approval

- Do not change storage locations, folder structure, runtime paths, mount points, or database path references without Martin's explicit approval for the exact proposed change.
- Before proposing a storage-path change, explain the cause, affected paths, migration impact, rollback plan, and expected disk usage; wait for approval before editing configuration or data.
- Thumbnail files must remain on the NAS under `/Users/martinclaw/nas/ai-photo-data/thumbs`. Do not place thumbnail caches on the Mac mini's local disk unless Martin explicitly approves that exception.
- An interactive shell or SSH session being able to write the NAS path does not prove that a `launchd` service can write it. Diagnose the actual service process identity, execution context, mount visibility, macOS privacy permissions, and logs before changing storage design.
- Never use a storage relocation as an implicit workaround for a permissions failure.

## Runtime service management and approval

- The approved macOS runtime mode for this project is `scripts/svc.sh`, started from Martin's interactive iTerm2 login session. This project was explicitly rolled back from `launchd` to `svc.sh`; do not reverse or bypass that decision.
- Do not create or use LaunchAgents, LaunchDaemons, `launchctl submit`, or temporary `*-codex-*-recovery` / `*-recovery` jobs for any project service.
- Do not start, stop, restart, replace, recover, or change the ownership or execution context of any running service without Martin's explicit approval for the exact service and exact action. A report that a service is unavailable is not permission to recover it automatically.
- When a runtime problem is reported, perform read-only diagnosis first, report the actual process identity, parent/coalition, launch context, port owner, mount visibility, and relevant logs, then present the proposed commands and wait for approval before changing runtime state.
- A process command containing `scripts/ai-photo-runner.sh`, a matching `.run/*.pid` file, or a successful `svc.sh status` result does not by itself prove that the service is in approved `svc.sh` mode. Check for submitted launchd jobs and the real macOS execution context before making that claim.
- Never introduce a temporary recovery mechanism merely to make a service stay alive. If the approved `svc.sh` process cannot remain running, stop and ask Martin how to proceed.
