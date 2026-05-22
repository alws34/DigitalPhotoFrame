import time

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import generate_password_hash

from WebAPI.database import (
    get_user_by_email_or_username,
    update_password_db,
)
from WebAPI.WebUtils.auth_security import EMAIL_RE, USERNAME_RE, password_policy_ok

auth_bp = Blueprint("auth_bp", __name__, url_prefix="/api/auth")


def _now() -> float:
    return time.time()


@auth_bp.route("/signup", methods=["POST"])
def signup():
    backend = current_app.config["backend"]
    if not backend._rl_signup.allow(backend._client_ip()):
        return jsonify({"error": "Please wait before trying again."}), 429

    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not password_policy_ok(password):
        return jsonify({"error": "Password does not meet policy."}), 400
    if not (EMAIL_RE.match(email) and USERNAME_RE.match(username)):
        return jsonify({"error": "Invalid input."}), 400

    try:
        uid = backend._users.create_user(
            email=email,
            username=username,
            password=password,
            role="user",
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        return jsonify({"error": "Cannot create account."}), 500

    return jsonify({"message": "Signup successful. Please log in.", "uid": uid}), 201


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    backend = current_app.config["backend"]

    # Password reset requires an authenticated session. Without this an
    # attacker could take over any account knowing only its email address.
    if not backend.is_authenticated():
        return jsonify({"error": "Password reset requires being logged in."}), 401

    # Rate-limit to blunt brute-force / account-enumeration attempts.
    if not backend._rl_signup.allow(backend._client_ip()):
        return jsonify({"error": "Please wait before trying again."}), 429

    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    new_password = data.get("password") or ""

    if not email or not new_password:
        return jsonify({"error": "Email and new password are required."}), 400

    if not password_policy_ok(new_password):
        return jsonify({"error": "Password does not meet policy."}), 400

    # Generic response regardless of whether the email exists (no enumeration).
    generic_ok = (
        jsonify({"message": "If that account exists, its password has been updated."}),
        200,
    )

    user = get_user_by_email_or_username(email)
    if not user:
        return generic_ok

    pw_hash = generate_password_hash(new_password)
    update_password_db(user["uid"], pw_hash, "pbkdf2:sha256", time.time())

    return generic_ok


@auth_bp.route("/login", methods=["POST"])
def login():
    backend = current_app.config["backend"]
    if not backend._rl_login.allow(backend._client_ip()):
        return jsonify({"error": "Too many attempts."}), 429

    data = request.json or {}
    identity = (data.get("username") or data.get("email_or_username") or "").strip()
    password = data.get("password") or ""

    user = backend._users.verify_login(identity, password)
    if not user or not user.get("is_active", True):
        return jsonify({"error": "Invalid credentials."}), 401

    backend._rotate_session(user["username"], user["uid"], user.get("role", "user"))
    return jsonify(
        {
            "message": "Login successful!",
            "user": {"username": user["username"], "role": user.get("role", "user")},
        }
    ), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "You have been logged out."}), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    backend = current_app.config["backend"]
    if not backend.is_authenticated():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(
        {
            "username": session.get("user"),
            "uid": session.get("uid"),
            "role": session.get("role"),
        }
    ), 200
