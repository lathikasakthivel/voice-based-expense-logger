# app/__init__.py
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object("app.config.Config")

    # ✅ Allow both localhost and 127.0.0.1 for development
    CORS(
        app,
        resources={r"/api/*": {"origins": ["http://127.0.0.1:5000", "http://localhost:5000"]}},
        supports_credentials=True
    )

    # ✅ Make sure session cookies behave well with credentials
    app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",   # default; works for same-origin
    SESSION_COOKIE_SECURE=False,     # fine for http://127.0.0.1:5000 in dev
    )

    # Register blueprints
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    return app
