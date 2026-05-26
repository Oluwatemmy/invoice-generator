from tests.conftest import login, signup, signup_and_login, verify


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_signup_creates_user_and_redirects_to_verify(app, client):
    resp = signup(client)
    assert resp.status_code == 200
    assert b"Verify your email" in resp.data

    with app.app_context():
        from models import User
        u = User.query.filter_by(email="alice@example.com").first()
        assert u is not None
        assert u.email_verified is False
        assert u.verification_code_hash is not None  # hash, not the raw code
        assert u.verification_code_expires_at is not None


def test_signup_rejects_short_password(client):
    resp = client.post(
        "/signup",
        data={"email": "x@y.com", "name": "X", "password": "short", "confirm": "short"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"between 8 and 128" in resp.data or b"at least 8" in resp.data.lower() or b"between" in resp.data


def test_signup_normalizes_email_lowercase(app, client):
    signup(client, email="ALICE@Example.COM")
    with app.app_context():
        from models import User
        u = User.query.filter_by(email="alice@example.com").first()
        assert u is not None


def test_login_with_mixed_case_email_works(app, client):
    signup_and_login(app, client, email="bob@example.com")
    client.get("/logout")
    resp = client.post(
        "/login",
        data={"email": "BOB@EXAMPLE.COM", "password": "hunter22!"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Redirected to dashboard
    assert b"Welcome back" in resp.data


def test_login_wrong_password_rejected(app, client):
    signup(client)
    verify(app, client)
    client.get("/logout")
    resp = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "wrongpassword!"},
        follow_redirects=True,
    )
    assert b"Invalid email or password" in resp.data


def test_unverified_user_gated_to_verify(app, client):
    signup(client)  # NOT verified
    # Try to hit the dashboard while unverified
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/verify" in resp.headers["Location"]


def test_login_next_url_blocks_external_redirect(app, client):
    signup_and_login(app, client)
    client.get("/logout")

    resp = client.post(
        "/login?next=https://evil.com/x",
        data={"email": "alice@example.com", "password": "hunter22!"},
        follow_redirects=False,
    )
    # Either redirects to safe location or to /; never to evil.com
    assert "evil.com" not in resp.headers.get("Location", "")


def test_login_next_url_blocks_protocol_relative(app, client):
    signup_and_login(app, client)
    client.get("/logout")

    resp = client.post(
        "/login?next=//evil.com/x",
        data={"email": "alice@example.com", "password": "hunter22!"},
        follow_redirects=False,
    )
    assert "evil.com" not in resp.headers.get("Location", "")


def test_login_next_url_blocks_backslash(app, client):
    signup_and_login(app, client)
    client.get("/logout")

    resp = client.post(
        "/login?next=/\\evil.com/x",
        data={"email": "alice@example.com", "password": "hunter22!"},
        follow_redirects=False,
    )
    loc = resp.headers.get("Location", "")
    assert "evil.com" not in loc


def test_verify_code_flow(app, client):
    signup(client)
    # Pull the raw code by regenerating one we know the hash matches.
    # Easier: directly trigger verify_code() on the model with the real raw code path.
    # We'll cheat the same way the resend route would: set a new code, capture it.
    with app.app_context():
        from extensions import db
        from models import User
        u = User.query.filter_by(email="alice@example.com").first()
        raw = u.generate_verification_code()
        db.session.commit()

    # Wrong code rejected
    resp = client.post("/verify", data={"code": "000000"}, follow_redirects=True)
    assert b"Invalid or expired code" in resp.data

    # Correct code accepted
    resp = client.post("/verify", data={"code": raw}, follow_redirects=True)
    assert b"Email verified" in resp.data

    with app.app_context():
        from models import User
        u = User.query.filter_by(email="alice@example.com").first()
        assert u.email_verified is True
        assert u.verification_code_hash is None
