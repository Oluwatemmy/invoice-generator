"""Make sure user A cannot see or mutate user B's data."""
from datetime import date

from tests.conftest import login, signup, signup_and_login, verify


def _invoice_form_data(**overrides):
    data = {
        "biller_name": "A",
        "biller_email": "a@a.com",
        "biller_address": "Addr",
        "client_name": "Client",
        "issue_date": date.today().isoformat(),
        "due_date": date.today().isoformat(),
        "description": ["thing"],
        "amount": ["1.00"],
    }
    data.update(overrides)
    return data


def test_user_cannot_view_other_users_invoice(app, client):
    # User A creates an invoice
    signup_and_login(app, client, email="a@a.com")
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id
    client.get("/logout")

    # User B logs in
    signup(client, email="b@b.com", name="B")
    verify(app, client, email="b@b.com")
    login(client, email="b@b.com")

    resp = client.get(f"/invoices/{inv_id}")
    assert resp.status_code == 404


def test_user_cannot_delete_other_users_invoice(app, client):
    signup_and_login(app, client, email="a@a.com")
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id
    client.get("/logout")

    signup(client, email="b@b.com", name="B")
    verify(app, client, email="b@b.com")
    login(client, email="b@b.com")

    resp = client.post(f"/invoices/{inv_id}/delete")
    assert resp.status_code == 404

    with app.app_context():
        from models import Invoice
        assert Invoice.query.count() == 1  # A's invoice still there


def test_user_cannot_toggle_other_users_invoice_status(app, client):
    signup_and_login(app, client, email="a@a.com")
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id
    client.get("/logout")

    signup(client, email="b@b.com", name="B")
    verify(app, client, email="b@b.com")
    login(client, email="b@b.com")

    resp = client.post(f"/invoices/{inv_id}/status")
    assert resp.status_code == 404


def test_clients_are_user_scoped(app, client):
    signup_and_login(app, client, email="a@a.com")
    client.post("/clients/new", data={"name": "ClientA", "email": "", "address": "", "country": ""}, follow_redirects=True)
    client.get("/logout")

    signup(client, email="b@b.com", name="B")
    verify(app, client, email="b@b.com")
    login(client, email="b@b.com")

    resp = client.get("/clients/")
    assert resp.status_code == 200
    assert b"ClientA" not in resp.data


def test_dashboard_only_shows_own_invoices(app, client):
    signup_and_login(app, client, email="a@a.com")
    client.post("/generate", data=_invoice_form_data(biller_name="UserA Inc"))
    client.get("/logout")

    signup(client, email="b@b.com", name="B")
    verify(app, client, email="b@b.com")
    login(client, email="b@b.com")

    resp = client.get("/")
    assert b"UserA Inc" not in resp.data
    assert b"No invoices yet" in resp.data


def test_duplicate_emails_blocked_case_insensitively(app, client):
    signup(client, email="dup@example.com")
    client.get("/logout")
    resp = client.post(
        "/signup",
        data={
            "email": "DUP@example.com",
            "name": "Dup",
            "password": "hunter22!",
            "confirm": "hunter22!",
        },
        follow_redirects=True,
    )
    assert b"already exists" in resp.data
