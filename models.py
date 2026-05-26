import secrets
from datetime import date, datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import Index, func
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager

VERIFICATION_CODE_TTL_MINUTES = 15


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    invoice_counters = db.Column(db.JSON, default=dict, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    # Stored as a Werkzeug password hash. Column kept as "verification_code"
    # for backwards-compatibility with existing SQLite DBs.
    verification_code_hash = db.Column("verification_code", db.String(255), nullable=True)
    verification_code_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_users_email_lower", func.lower(email), unique=True),
    )

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

    @validates("email")
    def _normalize_email(self, _key, value):
        if value is None:
            return value
        return value.strip().lower()

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def generate_verification_code(self) -> str:
        """Generate a fresh 6-digit code, store its hash with TTL, return the raw code for emailing."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.verification_code_hash = generate_password_hash(code)
        self.verification_code_expires_at = _utcnow() + timedelta(
            minutes=VERIFICATION_CODE_TTL_MINUTES
        )
        return code

    def verify_code(self, code: str) -> bool:
        """Validate a submitted code. On success, marks email verified and clears the stored hash."""
        if not (self.verification_code_hash and self.verification_code_expires_at):
            return False
        if _utcnow() > self.verification_code_expires_at:
            return False
        try:
            ok = check_password_hash(self.verification_code_hash, (code or "").strip())
        except (ValueError, TypeError):
            # Pre-hash legacy value in the column — refuse, user can resend.
            return False
        if not ok:
            return False
        self.email_verified = True
        self.verification_code_hash = None
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
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


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
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


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
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


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
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

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
