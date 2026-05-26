import os

from dotenv import load_dotenv
from flask import Flask, redirect, request, url_for
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from extensions import csrf, db, limiter, login_manager, migrate

load_dotenv()


_VERIFICATION_ALLOWED_ENDPOINTS = {
    "auth.verify",
    "auth.resend_code",
    "auth.logout",
    "healthz",
    "static",
}

_DEFAULT_SECRET_KEY = "dev-secret-change-me"


def _is_production() -> bool:
    return os.environ.get("FLASK_ENV", "").lower() == "production"


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db_url = os.environ.get("DATABASE_URL")
    # Heroku/Render historically emit "postgres://" — SQLAlchemy needs "postgresql://".
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    secret_key = os.environ.get("SECRET_KEY", _DEFAULT_SECRET_KEY)
    if _is_production() and secret_key == _DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY env var must be set to a real random value in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )

    # In production, fail fast on missing email config so we don't crash later
    # when the first user signs up or requests a password reset.
    if _is_production():
        mail_console = os.environ.get("MAIL_TO_CONSOLE", "").strip().lower() in {"1", "true", "yes"}
        if not mail_console:
            for var in ("RESEND_API_KEY", "FROM_EMAIL"):
                if not os.environ.get(var):
                    raise RuntimeError(
                        f"{var} env var is required in production "
                        f"(or set MAIL_TO_CONSOLE=1 to print emails to stdout)."
                    )

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url or (
        "sqlite:///" + os.path.join(app.instance_path, "invoices.db")
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = _is_production()
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = _is_production()

    if test_config:
        app.config.update(test_config)

    if _is_production():
        # Trust X-Forwarded-* headers from the reverse proxy (Render/Railway/Heroku/Nginx).
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    import models  # noqa: F401  — registers tables with SQLAlchemy

    # Flask-Migrate / Alembic. Init AFTER models are imported so the metadata is complete.
    migrate.init_app(app, db, render_as_batch=True)

    from routes.auth import bp as auth_bp
    from routes.bank_profiles import bp as bank_profiles_bp
    from routes.clients import bp as clients_bp
    from routes.invoices import bp as invoices_bp
    from routes.team_members import bp as team_members_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(team_members_bp)
    app.register_blueprint(bank_profiles_bp)

    @app.context_processor
    def _inject_globals():
        return {"is_production": _is_production()}

    @app.route("/healthz")
    def healthz():
        # Liveness probe for Render. Kept deliberately light — no DB hit so a
        # database blip doesn't make the platform restart the web service.
        return {"status": "ok"}, 200

    @app.before_request
    def _gate_unverified_users():
        if not current_user.is_authenticated:
            return None
        if current_user.email_verified:
            return None
        if request.endpoint in _VERIFICATION_ALLOWED_ENDPOINTS:
            return None
        return redirect(url_for("auth.verify"))

    # In tests we use an in-memory DB and skip migrations; create tables directly.
    if app.config.get("TESTING"):
        with app.app_context():
            db.create_all()

    return app


if __name__ == "__main__":
    create_app().run(debug=not _is_production())
