# Runtime And Verification

- For Python work, use only the project venv at `env/`.
- Prefer `env/bin/python` and `env/bin/pip` in commands, examples, and one-off scripts.
- If `env/` is missing, create it with `python -m venv env` from the repo root.
- Install project dependencies into `env/`; do not install this project's packages globally.
- Preferred one-time bootstrap: `env/bin/pip install -e . pytest ruff`
- Claude Code project settings prepend the repo venv to `PATH` at session start, including worktree sessions. Treat that as the default runtime for Python commands.
- Main Python commands:
  - `env/bin/python app.py`
  - `env/bin/python app.py --headless`
  - `env/bin/python -m pytest`
  - `env/bin/python -m ruff check .`
  - `env/bin/python -m ruff format .`
- Frontend commands:
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
- If `pytest` or `ruff` are missing from `env/`, install them into `env/` before using them there.
