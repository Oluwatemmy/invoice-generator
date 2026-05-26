import os
import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so `import app` works under pytest.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Quiet rate limiter and mailer for tests by setting required env before imports.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("RESEND_API_KEY", "test-key")
os.environ.setdefault("FROM_EMAIL", "test@example.com")

from app import create_app  # noqa: E402
from extensions import db, limiter  # noqa: E402


@pytest.fixture
def app(monkeypatch):
    # Stub outbound email so tests don't hit the network.
    import mailer
    monkeypatch.setattr(mailer, "send_verification_email", lambda *a, **kw: None)
    monkeypatch.setattr(mailer, "send_password_reset_email", lambda *a, **kw: None)
    import routes.auth as auth_mod
    monkeypatch.setattr(auth_mod, "send_verification_email", lambda *a, **kw: None)
    monkeypatch.setattr(auth_mod, "send_password_reset_email", lambda *a, **kw: None)

    app = create_app(test_config={
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
    # Reset any rate limit state between tests.
    limiter.reset()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def signup(client, email="alice@example.com", name="Alice Smith", password="hunter22!"):
    return client.post(
        "/signup",
        data={"email": email, "name": name, "password": password, "confirm": password},
        follow_redirects=True,
    )


def verify(app, client, email="alice@example.com"):
    """Mark the user as verified directly (skips the email round-trip)."""
    with app.app_context():
        from models import User
        u = User.query.filter_by(email=email).first()
        u.email_verified = True
        u.verification_code_hash = None
        u.verification_code_expires_at = None
        db.session.commit()


def login(client, email="alice@example.com", password="hunter22!"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def signup_and_login(app, client, **kwargs):
    signup(client, **kwargs)
    verify(app, client, email=kwargs.get("email", "alice@example.com"))
    return login(
        client,
        email=kwargs.get("email", "alice@example.com"),
        password=kwargs.get("password", "hunter22!"),
    )
