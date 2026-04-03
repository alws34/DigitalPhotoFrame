#!/usr/bin/env bash
set -euo pipefail

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd -P)}"
repo_root="$project_dir"

if git -C "$project_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  common_dir="$(git -C "$project_dir" rev-parse --path-format=absolute --git-common-dir)"
  candidate_root="$(cd "$common_dir/.." && pwd -P)"
  if [ -d "$candidate_root" ]; then
    repo_root="$candidate_root"
  fi
fi

venv_dir="$repo_root/env"

if [ -x "$venv_dir/bin/python" ]; then
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    {
      echo "export DIGITALPHOTOFRAME_REPO_ROOT=\"$repo_root\""
      echo "export DIGITALPHOTOFRAME_VENV=\"$venv_dir\""
      echo "export VIRTUAL_ENV=\"$venv_dir\""
      echo "export PATH=\"$venv_dir/bin:\$PATH\""
      echo "unset PYTHONHOME"
    } >> "$CLAUDE_ENV_FILE"
  fi

  cat <<EOF
Using DigitalPhotoFrame virtualenv at $venv_dir.
Bare python/pip commands in this Claude session now resolve from that venv first.
EOF
  exit 0
fi

cat <<EOF
DigitalPhotoFrame venv not found at $venv_dir.
Create it from the main repo root with:
  python -m venv env
  env/bin/pip install -e . pytest ruff
EOF
