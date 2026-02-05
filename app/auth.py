# app/auth.py
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import get_db
from datetime import datetime

# ✅ Mount under /api/auth to match the frontend (API_BASE + /auth/...)
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not (email and username and password):
        return jsonify({"error": "Missing email, username, or password"}), 400

    db = get_db()
    if db.users.find_one({"email": email}):
        return jsonify({"error": "Email already exists"}), 400

    user = {
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.utcnow(),
    }
    result = db.users.insert_one(user)

    # set session
    session["user_id"] = str(result.inserted_id)

    return jsonify({"message": "Signed up", "user_id": str(result.inserted_id)}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not (email and password):
        return jsonify({"error": "Missing email or password"}), 400

    db = get_db()
    user = db.users.find_one({"email": email})
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    session["user_id"] = str(user["_id"])
    return jsonify({"message": "Logged in", "user_id": str(user["_id"])}), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out"}), 200


# Optional: useful for debugging auth quickly
@auth_bp.route("/me", methods=["GET"])
def me():
    uid = session.get("user_id")
    return jsonify({"user_id": uid}), 200
