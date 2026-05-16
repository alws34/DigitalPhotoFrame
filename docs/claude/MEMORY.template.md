# DigitalPhotoFrame Claude Memory Seed

Use this as a seed for Claude Code's real auto-memory entrypoint for this repo.

Actual location, per the Claude Code docs:

- `~/.claude/projects/<project>/memory/MEMORY.md`

Suggested contents:

- Use only the project venv at `env/` for Python work.
- If `env/` is missing, create it from the repo root with `python -m venv env`.
- Preferred bootstrap command: `env/bin/pip install -e . pytest ruff`.
- Prefer `env/bin/python` and `env/bin/pip`; do not rely on global Python tooling for this repo.
- Claude project settings prepend the repo venv to `PATH` at session start, including Claude worktree sessions.
- `photoframe_settings.json` is gitignored and copied into Claude worktrees via `.worktreeinclude`.
- This project is a long-running photo-frame app; reliability and fail-soft behavior matter as much as correctness.
- `FrameServer/` and overlay code are performance-sensitive; avoid blocking I/O and unnecessary per-frame work.
- Flask serves the built React app from `frontend/dist`; rebuild the frontend after React UI changes.
- Settings changes must be end-to-end across JSON defaults, persistence, backend routes, and UI/editor layers.
- If Claude Code cache-resume behavior looks unhealthy, see `docs/claude/cache-fix.md`.
