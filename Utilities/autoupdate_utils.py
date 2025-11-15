import os, time, shutil, logging, subprocess, threading, random, re
from datetime import datetime
from typing import Optional, Tuple, Dict, Callable, List


class AutoUpdater:
    """
    Tag-gated auto-updater.

    Behavior:
      - Only updates when a newer *remote* semver tag exists (e.g., v1.2.3 or V1.2.3).
      - Backs up all config-related JSON files before switching tags and restores
        them after update to preserve user settings, including custom configs.
      - Keeps the old 'git pull' path as a fallback if no tags are found.
      - Optionally restarts your service after a successful update.

    Public:
      start() -> None
      pull_now() -> Tuple[bool, str]
    """

    def __init__(
        self,
        stop_event: threading.Event,
        interval_sec: int = 1800,
        on_update_available: Optional[Callable[[int], None]] = None,
        on_updated: Optional[Callable[[str], None]] = None,
        restart_service_async: Optional[Callable[[], None]] = None,
        min_restart_interval_sec: int = 900,
        auto_restart_on_update: bool = True,
    ):
        self._stop = stop_event
        self._thread: Optional[threading.Thread] = None
        self._pull_lock = threading.Lock()
        self._interval = int(interval_sec)
        self.last_pull: Optional[Dict[str, object]] = None

        self._on_update_available = on_update_available
        self._on_updated = on_updated
        self._restart_service_async = restart_service_async
        self._auto_restart_on_update = bool(auto_restart_on_update)
        self._min_restart_interval = int(min_restart_interval_sec)
        self._last_restart_ts = 0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def pull_now(self) -> Tuple[bool, str]:
        """
        Manual update trigger used by the Settings dialog button.
        Only updates when a newer remote tag exists. If no tag information
        is available, falls back to branch fast-forward pull.
        """
        repo = self._find_repo_root()
        if not repo:
            msg = "Repository root not found"
            self._record(False, msg)
            return False, msg

        ok, changed, out = self._update_to_newer_tag(repo_path=repo, timeout=180)
        if not ok and "no tags" in out.lower():
            # Optional fallback to branch pull if tags are not used
            ok, out = self._git_pull(repo_path=repo)

        # Optional restart if code actually changed
        if ok and changed and self._auto_restart_on_update and self._restart_service_async:
            try:
                threading.Thread(target=self._restart_service_async, daemon=True).start()
            except Exception:
                logging.exception("[AutoUpdate] restart hook failed (manual)")

        return ok, out

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------
    def _worker(self) -> None:
        # random initial delay to de-synchronize many devices
        if self._stop.wait(timeout=random.uniform(5.0, 60.0)):
            return

        while not self._stop.is_set():
            try:
                repo = self._find_repo_root()
                if repo and shutil.which("git"):
                    env = self._git_env()

                    # Preferred path: tag-based update
                    ok, changed, out = self._update_to_newer_tag(repo_path=repo, timeout=180)
                    if self._on_updated and out:
                        try:
                            self._on_updated(out)
                        except Exception:
                            pass

                    # If tags are not present at all, use branch fast-forward fallback
                    if not ok and "no tags" in out.lower():
                        upstream = self._upstream_ref(repo, env, 10)
                        if upstream:
                            ahead, behind = self._behind_counts(repo, env, 10)
                            if behind > 0 and self._on_update_available:
                                try:
                                    self._on_update_available(behind)
                                except Exception:
                                    pass
                        ok2, out2 = self._git_pull(repo, 180)
                        if self._on_updated and out2:
                            try:
                                self._on_updated(out2)
                            except Exception:
                                pass
                        changed = ok2 and self._pull_changed(out2)

                    # Restart if code actually changed
                    if changed and self._auto_restart_on_update and self._restart_service_async:
                        now = time.time()
                        if now - self._last_restart_ts >= self._min_restart_interval:
                            self._last_restart_ts = now
                            try:
                                threading.Thread(target=self._restart_service_async, daemon=True).start()
                            except Exception:
                                logging.exception("[AutoUpdate] restart hook failed")
                else:
                    self._record(False, "git not found or repo not detected")
            except Exception:
                logging.exception("[AutoUpdate] unexpected error during scheduled pull")

            # sleep in 1s chunks so we can stop promptly
            for _ in range(self._interval):
                if self._stop.is_set():
                    return
                time.sleep(1)

    # ------------------------------------------------------------------
    # Tag-based update (now with multi-config backup/restore)
    # ------------------------------------------------------------------
    def _update_to_newer_tag(self, repo_path: str, timeout: int = 180) -> Tuple[bool, bool, str]:
        """
        Returns (ok, changed, message).
        ok      -> the operation executed without internal error (even if no update was needed)
        changed -> code actually changed (we switched to a newer tag)
        message -> details (includes backup path when applicable)
        """
        env = self._git_env()
        if not shutil.which("git"):
            msg = "git not found"
            self._record(False, msg)
            return False, False, msg

        if not repo_path or not os.path.isdir(os.path.join(repo_path, ".git")):
            msg = f"Not a git repository: {repo_path}"
            self._record(False, msg)
            return False, False, msg

        # Determine remote and fetch tags
        upstream = self._upstream_ref(repo_path, env, timeout)
        remote = upstream[0] if upstream else "origin"
        self._fetch(repo_path, remote, env, timeout)
        # Make sure we have all tags
        self._run_git(["git", "-C", repo_path, "fetch", "--tags", "--prune", remote], env, timeout)

        remote_tags = self._list_remote_semver_tags(remote, env, timeout)

        if not remote_tags:
            msg = "No tags found on remote; skipping tag-based update"
            self._record(True, msg)
            # ok=False triggers branch-pull fallback in callers
            return False, False, msg

        latest_remote_tag = self._max_tag(remote_tags)
        current_tag = self._current_semver_tag(repo_path, env, timeout)
        # If HEAD is not at a tag, assume version 0.0.0 so we jump forward once
        current_ver = self._parse_semver(current_tag) if current_tag else (0, 0, 0)

        if self._parse_semver(latest_remote_tag) <= current_ver:
            msg = f"Already at latest tag ({current_tag or 'unknown'}); no update needed"
            self._record(True, msg)
            return True, False, msg

        # Newer tag exists -> backup all configs, checkout, restore configs
        backup_root = self._backup_settings(repo_path)
        changed, msg_checkout = self._checkout_tag(repo_path, latest_remote_tag, env, timeout)

        # Restore all configs (best-effort)
        self._restore_settings(repo_path, backup_root)

        msg = f"Updated to tag {latest_remote_tag}.\n{msg_checkout}"
        if backup_root:
            msg += f"\nSettings backup root: {backup_root}"

        self._record(changed, msg)
        return True, changed, msg

    def _checkout_tag(self, repo_path: str, tag: str, env, timeout: int) -> Tuple[bool, str]:
        """
        Switch to the provided tag by creating/updating a local 'autoupdate' branch.
        This avoids detached HEAD and makes future updates simpler.
        """
        # Resolve tag ref to a commit
        ok_res, out_res = self._run_git(
            ["git", "-C", repo_path, "rev-list", "-n", "1", f"refs/tags/{tag}"],
            env,
            timeout,
        )
        if not ok_res or not out_res:
            return False, f"Failed to resolve tag {tag}: {out_res}"

        # Create or reset 'autoupdate' branch to the tag
        cmd = ["git", "-C", repo_path, "checkout", "-B", "autoupdate", f"refs/tags/{tag}"]
        ok_co, out_co = self._run_git(cmd, env, timeout)
        if not ok_co:
            return False, f"Checkout failed: {out_co}"

        return True, "Checkout succeeded"

    def _list_remote_semver_tags(self, remote: str, env, timeout: int) -> List[str]:
        ok, out = self._run_git(["git", "ls-remote", "--tags", remote], env, timeout)
        if not ok or not out:
            return []
        tags: List[str] = []
        for line in out.splitlines():
            try:
                ref = line.split("\t", 1)[1]
            except Exception:
                continue
            if ref.endswith("^{}"):
                ref = ref[:-3]
            name = ref.rsplit("/", 1)[-1]
            if self._is_semver_tag(name):
                tags.append(name)
        return tags

    def _list_local_semver_tags(self, repo_path: str, env, timeout: int) -> List[str]:
        ok, out = self._run_git(["git", "-C", repo_path, "tag", "--list"], env, timeout)
        if not ok or not out:
            return []
        return [t.strip() for t in out.splitlines() if self._is_semver_tag(t.strip())]

    def _current_semver_tag(self, repo_path: str, env, timeout: int) -> Optional[str]:
        # Prefer exact tag(s) pointing at HEAD
        ok, out = self._run_git(["git", "-C", repo_path, "tag", "--points-at", "HEAD"], env, timeout)
        if ok and out:
            tags = [t.strip() for t in out.splitlines() if self._is_semver_tag(t.strip())]
            if tags:
                return self._max_tag(tags)
        # Fallback to describe
        ok, out = self._run_git(["git", "-C", repo_path, "describe", "--tags", "--abbrev=0"], env, timeout)
        if ok and out and self._is_semver_tag(out.strip()):
            return out.strip()
        return None

    @staticmethod
    def _is_semver_tag(tag: str) -> bool:
        # Accept v1.2.3, V1.2.3, 1.2.3
        return re.fullmatch(r"[Vv]?\d+\.\d+\.\d+", tag) is not None

    @staticmethod
    def _parse_semver(tag: str) -> Tuple[int, int, int]:
        m = re.fullmatch(r"[Vv]?(\d+)\.(\d+)\.(\d+)", tag or "")
        if not m:
            return (0, 0, 0)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    def _max_tag(self, tags: List[str]) -> str:
        return max(tags, key=lambda t: self._parse_semver(t))

    # ------------------------------------------------------------------
    # Settings backup / restore
    # ------------------------------------------------------------------
    def _settings_candidates(self, repo_path: str) -> List[str]:
        """
        Legacy helper: known main settings filenames in repo root.
        Kept for compatibility; main backup now uses _list_config_files().
        """
        names = ["photoframe_settings.json", "settings.json", "Settings.json"]
        return [os.path.join(repo_path, n) for n in names]

    def _find_settings_file(self, repo_path: str) -> Optional[str]:
        for p in self._settings_candidates(repo_path):
            if os.path.isfile(p):
                return p
        return None

    def _list_config_files(self, repo_path: str) -> List[str]:
        """
        Discover all config JSON files that must be preserved.

        Rules:
          - Only *.json files.
          - Filename (without path) must contain 'settings' or 'config' (case-insensitive).
          - Skip .git, virtualenvs, caches, and the .autoupdate_backups folder.
        """
        results: List[str] = []
        skip_dirs = {
            ".git",
            ".autoupdate_backups",
            "__pycache__",
            "env",
            ".env",
            ".venv",
            "venv",
            ".mypy_cache",
            ".pytest_cache",
            "node_modules",
        }

        for root, dirs, files in os.walk(repo_path):
            # prune dirs in-place to avoid descending into them
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for fn in files:
                if not fn.lower().endswith(".json"):
                    continue
                base = fn.lower()
                if "settings" not in base and "config" not in base:
                    continue
                full = os.path.join(root, fn)
                results.append(os.path.abspath(full))

        # Ensure deterministic order, but do not rely on it for correctness
        return sorted(set(results))

    def _backup_settings(self, repo_path: str) -> Optional[str]:
        """
        Backup all config-related JSON files into .autoupdate_backups/<ts>/.
        Returns the backup root directory (or None if nothing to back up).
        """
        cfg_files = self._list_config_files(repo_path)
        if not cfg_files:
            logging.info("[AutoUpdate] No config JSON files found to backup.")
            return None

        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        backup_root = os.path.join(repo_path, ".autoupdate_backups", ts)

        try:
            for src in cfg_files:
                rel = os.path.relpath(src, repo_path)
                dst = os.path.join(backup_root, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            logging.info("[AutoUpdate] Backed up %d config file(s) under %s", len(cfg_files), backup_root)
            return backup_root
        except Exception:
            logging.exception("[AutoUpdate] Failed to backup settings")
            return None

    def _restore_settings(self, repo_path: str, backup_path: Optional[str]) -> None:
        """
        Restore config files after update.

        If backup_path is a directory, treat it as .autoupdate_backups/<ts>/.
        If backup_path is a file, fall back to the old single-file flow.
        """
        if not backup_path:
            return

        try:
            # New multi-file backup format: directory
            if os.path.isdir(backup_path):
                for root, _, files in os.walk(backup_path):
                    for fn in files:
                        src = os.path.join(root, fn)
                        rel = os.path.relpath(src, backup_path)
                        dst = os.path.join(repo_path, rel)
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                logging.info("[AutoUpdate] Restored settings from %s", backup_path)
                return

            # Legacy single-file backup: treat backup_path as a single JSON
            if os.path.isfile(backup_path):
                dest = (
                    self._find_settings_file(repo_path)
                    or os.path.join(repo_path, os.path.basename(backup_path).split(".bak-")[0])
                )
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(backup_path, dest)
                logging.info("[AutoUpdate] Settings restored from %s", backup_path)
        except Exception:
            logging.exception("[AutoUpdate] Failed to restore settings from %s", backup_path)

    # ------------------------------------------------------------------
    # Repo detection
    # ------------------------------------------------------------------
    def _find_repo_root(self) -> Optional[str]:
        here = os.path.abspath(os.path.dirname(__file__))
        env = self._git_env()
        ok, out = self._run_git(["git", "-C", here, "rev-parse", "--show-toplevel"], env, 10)
        if ok and out:
            return out.strip()
        # fallback: walk up looking for .git
        cur = here
        while True:
            if os.path.isdir(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return None

    # ------------------------------------------------------------------
    # Git plumbing
    # ------------------------------------------------------------------
    def _git_pull(self, repo_path: Optional[str], timeout: int = 180) -> Tuple[bool, str]:
        with self._pull_lock:
            try:
                if not shutil.which("git"):
                    msg = "git not found"
                    self._record(False, msg)
                    return False, msg
                if not repo_path or not os.path.isdir(os.path.join(repo_path, ".git")):
                    msg = f"Not a git repository: {repo_path}"
                    self._record(False, msg)
                    return False, msg

                env = self._git_env()
                branch = self._current_branch(repo_path, env, timeout)
                upstream = self._upstream_ref(repo_path, env, timeout)
                if upstream:
                    remote, upstream_branch = upstream
                else:
                    remote = "origin"
                    upstream_branch = branch

                # Always fetch first
                self._fetch(repo_path, remote, env, timeout)

                # ff-only pull
                cmd = ["git", "-C", repo_path, "pull", "--ff-only"]
                if remote and upstream_branch:
                    cmd += [remote, upstream_branch]

                ok, out = self._run_git(cmd, env, timeout)
                if not ok and self._looks_like_dubious_ownership(out):
                    self._mark_repo_safe(repo_path, env, timeout)
                    ok, out = self._run_git(cmd, env, timeout)

                if not ok and self._looks_like_non_ff(out):
                    out += "\nHint: Non fast-forward. Manual rebase/reset may be required."

                logging.info("[AutoUpdate] git pull %s.\n%s", "succeeded" if ok else "failed", out)
                self._record(ok, out)
                return ok, out
            except subprocess.TimeoutExpired:
                msg = "git pull timed out"
                self._record(False, msg)
                return False, msg
            except Exception as e:
                msg = f"git pull error: {e}"
                logging.exception("[AutoUpdate] %s", msg)
                self._record(False, msg)
                return False, msg

    def _git_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        for home in (os.environ.get("HOME"), "/home/pi", "/root"):
            if home and os.path.isdir(home):
                env.setdefault("HOME", home)
                break
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        return env

    def _run_git(self, cmd, env, timeout) -> Tuple[bool, str]:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = (res.stdout or "") + (res.stderr or "")
        return res.returncode == 0, out.strip()

    def _current_branch(self, repo_path: str, env, timeout: int) -> Optional[str]:
        ok, out = self._run_git(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            env,
            timeout,
        )
        if ok:
            br = out.strip()
            return None if br == "HEAD" else br
        return None

    def _upstream_ref(self, repo_path: str, env, timeout: int) -> Optional[Tuple[str, str]]:
        ok, out = self._run_git(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            env,
            timeout,
        )
        if ok and out and "/" in out:
            r, b = out.split("/", 1)
            return r.strip(), b.strip()
        return None

    def _fetch(self, repo_path: str, remote: str, env, timeout: int) -> None:
        shallow = os.path.isfile(os.path.join(repo_path, ".git", "shallow"))
        cmd = ["git", "-C", repo_path, "fetch", "--prune", remote]
        if shallow:
            cmd += ["--depth=1", "--update-shallow"]
        self._run_git(cmd, env, timeout)

    def _mark_repo_safe(self, repo_path: str, env, timeout: int) -> None:
        self._run_git(
            ["git", "config", "--global", "--add", "safe.directory", repo_path],
            env,
            timeout,
        )

    @staticmethod
    def _looks_like_dubious_ownership(out: str) -> bool:
        o = (out or "").lower()
        return "dubious ownership" in o or "safe.directory" in o

    @staticmethod
    def _looks_like_non_ff(out: str) -> bool:
        o = (out or "").lower()
        return "non-fast-forward" in o or "not possible to fast-forward" in o

    def _record(self, ok: bool, msg: str) -> None:
        self.last_pull = {"ok": ok, "ts": time.time(), "msg": msg}

    def _behind_counts(self, repo_path: str, env, timeout: int) -> Tuple[int, int]:
        ok, out = self._run_git(
            ["git", "-C", repo_path, "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            env,
            timeout,
        )
        if ok and out:
            try:
                ahead_str, behind_str = out.split()
                return int(ahead_str), int(behind_str)
            except Exception:
                pass
        return (0, 0)

    @staticmethod
    def _pull_changed(out: str) -> bool:
        o = (out or "")
        return ("Updating" in o) or ("Fast-forward" in o) or ("Fast-Forward" in o)
