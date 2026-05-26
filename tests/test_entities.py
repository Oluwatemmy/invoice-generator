from tests.conftest import signup_and_login


def test_create_client(app, client):
    signup_and_login(app, client)
    resp = client.post(
        "/clients/new",
        data={"name": "Acme", "email": "ops@acme.com", "address": "100 Main", "country": "USA"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        from models import Client
        c = Client.query.first()
        assert c is not None
        assert c.name == "Acme"


def test_duplicate_client_name_blocked(app, client):
    signup_and_login(app, client)
    client.post("/clients/new", data={"name": "Acme", "email": "", "address": "", "country": ""})
    resp = client.post(
        "/clients/new",
        data={"name": "ACME", "email": "", "address": "", "country": ""},
        follow_redirects=True,
    )
    assert b"already exists" in resp.data


def test_edit_client(app, client):
    signup_and_login(app, client)
    client.post("/clients/new", data={"name": "Acme", "email": "", "address": "", "country": ""})
    with app.app_context():
        from models import Client
        cid = Client.query.first().id
    client.post(
        f"/clients/{cid}/edit",
        data={"name": "Acme Inc", "email": "x@y.com", "address": "", "country": ""},
        follow_redirects=True,
    )
    with app.app_context():
        from models import Client
        c = Client.query.first()
        assert c.name == "Acme Inc"
        assert c.email == "x@y.com"


def test_delete_client(app, client):
    signup_and_login(app, client)
    client.post("/clients/new", data={"name": "Acme", "email": "", "address": "", "country": ""})
    with app.app_context():
        from models import Client
        cid = Client.query.first().id
    client.post(f"/clients/{cid}/delete", follow_redirects=True)
    with app.app_context():
        from models import Client
        assert Client.query.count() == 0


def test_create_team_member(app, client):
    signup_and_login(app, client)
    resp = client.post(
        "/team/new",
        data={"name": "Alice", "email": "a@a.com", "address": "", "country": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200


def test_create_bank_profile(app, client):
    signup_and_login(app, client)
    resp = client.post(
        "/bank-profiles/new",
        data={
            "label": "Chase Checking",
            "account_name": "Alice",
            "bank_name": "Chase",
            "account_number": "1234",
            "routing_number": "0210",
            "account_type": "Checking",
            "account_address": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        from models import BankProfile
        p = BankProfile.query.first()
        assert p.bank_name == "Chase"


def test_bank_profile_duplicate_label_blocked(app, client):
    signup_and_login(app, client)
    client.post(
        "/bank-profiles/new",
        data={
            "label": "Chase",
            "account_name": "",
            "bank_name": "",
            "account_number": "",
            "routing_number": "",
            "account_type": "",
            "account_address": "",
        },
    )
    resp = client.post(
        "/bank-profiles/new",
        data={
            "label": "chase",
            "account_name": "",
            "bank_name": "",
            "account_number": "",
            "routing_number": "",
            "account_type": "",
            "account_address": "",
        },
        follow_redirects=True,
    )
    assert b"already exists" in resp.data
