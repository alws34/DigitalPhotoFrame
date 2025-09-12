# auth_security.py
import os
import re
import json
import hmac
import time
import secrets
import hashlib
import tempfile
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from werkzeug.security import generate_password_hash, check_password_hash

# Optional argon2 (preferred)
try:
    from argon2 import PasswordHasher  # pip install argon2-cffi
    _ARGON2 = PasswordHasher(time_cost=2, memory_cost=256*1024, parallelism=2)  # ~256 MB, tune down on tiny devices
    _USE_ARGON2 = True
except Exception:
    _USE_ARGON2 = False

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._\-]{3,32}$")

# Basic password policy: length >= 10, and at least 3 classes among [lower, upper, digit, symbol].
def password_policy_ok(pw: str) -> bool:
    if len(pw) < 10:
        return False
    classes = 0
    classes += any(c.islower() for c in pw)
    classes += any(c.isupper() for c in pw)
    classes += any(c.isdigit() for c in pw)
    classes += any(c in r"!@#$%^&*()_+-=[]{};':\",.<>/?\|" for c in pw)
    return classes >= 3

def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)

def _now() -> float:
    return time.time()

@dataclass
class UserRecord:
    uid: str
    email: str
    username: str
    pw_hash: str
    algo: str  # "argon2" or "pbkdf2"
    role: str  # "user" or "admin"
    is_active: bool
    created_at: float
    last_login: Optional[float] = None
    failed_count: int = 0
    lock_until: float = 0.0
    password_changed_at: Optional[float] = None

class UserStore:
    """
    JSON format:
    {
      "users": { "<uid>": <UserRecord-as-dict>, ... },
      "index": { "email": {"e@x": "<uid>"}, "username": {"name": "<uid>"} }
    }
    """
    def __init__(self, path: str):
        self.path = path
        self._data = {"users": {}, "index": {"email": {}, "username": {}}}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict) and "users" in obj and "index" in obj:
                self._data = obj
        except FileNotFoundError:
            self._atomic_save()
        except Exception:
            # If corrupt, back it up and start fresh
            try:
                os.replace(self.path, self.path + ".corrupt")
            except Exception:
                pass
            self._data = {"users": {}, "index": {"email": {}, "username": {}}}
            self._atomic_save()

    def _atomic_save(self) -> None:
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=d or None, prefix=".users.json.")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    def _new_uid(self) -> str:
        return secrets.token_hex(16)

    def _hash_password(self, password: str) -> Tuple[str, str]:
        if _USE_ARGON2:
            return _ARGON2.hash(password), "argon2"
        # PBKDF2 fallback via Werkzeug
        # Increase iterations moderately for desktop/server (tune if Pi)
        return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16), "pbkdf2"

    def _verify_password(self, algo: str, pw_hash: str, password: str) -> bool:
        if algo == "argon2" and _USE_ARGON2:
            try:
                _ARGON2.verify(pw_hash, password)
                return True
            except Exception:
                return False
        return check_password_hash(pw_hash, password)

    # Public API
    def create_user(self, email: str, username: str, password: str, role: str = "user") -> str:
        email = email.strip().lower()
        username = username.strip()

        if not EMAIL_RE.match(email):
            raise ValueError("Invalid email")
        if not USERNAME_RE.match(username):
            raise ValueError("Invalid username")
        if not password_policy_ok(password):
            raise ValueError("Password does not meet policy")

        if email in self._data["index"]["email"]:
            raise ValueError("Email already registered")
        if username in self._data["index"]["username"]:
            raise ValueError("Username already taken")

        pw_hash, algo = self._hash_password(password)
        uid = self._new_uid()
        rec = UserRecord(
            uid=uid,
            email=email,
            username=username,
            pw_hash=pw_hash,
            algo=algo,
            role=role,
            is_active=True,
            created_at=_now(),
            password_changed_at=_now(),
        )
        self._data["users"][uid] = rec.__dict__
        self._data["index"]["email"][email] = uid
        self._data["index"]["username"][username] = uid
        self._atomic_save()
        return uid

    def find_by_email_or_username(self, identity: str) -> Optional[Dict]:
        identity_norm = identity.strip()
        by_email = self._data["index"]["email"].get(identity_norm.lower())
        if by_email:
            return self._data["users"].get(by_email)
        by_user = self._data["index"]["username"].get(identity_norm)
        if by_user:
            return self._data["users"].get(by_user)
        return None

    def verify_login(self, identity: str, password: str) -> Optional[Dict]:
        user = self.find_by_email_or_username(identity)
        # Always do a constant-time check even if user missing to reduce timing diff
        fake_hash = generate_password_hash("x")  # PBKDF2 waste
        if not user:
            _ = check_password_hash(fake_hash, password)
            return None
        # lockout
        if _now() < float(user.get("lock_until", 0.0)):
            return None
        ok = self._verify_password(user.get("algo", "pbkdf2"), user.get("pw_hash", ""), password)
        if ok:
            user["failed_count"] = 0
            user["lock_until"] = 0.0
            user["last_login"] = _now()
            self._atomic_save()
            return user
        # failure
        user["failed_count"] = int(user.get("failed_count", 0)) + 1
        if user["failed_count"] >= 5:  # lock for 15 minutes
            user["lock_until"] = _now() + 15 * 60
            user["failed_count"] = 0
        self._atomic_save()
        return None

    def change_password(self, uid: str, new_password: str) -> None:
        if not password_policy_ok(new_password):
            raise ValueError("Password does not meet policy")
        user = self._data["users"].get(uid)
        if not user:
            raise ValueError("User not found")
        pw_hash, algo = self._hash_password(new_password)
        user["pw_hash"] = pw_hash
        user["algo"] = algo
        user["password_changed_at"] = _now()
        self._atomic_save()

    def list_users(self) -> Dict[str, Dict]:
        return self._data["users"].copy()

# -------------- CSRF --------------

CSRF_SESSION_KEY = "_csrf_token"

def ensure_csrf(session_obj) -> str:
    tok = session_obj.get(CSRF_SESSION_KEY)
    if not tok:
        tok = secrets.token_urlsafe(32)
        session_obj[CSRF_SESSION_KEY] = tok
    return tok

def validate_csrf(session_obj, form_value: str) -> bool:
    want = session_obj.get(CSRF_SESSION_KEY, "")
    if not want or not form_value:
        return False
    return _constant_time_eq(want, form_value)

# -------------- IP rate limiting (simple in-memory) --------------

class RateLimiter:
    """
    Sliding window per key. Not persistent across restarts.
    """
    def __init__(self, limit: int, window_sec: int):
        self.limit = limit
        self.window = window_sec
        self._buckets: Dict[str, list] = {}

    def allow(self, key: str) -> bool:
        now = _now()
        bucket = self._buckets.setdefault(key, [])
        # drop old
        i = 0
        for i in range(len(bucket)):
            if now - bucket[i] <= self.window:
                break
        bucket[:] = bucket[i:] if bucket and now - bucket[0] > self.window else bucket
        # append
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True
