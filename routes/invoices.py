from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from extensions import db
from models import BankProfile, Client, Invoice, InvoiceLineItem, TeamMember

bp = Blueprint("invoices", __name__)


# ---------- Formatting helpers ----------


def _fmt_long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _fmt_period_dates(s, e) -> str:
    if not (s and e):
        return ""
    if s.year == e.year:
        return f"{s.strftime('%b')} {s.day} – {e.strftime('%b')} {e.day}, {e.year}"
    return (
        f"{s.strftime('%b')} {s.day}, {s.year} – "
        f"{e.strftime('%b')} {e.day}, {e.year}"
    )


def _parse_date_or_none(s: str):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _build_invoice_context(inv: Invoice) -> dict:
    biller = dict(inv.biller_data or {})
    biller["initial"] = (biller.get("name") or "?")[:1].upper() or "?"

    return {
        "invoice": inv,
        "invoice_number": inv.invoice_number,
        "issue_date": _fmt_long_date(inv.issue_date),
        "due_date": _fmt_long_date(inv.due_date),
        "biller": biller,
        "client": dict(inv.client_data or {}),
        "bank": dict(inv.bank_data or {}),
        "line_items": [
            {
                "description": item.description,
                "amount_formatted": f"${float(item.amount):,.2f}",
            }
            for item in inv.line_items
        ],
        "total_formatted": f"${float(inv.total):,.2f}",
        "period_range": _fmt_period_dates(inv.period_start, inv.period_end),
    }


# ---------- Routes ----------


@bp.route("/")
@login_required
def home():
    invoices = (
        Invoice.query.filter_by(user_id=current_user.id)
        .order_by(Invoice.created_at.desc())
        .all()
    )
    paid_count = sum(1 for i in invoices if i.status == "paid")
    unpaid_count = len(invoices) - paid_count
    total_paid = sum(float(i.total) for i in invoices if i.status == "paid")
    total_unpaid = sum(float(i.total) for i in invoices if i.status == "unpaid")
    total_billed = total_paid + total_unpaid

    recent = invoices[:5]
    recent_rows = [
        {
            "id": inv.id,
            "number": inv.invoice_number,
            "client_name": (inv.client_data or {}).get("name", ""),
            "total_formatted": f"${float(inv.total):,.2f}",
            "status": inv.status,
            "issue_date": _fmt_long_date(inv.issue_date),
        }
        for inv in recent
    ]

    return render_template(
        "dashboard.html",
        total_billed_fmt=f"${total_billed:,.2f}",
        total_paid_fmt=f"${total_paid:,.2f}",
        total_unpaid_fmt=f"${total_unpaid:,.2f}",
        paid_count=paid_count,
        unpaid_count=unpaid_count,
        recent=recent_rows,
    )


def _form_context(
    prefill: dict | None = None,
    form_action: str | None = None,
    edit_mode: bool = False,
) -> dict:
    today = date.today()
    team_members = (
        TeamMember.query.filter_by(user_id=current_user.id)
        .order_by(TeamMember.name)
        .all()
    )
    clients = (
        Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()
    )
    bank_profiles = (
        BankProfile.query.filter_by(user_id=current_user.id)
        .order_by(BankProfile.label)
        .all()
    )
    entities = {
        "team_members": [
            {
                "id": m.id,
                "name": m.name,
                "email": m.email,
                "address": m.address,
                "country": m.country,
            }
            for m in team_members
        ],
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "address": c.address,
                "country": c.country,
            }
            for c in clients
        ],
        "bank_profiles": [
            {
                "id": p.id,
                "label": p.label,
                "account_name": p.account_name,
                "bank_name": p.bank_name,
                "account_number": p.account_number,
                "routing_number": p.routing_number,
                "account_address": p.account_address,
                "account_type": p.account_type,
            }
            for p in bank_profiles
        ],
    }
    return {
        "default_issue": today.isoformat(),
        "default_due": (today + timedelta(days=14)).isoformat(),
        "team_members": team_members,
        "clients": clients,
        "bank_profiles": bank_profiles,
        "entities": entities,
        "prefill": prefill,
        "form_action": form_action,
        "edit_mode": edit_mode,
    }


@bp.route("/new")
@login_required
def new_invoice():
    return render_template("form.html", **_form_context())


@bp.route("/invoices/<int:invoice_id>/duplicate")
@login_required
def duplicate_invoice(invoice_id: int):
    inv = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first()
    if inv is None:
        abort(404)
    prefill = {
        "biller": dict(inv.biller_data or {}),
        "client": dict(inv.client_data or {}),
        "bank": dict(inv.bank_data or {}),
        "line_items": [
            {"description": item.description, "amount": f"{float(item.amount):.2f}"}
            for item in inv.line_items
        ],
    }
    return render_template("form.html", **_form_context(prefill=prefill))


@bp.route("/generate", methods=["POST"])
@login_required
def generate():
    biller_name = request.form["biller_name"].strip()
    issue_date = date.fromisoformat(request.form["issue_date"])
    due_date = date.fromisoformat(request.form["due_date"])

    descriptions = request.form.getlist("description")
    raw_amounts = request.form.getlist("amount")
    parsed_items: list[tuple[str, Decimal]] = []
    for desc, raw in zip(descriptions, raw_amounts):
        desc = desc.strip()
        if not desc or not raw:
            continue
        try:
            amt = Decimal(raw)
        except (ValueError, ArithmeticError):
            continue
        parsed_items.append((desc, amt))

    if not parsed_items:
        return "At least one line item is required.", 400

    total = sum((amt for _, amt in parsed_items), Decimal("0"))

    invoice_number = current_user.next_invoice_number(biller_name)

    biller_data = {
        "name": biller_name,
        "email": request.form["biller_email"].strip(),
        "address": request.form["biller_address"].strip(),
        "country": request.form.get("biller_country", "").strip(),
    }
    client_data = {
        "name": request.form["client_name"].strip(),
        "email": request.form.get("client_email", "").strip(),
        "address": request.form.get("client_address", "").strip(),
        "country": request.form.get("client_country", "").strip(),
    }
    bank_data = {
        "account_name": request.form.get("account_name", "").strip(),
        "name": request.form.get("bank_name", "").strip(),
        "account_number": request.form.get("account_number", "").strip(),
        "routing_number": request.form.get("routing_number", "").strip(),
        "account_address": request.form.get("account_address", "").strip(),
        "account_type": request.form.get("account_type", "").strip(),
    }

    invoice = Invoice(
        user_id=current_user.id,
        invoice_number=invoice_number,
        issue_date=issue_date,
        due_date=due_date,
        period_start=_parse_date_or_none(request.form.get("period_start", "")),
        period_end=_parse_date_or_none(request.form.get("period_end", "")),
        biller_data=biller_data,
        client_data=client_data,
        bank_data=bank_data,
        total=total,
        status="unpaid",
    )
    db.session.add(invoice)
    db.session.flush()  # assign invoice.id before line items

    for idx, (desc, amt) in enumerate(parsed_items):
        db.session.add(
            InvoiceLineItem(
                invoice_id=invoice.id,
                position=idx,
                description=desc,
                amount=amt,
            )
        )

    # Optional: persist biller / client / bank as saved entities for next time.
    # Silently skip if a matching record already exists for this user.
    if request.form.get("save_team") and biller_data["name"]:
        existing = TeamMember.query.filter(
            TeamMember.user_id == current_user.id,
            func.lower(TeamMember.name) == biller_data["name"].lower(),
        ).first()
        if existing is None:
            db.session.add(
                TeamMember(
                    user_id=current_user.id,
                    name=biller_data["name"],
                    email=biller_data["email"],
                    address=biller_data["address"],
                    country=biller_data["country"],
                )
            )
    if request.form.get("save_client") and client_data["name"]:
        existing = Client.query.filter(
            Client.user_id == current_user.id,
            func.lower(Client.name) == client_data["name"].lower(),
        ).first()
        if existing is None:
            db.session.add(
                Client(
                    user_id=current_user.id,
                    name=client_data["name"],
                    email=client_data["email"],
                    address=client_data["address"],
                    country=client_data["country"],
                )
            )
    if request.form.get("save_bank") and any(bank_data.values()):
        label = bank_data["name"] or bank_data["account_name"] or "Saved bank"
        conditions = [func.lower(BankProfile.label) == label.lower()]
        if bank_data["account_number"]:
            conditions.append(BankProfile.account_number == bank_data["account_number"])
        existing = BankProfile.query.filter(
            BankProfile.user_id == current_user.id,
            or_(*conditions),
        ).first()
        if existing is None:
            db.session.add(
                BankProfile(
                    user_id=current_user.id,
                    label=label,
                    account_name=bank_data["account_name"],
                    bank_name=bank_data["name"],
                    account_number=bank_data["account_number"],
                    routing_number=bank_data["routing_number"],
                    account_address=bank_data["account_address"],
                    account_type=bank_data["account_type"],
                )
            )

    db.session.commit()
    return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))


@bp.route("/invoices")
@login_required
def list_invoices():
    status_filter = request.args.get("status")
    query = Invoice.query.filter_by(user_id=current_user.id)
    if status_filter in ("paid", "unpaid"):
        query = query.filter_by(status=status_filter)
    invoices = query.order_by(Invoice.created_at.desc()).all()

    rows = []
    for inv in invoices:
        client = dict(inv.client_data or {})
        rows.append({
            "id": inv.id,
            "number": inv.invoice_number,
            "client_name": client.get("name", ""),
            "issue_date": _fmt_long_date(inv.issue_date),
            "due_date": _fmt_long_date(inv.due_date),
            "total_formatted": f"${float(inv.total):,.2f}",
            "status": inv.status,
        })

    return render_template(
        "invoices_list.html", invoices=rows, status_filter=status_filter
    )


@bp.route("/invoices/<int:invoice_id>")
@login_required
def view_invoice(invoice_id: int):
    inv = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first()
    if inv is None:
        abort(404)
    return render_template("invoice.html", **_build_invoice_context(inv))


@bp.route("/invoices/<int:invoice_id>/status", methods=["POST"])
@login_required
def toggle_status(invoice_id: int):
    inv = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first()
    if inv is None:
        abort(404)
    inv.status = "paid" if inv.status == "unpaid" else "unpaid"
    db.session.commit()
    next_url = request.form.get("next") or url_for(
        "invoices.view_invoice", invoice_id=inv.id
    )
    return redirect(next_url)


@bp.route("/invoices/<int:invoice_id>/delete", methods=["POST"])
@login_required
def delete_invoice(invoice_id: int):
    inv = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first()
    if inv is None:
        abort(404)
    db.session.delete(inv)
    db.session.commit()
    return redirect(url_for("invoices.list_invoices"))


@bp.route("/invoices/<int:invoice_id>/edit", methods=["GET", "POST"])
@login_required
def edit_invoice(invoice_id: int):
    inv = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first()
    if inv is None:
        abort(404)
    if inv.status == "paid":
        flash(
            "Paid invoices can't be edited. Mark it as unpaid first if you need to change it.",
            "error",
        )
        return redirect(url_for("invoices.view_invoice", invoice_id=inv.id))

    if request.method == "GET":
        prefill = {
            "biller": dict(inv.biller_data or {}),
            "client": dict(inv.client_data or {}),
            "bank": dict(inv.bank_data or {}),
            "issue_date": inv.issue_date.isoformat(),
            "due_date": inv.due_date.isoformat(),
            "period_start": inv.period_start.isoformat() if inv.period_start else "",
            "period_end": inv.period_end.isoformat() if inv.period_end else "",
            "line_items": [
                {"description": item.description, "amount": f"{float(item.amount):.2f}"}
                for item in inv.line_items
            ],
        }
        return render_template(
            "form.html",
            **_form_context(
                prefill=prefill,
                form_action=url_for("invoices.edit_invoice", invoice_id=inv.id),
                edit_mode=True,
            ),
        )

    # POST: update the invoice in place
    biller_name = request.form["biller_name"].strip()

    descriptions = request.form.getlist("description")
    raw_amounts = request.form.getlist("amount")
    parsed_items: list[tuple[str, Decimal]] = []
    for desc, raw in zip(descriptions, raw_amounts):
        desc = desc.strip()
        if not desc or not raw:
            continue
        try:
            amt = Decimal(raw)
        except (ValueError, ArithmeticError):
            continue
        parsed_items.append((desc, amt))

    if not parsed_items:
        return "At least one line item is required.", 400

    inv.issue_date = date.fromisoformat(request.form["issue_date"])
    inv.due_date = date.fromisoformat(request.form["due_date"])
    inv.period_start = _parse_date_or_none(request.form.get("period_start", ""))
    inv.period_end = _parse_date_or_none(request.form.get("period_end", ""))
    inv.biller_data = {
        "name": biller_name,
        "email": request.form["biller_email"].strip(),
        "address": request.form["biller_address"].strip(),
        "country": request.form.get("biller_country", "").strip(),
    }
    inv.client_data = {
        "name": request.form["client_name"].strip(),
        "email": request.form.get("client_email", "").strip(),
        "address": request.form.get("client_address", "").strip(),
        "country": request.form.get("client_country", "").strip(),
    }
    inv.bank_data = {
        "account_name": request.form.get("account_name", "").strip(),
        "name": request.form.get("bank_name", "").strip(),
        "account_number": request.form.get("account_number", "").strip(),
        "routing_number": request.form.get("routing_number", "").strip(),
        "account_address": request.form.get("account_address", "").strip(),
        "account_type": request.form.get("account_type", "").strip(),
    }
    inv.total = sum((amt for _, amt in parsed_items), Decimal("0"))

    # Replace line items wholesale (handles add/remove/reorder cleanly).
    for item in list(inv.line_items):
        db.session.delete(item)
    db.session.flush()
    for idx, (desc, amt) in enumerate(parsed_items):
        db.session.add(
            InvoiceLineItem(
                invoice_id=inv.id,
                position=idx,
                description=desc,
                amount=amt,
            )
        )

    db.session.commit()
    flash("Invoice updated.", "success")
    return redirect(url_for("invoices.view_invoice", invoice_id=inv.id))
