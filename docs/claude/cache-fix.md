# Claude Code Cache Fix

Use this only for Claude Code itself, not for the DigitalPhotoFrame app runtime.

## What It Is

The `cc-cache-fix` project patches Claude Code to improve prompt-cache behavior around resume flows and cache TTL. The repo keeps the stock `claude` binary untouched and provides a separate `claude-patched` command instead.

Reference:

- `https://github.com/Rangizingo/cc-cache-fix/tree/main`

## When To Reach For It

- Resume sessions show unexpectedly low cache-read ratios.
- Cache health looks much worse after resume than during fresh sessions.
- You are investigating Claude Code cost/performance rather than app behavior.

## Repo Guidance

- Prefer documenting the workflow rather than assuming every contributor has the patch installed.
- If `claude-patched` is installed on a machine, it is reasonable to use it for long sessions in this repo.
- Do not make project scripts depend on `claude-patched`; keep it optional and developer-local.
- If you compare cache behavior, keep notes in Claude auto memory or local developer notes, not in app code.

## Install And Verify

From the upstream repo:

- Install with the platform script (`install.sh`, `install-mac.sh`, or `install-windows.ps1`).
- Verify with `type -a claude-patched`.
- Run the supplied cache test script against `claude-patched`.

The upstream README notes that the first run after patching may still look unhealthy because old short-TTL cache entries have not expired yet; rerun the test after that initial pass.
