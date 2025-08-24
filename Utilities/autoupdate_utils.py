import os, time, shutil, logging, subprocess, threading, random
from typing import Optional, Tuple, Dict, Callable

class AutoUpdater:
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

    # ---- public -------------------------------------------------
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def pull_now(self) -> Tuple[bool, str]:
        repo = self._find_repo_root()
        ok, out = self._git_pull(repo_path=repo)
        # Optional: also trigger restart here if a real update happened
        if ok and ("Updating" in out or "Fast-forward" in out or "Fast-Forward" in out):
            if self._auto_restart_on_update and self._restart_service_async:
                try:
                    threading.Thread(target=self._restart_service_async, daemon=True).start()
                except Exception:
                    logging.exception("[AutoUpdate] restart hook failed (manual)")
        return ok, out

    # ---- worker -------------------------------------------------
    def _worker(self) -> None:
        if self._stop.wait(timeout=random.uniform(5.0, 60.0)):
            return

        while not self._stop.is_set():
            try:
                repo = self._find_repo_root()
                if repo and shutil.which("git"):
                    env = self._git_env()
                    # Skip if no upstream configured
                    upstream = self._upstream_ref(repo, env, 10)
                    if upstream:
                        _r, _b = upstream
                        ahead, behind = self._behind_counts(repo, env, 10)

                        if behind > 0:
                            # Notify: new version available
                            if self._on_update_available:
                                try: self._on_update_available(behind)
                                except Exception: pass

                            # Pull
                            ok, out = self._git_pull(repo, 180)
                            if self._on_updated:
                                try: self._on_updated(out)
                                except Exception: pass

                            # Restart if pull succeeded & changed anything
                            if ok and ("Updating" in out or "Fast-forward" in out or "Fast-Forward" in out):
                                now = time.time()
                                if self._auto_restart_on_update and self._restart_service_async:
                                    # Debounce restarts
                                    if now - self._last_restart_ts >= self._min_restart_interval:
                                        self._last_restart_ts = now
                                        try:
                                            # do it in a thread so we return quickly
                                            threading.Thread(
                                                target=self._restart_service_async,
                                                daemon=True
                                            ).start()
                                        except Exception:
                                            logging.exception("[AutoUpdate] restart hook failed")
                    else:
                        # No upstream: just try a normal pull (will likely noop)
                        self._git_pull(repo, 60)
                else:
                    self._record(False, "git not found or repo not detected")
            except Exception:
                logging.exception("[AutoUpdate] unexpected error during scheduled pull")

            # sleep in 1s chunks so we can stop promptly
            for _ in range(self._interval):
                if self._stop.is_set():
                    return
                time.sleep(1)


    # ---- repo detection -----------------------------------------
    def _find_repo_root(self) -> Optional[str]:
        here = os.path.abspath(os.path.dirname(__file__))
        # try git toplevel first
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

    # ---- git plumbing -------------------------------------------
    def _git_pull(self, repo_path: Optional[str], timeout: int = 180) -> Tuple[bool, str]:
        with self._pull_lock:
            try:
                if not shutil.which("git"):
                    msg = "git not found"
                    self._record(False, msg); return False, msg
                if not repo_path or not os.path.isdir(os.path.join(repo_path, ".git")):
                    msg = f"Not a git repository: {repo_path}"
                    self._record(False, msg); return False, msg

                env = self._git_env()

                # What branch are we on?
                branch = self._current_branch(repo_path, env, timeout)  # None if detached
                # Try upstream remote/branch (origin/main etc.)
                upstream = self._upstream_ref(repo_path, env, timeout)
                if upstream:
                    remote, upstream_branch = upstream
                else:
                    remote = "origin"
                    upstream_branch = branch  # may be None; pull will still work if upstream is set in config

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
                self._record(False, msg); return False, msg
            except Exception as e:
                msg = f"git pull error: {e}"
                logging.exception("[AutoUpdate] %s", msg)
                self._record(False, msg); return False, msg

    def _git_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        # ensure HOME so git can read configs
        for home in (os.environ.get("HOME"), "/home/pi", "/root"):
            if home and os.path.isdir(home):
                env.setdefault("HOME", home); break
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        return env

    def _run_git(self, cmd, env, timeout) -> Tuple[bool, str]:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, timeout=timeout, env=env)
        out = (res.stdout or "") + (res.stderr or "")
        return res.returncode == 0, out.strip()

    def _current_branch(self, repo_path: str, env, timeout: int) -> Optional[str]:
        ok, out = self._run_git(["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"], env, timeout)
        if ok:
            br = out.strip()
            return None if br == "HEAD" else br
        return None

    def _upstream_ref(self, repo_path: str, env, timeout: int) -> Optional[Tuple[str, str]]:
        ok, out = self._run_git(["git", "-C", repo_path, "rev-parse",
                                 "--abbrev-ref", "--symbolic-full-name", "@{u}"], env, timeout)
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
        self._run_git(["git", "config", "--global", "--add", "safe.directory", repo_path], env, timeout)

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
        """
        Returns (ahead, behind) relative to upstream.
        If no upstream, returns (0, 0).
        """
        ok, out = self._run_git(
            ["git", "-C", repo_path, "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            env, timeout
        )
        if ok and out:
            try:
                ahead_str, behind_str = out.split()
                return int(ahead_str), int(behind_str)
            except Exception:
                pass
        return (0, 0)
