from datetime import date, timedelta

from tests.conftest import signup_and_login


def _invoice_form_data(**overrides):
    data = {
        "biller_name": "Tolga Doksanbir",
        "biller_email": "tolga@example.com",
        "biller_address": "1 Main St\nBerlin",
        "biller_country": "Germany",
        "client_name": "Acme Corp",
        "client_email": "billing@acme.com",
        "client_address": "100 Acme Way",
        "client_country": "USA",
        "issue_date": date.today().isoformat(),
        "due_date": date.today().isoformat(),
        "description": ["Web design", "Hosting"],
        "amount": ["500.00", "120.50"],
        "bank_name": "Chase",
        "account_name": "Tolga D",
        "account_number": "1234567890",
        "routing_number": "021000021",
        "account_type": "Checking",
    }
    data.update(overrides)
    return data


def test_dashboard_renders_when_empty(app, client):
    signup_and_login(app, client)
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"No invoices yet" in resp.data
    assert b"Welcome back" in resp.data


def test_create_invoice_redirects_to_view(app, client):
    signup_and_login(app, client)
    resp = client.post("/generate", data=_invoice_form_data(), follow_redirects=False)
    assert resp.status_code == 302
    assert "/invoices/" in resp.headers["Location"]


def test_create_invoice_persists_data_and_total(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv = Invoice.query.first()
        assert inv is not None
        assert float(inv.total) == 620.50
        assert inv.status == "unpaid"
        assert inv.invoice_number.startswith("TD-")
        # Bank uses standardized "bank_name" key in JSON snapshot
        assert inv.bank_data["bank_name"] == "Chase"
        assert "name" not in inv.bank_data or inv.bank_data.get("name") in (None, "")
        assert len(inv.line_items) == 2


def test_invoice_rejects_missing_line_items(app, client):
    signup_and_login(app, client)
    resp = client.post(
        "/generate",
        data=_invoice_form_data(description=[""], amount=[""]),
        follow_redirects=True,
    )
    assert b"At least one line item" in resp.data


def test_invoice_rejects_bad_amount(app, client):
    signup_and_login(app, client)
    resp = client.post(
        "/generate",
        data=_invoice_form_data(description=["X"], amount=["abc"]),
        follow_redirects=True,
    )
    assert b"Invalid amount" in resp.data


def test_invoice_rejects_negative_amount(app, client):
    signup_and_login(app, client)
    resp = client.post(
        "/generate",
        data=_invoice_form_data(description=["X"], amount=["-5"]),
        follow_redirects=True,
    )
    assert b"Negative amount" in resp.data


def test_invoice_rejects_missing_required_field(app, client):
    signup_and_login(app, client)
    data = _invoice_form_data()
    data["biller_name"] = ""
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"Biller name is required" in resp.data


def test_invoice_rejects_invalid_date(app, client):
    signup_and_login(app, client)
    data = _invoice_form_data()
    data["issue_date"] = "not-a-date"
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"Invalid date" in resp.data


def test_invoice_number_retries_on_collision(app, client):
    """Simulate a concurrent commit by pre-inserting the would-be-next number
    + bumping the user counter. The new request should refresh and skip past."""
    from decimal import Decimal
    from extensions import db
    from models import Invoice, User

    signup_and_login(app, client)
    year = str(date.today().year)
    biller = _invoice_form_data()["biller_name"]
    initials = "".join(w[0] for w in biller.split() if w)[:3].upper()
    colliding_number = f"{initials}-{year}-0001"

    with app.app_context():
        user = User.query.first()
        # Pretend another transaction already committed: counter bumped + invoice exists.
        user.invoice_counters = {year: 1}
        db.session.add(
            Invoice(
                user_id=user.id,
                invoice_number=colliding_number,
                issue_date=date.today(),
                due_date=date.today(),
                biller_data={"name": biller},
                client_data={"name": "Other"},
                bank_data={},
                total=Decimal("1.00"),
                status="paid",
            )
        )
        db.session.commit()

    resp = client.post("/generate", data=_invoice_form_data(), follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        latest = (
            Invoice.query.filter(Invoice.invoice_number != colliding_number)
            .order_by(Invoice.id.desc())
            .first()
        )
        # Should have skipped 0001 (collision) and gotten 0002
        assert latest.invoice_number == f"{initials}-{year}-0002"


def test_invoice_number_increments_per_year(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        nums = sorted(i.invoice_number for i in Invoice.query.all())
        year = str(date.today().year)
        assert nums[0].endswith(f"-{year}-0001")
        assert nums[1].endswith(f"-{year}-0002")


def test_toggle_status_flips_paid_unpaid(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id

    client.post(f"/invoices/{inv_id}/status")
    with app.app_context():
        from extensions import db
        from models import Invoice
        assert db.session.get(Invoice, inv_id).status == "paid"

    client.post(f"/invoices/{inv_id}/status")
    with app.app_context():
        from extensions import db
        from models import Invoice
        assert db.session.get(Invoice, inv_id).status == "unpaid"


def test_edit_invoice_paid_is_blocked(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id
    client.post(f"/invoices/{inv_id}/status")  # mark paid
    resp = client.get(f"/invoices/{inv_id}/edit", follow_redirects=True)
    assert b"can&#39;t be edited" in resp.data or b"can't be edited" in resp.data


def test_edit_invoice_updates_fields(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id

    updated = _invoice_form_data(
        description=["Updated"], amount=["999.99"], client_name="New Client"
    )
    client.post(f"/invoices/{inv_id}/edit", data=updated, follow_redirects=True)
    with app.app_context():
        from extensions import db
        from models import Invoice
        inv = db.session.get(Invoice, inv_id)
        assert float(inv.total) == 999.99
        assert inv.client_data["name"] == "New Client"
        assert len(inv.line_items) == 1


def test_delete_invoice(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id
    resp = client.post(f"/invoices/{inv_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        from models import Invoice
        assert Invoice.query.count() == 0


def test_duplicate_invoice_prefills_form(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id
    resp = client.get(f"/invoices/{inv_id}/duplicate")
    assert resp.status_code == 200
    assert b"Tolga Doksanbir" in resp.data
    assert b"Acme Corp" in resp.data


def test_invoice_list_filters_by_status(app, client):
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        first = Invoice.query.first()
        first_id = first.id
    client.post(f"/invoices/{first_id}/status")  # one paid, one unpaid

    resp = client.get("/invoices?status=paid")
    assert resp.status_code == 200
    resp_unpaid = client.get("/invoices?status=unpaid")
    assert resp_unpaid.status_code == 200


def test_invoice_rejects_due_before_issue(app, client):
    signup_and_login(app, client)
    today = date.today()
    data = _invoice_form_data(
        issue_date=today.isoformat(),
        due_date=(today - timedelta(days=1)).isoformat(),
    )
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"Due date cannot be before" in resp.data


def test_invoice_rejects_period_end_before_start(app, client):
    signup_and_login(app, client)
    today = date.today()
    data = _invoice_form_data(
        period_start=today.isoformat(),
        period_end=(today - timedelta(days=1)).isoformat(),
    )
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"Service period end cannot be before" in resp.data


def test_invoice_rejects_too_many_line_items(app, client):
    signup_and_login(app, client)
    data = _invoice_form_data(
        description=["x"] * 101, amount=["1.00"] * 101
    )
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"Too many line items" in resp.data


def test_invoice_rejects_amount_over_max(app, client):
    signup_and_login(app, client)
    data = _invoice_form_data(description=["X"], amount=["100000000.00"])
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"exceeds the" in resp.data


def test_invoice_rejects_long_description(app, client):
    signup_and_login(app, client)
    data = _invoice_form_data(description=["x" * 501], amount=["1.00"])
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"500 characters or less" in resp.data


def test_invoice_rejects_long_biller_address(app, client):
    signup_and_login(app, client)
    data = _invoice_form_data(biller_address="x" * 1001)
    resp = client.post("/generate", data=data, follow_redirects=True)
    assert b"1000 characters or less" in resp.data


def test_pdf_route_returns_503_when_weasyprint_unavailable(app, client, monkeypatch):
    """On Windows local dev WeasyPrint usually isn't installed; the route must
    fail gracefully with 503, not 500."""
    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id

    # Force the ImportError path regardless of whether weasyprint is installed locally
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "weasyprint" or name.startswith("weasyprint."):
            raise ImportError("simulated for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    resp = client.get(f"/invoices/{inv_id}/pdf")
    assert resp.status_code == 503


def test_pdf_route_serves_pdf_when_weasyprint_available(app, client):
    """If WeasyPrint can import + render in this environment, the route returns a PDF."""
    try:
        import weasyprint  # noqa: F401
        weasyprint.HTML(string="<p>ok</p>").write_pdf()
    except Exception:
        import pytest
        pytest.skip("WeasyPrint not functional in this environment (typical on Windows)")

    signup_and_login(app, client)
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv = Invoice.query.first()
        inv_id, inv_number = inv.id, inv.invoice_number

    resp = client.get(f"/invoices/{inv_id}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert f"invoice-{inv_number}.pdf" in resp.headers["Content-Disposition"]


def test_pdf_route_scoped_to_owner(app, client):
    """User B cannot download user A's invoice PDF."""
    signup_and_login(app, client, email="a@a.com")
    client.post("/generate", data=_invoice_form_data())
    with app.app_context():
        from models import Invoice
        inv_id = Invoice.query.first().id
    client.get("/logout")

    from tests.conftest import login, signup, verify
    signup(client, email="b@b.com", name="B")
    verify(app, client, email="b@b.com")
    login(client, email="b@b.com")

    resp = client.get(f"/invoices/{inv_id}/pdf")
    assert resp.status_code == 404


def test_save_as_new_persists_entities(app, client):
    signup_and_login(app, client)
    data = _invoice_form_data()
    data["save_client"] = "1"
    data["save_team"] = "1"
    data["save_bank"] = "1"
    client.post("/generate", data=data)
    with app.app_context():
        from models import BankProfile, Client, TeamMember
        assert TeamMember.query.count() == 1
        assert Client.query.count() == 1
        assert BankProfile.query.count() == 1
