import secrets
from datetime import date, datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager

VERIFICATION_CODE_TTL_MINUTES = 15


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    invoice_counters = db.Column(db.JSON, default=dict, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_code = db.Column(db.String(10), nullable=True)
    verification_code_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    clients = db.relationship(
        "Client", backref="user", cascade="all, delete-orphan", lazy=True
    )
    team_members = db.relationship(
        "TeamMember", backref="user", cascade="all, delete-orphan", lazy=True
    )
    bank_profiles = db.relationship(
        "BankProfile", backref="user", cascade="all, delete-orphan", lazy=True
    )
    invoices = db.relationship(
        "Invoice", backref="user", cascade="all, delete-orphan", lazy=True
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def generate_verification_code(self) -> str:
        """Generate a fresh 6-digit code, store with TTL, return it for emailing."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.verification_code = code
        self.verification_code_expires_at = datetime.utcnow() + timedelta(
            minutes=VERIFICATION_CODE_TTL_MINUTES
        )
        return code

    def verify_code(self, code: str) -> bool:
        """Validate a submitted code. On success, marks email verified and clears the code."""
        if not (self.verification_code and self.verification_code_expires_at):
            return False
        if datetime.utcnow() > self.verification_code_expires_at:
            return False
        if code.strip() != self.verification_code:
            return False
        self.email_verified = True
        self.verification_code = None
        self.verification_code_expires_at = None
        return True

    def next_invoice_number(self, biller_name: str) -> str:
        year = str(date.today().year)
        counters = dict(self.invoice_counters or {})
        next_num = counters.get(year, 0) + 1
        counters[year] = next_num
        self.invoice_counters = counters
        initials = "".join(w[0] for w in biller_name.split() if w)[:3].upper() or "INV"
        return f"{initials}-{year}-{next_num:04d}"


@login_manager.user_loader
def _load_user(user_id: str):
    return db.session.get(User, int(user_id))


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), default="", nullable=False)
    address = db.Column(db.Text, default="", nullable=False)
    country = db.Column(db.String(120), default="", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class TeamMember(db.Model):
    __tablename__ = "team_members"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), default="", nullable=False)
    address = db.Column(db.Text, default="", nullable=False)
    country = db.Column(db.String(120), default="", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class BankProfile(db.Model):
    __tablename__ = "bank_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    label = db.Column(db.String(255), nullable=False)
    account_name = db.Column(db.String(255), default="", nullable=False)
    bank_name = db.Column(db.String(255), default="", nullable=False)
    account_number = db.Column(db.String(120), default="", nullable=False)
    routing_number = db.Column(db.String(120), default="", nullable=False)
    account_address = db.Column(db.Text, default="", nullable=False)
    account_type = db.Column(db.String(60), default="", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    invoice_number = db.Column(db.String(60), unique=True, nullable=False)
    issue_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)
    biller_data = db.Column(db.JSON, nullable=False)
    client_data = db.Column(db.JSON, nullable=False)
    bank_data = db.Column(db.JSON, default=dict, nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="unpaid", nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    line_items = db.relationship(
        "InvoiceLineItem",
        backref="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.position",
    )


class InvoiceLineItem(db.Model):
    __tablename__ = "invoice_line_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(
        db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True
    )
    position = db.Column(db.Integer, default=0, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
