import os
import time
import shutil
import logging
import subprocess
import threading
import random
from typing import Dict, Optional, Tuple


class AutoUpdater:
    """
    Periodically performs a safe, fast-forward-only update on the repo.
    - Pulls from one directory above this file by default.
    - Auto-detects current branch and its upstream (remote/branch).
    - Serializes pulls (prevents overlap with UI-triggered pulls).
    - Handles shallow clones and detached HEAD.
    - Best-effort fix for Git 'dubious ownership' warnings.
    """

    def __init__(self, settings: Dict, stop_event: threading.Event) -> None:
        self._settings = settings
        self._stop = stop_event
        self._thread: Optional[threading.Thread] = None
        self._pull_lock = threading.Lock()
        self.last_pull: Optional[Dict[str, object]] = None

    # Public API ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def pull_now(self) -> Tuple[bool, str]:
        au = self._cfg()
        return self._git_pull(
            repo_path=au.get("repo_path"),
            remote=au.get("remote"),
            branch=au.get("branch"),
        )

    # Internal ----------------------------------------------------------------

    def _cfg(self) -> Dict:
        au = self._settings.setdefault("autoupdate", {})
        au.setdefault("enabled", True)
        au.setdefault("hour", 4)
        au.setdefault("minute", 0)
        # Pull one dir up from this file (repo root)
        au.setdefault("repo_path", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        # If not set, these will be auto-detected from upstream
        au.setdefault("remote", None)
        au.setdefault("branch", None)
        # Optional: perform a shallow-friendly fetch (no full history)
        au.setdefault("shallow_ok", True)
        return au

    def _worker(self) -> None:
        # Add a small random jitter so multiple devices do not all pull at the same second
        initial_jitter = random.uniform(5.0, 60.0)
        if self._stop.wait(timeout=initial_jitter):
            return

        while not self._stop.is_set():
            au = self._cfg()
            if not au.get("enabled", True):
                if self._stop.wait(timeout=3600):
                    return
                continue

            next_ts = self._compute_next_run_ts(au.get("hour", 4), au.get("minute", 0))
            while True:
                if self._stop.is_set():
                    return
                remaining = next_ts - time.time()
                if remaining <= 0:
                    break
                self._stop.wait(timeout=min(remaining, 60))

            try:
                self.pull_now()
            except Exception:
                logging.exception("[AutoUpdate] unexpected error during scheduled pull")

    @staticmethod
    def _compute_next_run_ts(hour: int, minute: int) -> float:
        now = time.localtime()
        target = time.struct_time((
            now.tm_year, now.tm_mon, now.tm_mday, int(hour), int(minute), 0,
            now.tm_wday, now.tm_yday, now.tm_isdst
        ))
        now_ts = time.time()
        target_ts = time.mktime(target)
        if target_ts <= now_ts:
            target_ts += 86400
        return target_ts

    # Git helpers -------------------------------------------------------------

    def _git_pull(
        self,
        repo_path: Optional[str],
        remote: Optional[str],
        branch: Optional[str],
        timeout: int = 180
    ) -> Tuple[bool, str]:
        with self._pull_lock:
            try:
                repo_path = repo_path or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

                if not shutil.which("git"):
                    msg = "git executable not found in PATH"
                    logging.warning("[AutoUpdate] %s", msg)
                    self._record(False, msg)
                    return False, msg

                if not os.path.isdir(os.path.join(repo_path, ".git")):
                    msg = f"Not a git repository: {repo_path}"
                    logging.info("[AutoUpdate] %s", msg)
                    self._record(False, msg)
                    return False, msg

                env = self._git_env()

                # Auto-detect current branch if missing
                if not branch:
                    branch = self._current_branch(repo_path, env, timeout)

                # Try to detect upstream (remote/branch) if not explicitly provided
                if not remote or not branch:
                    upstream = self._upstream_ref(repo_path, env, timeout)
                    if upstream:
                        detected_remote, detected_branch = upstream
                        if not remote:
                            remote = detected_remote
                        if not branch:
                            branch = detected_branch

                # If still no remote (no upstream configured), default to origin
                if not remote:
                    remote = "origin"

                # Always fetch first (friendly to shallow clones)
                self._fetch(repo_path, remote, env, timeout)

                # Fast-forward-only pull. If we know remote+branch, use them.
                cmd = ["git", "-C", repo_path, "pull", "--ff-only"]
                if remote and branch:
                    cmd += [remote, branch]

                ok, out = self._run_git(cmd, env, timeout)
                if not ok and self._looks_like_dubious_ownership(out):
                    # Best-effort fix for 'dubious ownership' and retry once
                    self._mark_repo_safe(repo_path, env, timeout)
                    ok, out = self._run_git(cmd, env, timeout)

                # If still failing with non-ff scenario, report clearly
                if not ok and self._looks_like_non_ff(out):
                    out += "\nHint: Non fast-forward. Rebase or reset may be required on the device."

                logging.info("[AutoUpdate] git pull %s.\n%s", "succeeded" if ok else "failed", out)
                self._record(ok, out)
                return ok, out

            except subprocess.TimeoutExpired:
                msg = "git pull timed out"
                logging.error("[AutoUpdate] %s", msg)
                self._record(False, msg)
                return False, msg
            except Exception as e:
                msg = f"git pull error: {e}"
                logging.exception("[AutoUpdate] %s", msg)
                self._record(False, msg)
                return False, msg

    def _git_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        # Ensure HOME exists for git config and credential helpers
        try_home = "/home/pi"
        if os.path.isdir(try_home):
            env.setdefault("HOME", try_home)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        return env

    def _run_git(self, cmd, env, timeout) -> Tuple[bool, str]:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, env=env)
        out = (res.stdout or "") + (res.stderr or "")
        return res.returncode == 0, out.strip()

    def _current_branch(self, repo_path: str, env: Dict[str, str], timeout: int) -> Optional[str]:
        # If detached HEAD, this returns "HEAD"
        ok, out = self._run_git(["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"], env, timeout)
        if ok:
            br = out.strip()
            return None if br == "HEAD" else br
        return None

    def _upstream_ref(self, repo_path: str, env: Dict[str, str], timeout: int) -> Optional[Tuple[str, str]]:
        # Returns ("origin", "main") for upstream origin/main, if configured
        ok, out = self._run_git(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            env, timeout
        )
        if ok and out and "/" in out:
            remote, branch = out.split("/", 1)
            return remote.strip(), branch.strip()
        return None

    def _fetch(self, repo_path: str, remote: str, env: Dict[str, str], timeout: int) -> None:
        # Shallow-friendly fetch; if repo is shallow, update shallow history
        shallow = os.path.isfile(os.path.join(repo_path, ".git", "shallow"))
        if shallow:
            self._run_git(["git", "-C", repo_path, "fetch", "--prune", remote, "--depth=1", "--update-shallow"], env, timeout)
        else:
            self._run_git(["git", "-C", repo_path, "fetch", "--prune", remote], env, timeout)

    def _mark_repo_safe(self, repo_path: str, env: Dict[str, str], timeout: int) -> None:
        # git safe.directory for ownership warnings
        self._run_git(["git", "config", "--global", "--add", "safe.directory", repo_path], env, timeout)

    @staticmethod
    def _looks_like_dubious_ownership(out: str) -> bool:
        if not out:
            return False
        o = out.lower()
        return "detected dubious ownership" in o or "safe.directory" in o

    @staticmethod
    def _looks_like_non_ff(out: str) -> bool:
        if not out:
            return False
        o = out.lower()
        return "non-fast-forward" in o or "fatal: not possible to fast-forward" in o

    def _record(self, ok: bool, msg: str) -> None:
        self.last_pull = {"ok": ok, "ts": time.time(), "msg": msg}
