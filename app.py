import os

from dotenv import load_dotenv
from flask import Flask, redirect, request, url_for
from flask_login import current_user

from extensions import csrf, db, login_manager

load_dotenv()


_VERIFICATION_ALLOWED_ENDPOINTS = {
    "auth.verify",
    "auth.resend_code",
    "auth.logout",
    "static",
}


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url or (
        "sqlite:///" + os.path.join(app.instance_path, "invoices.db")
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    import models  # noqa: F401  — registers tables with SQLAlchemy

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

    @app.before_request
    def _gate_unverified_users():
        if not current_user.is_authenticated:
            return None
        if current_user.email_verified:
            return None
        if request.endpoint in _VERIFICATION_ALLOWED_ENDPOINTS:
            return None
        return redirect(url_for("auth.verify"))

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
