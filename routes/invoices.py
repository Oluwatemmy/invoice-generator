from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.exc import IntegrityError

# Server-side validation limits.
MAX_LINE_ITEMS = 100
MAX_FIELD_LENGTH = 1000          # for free-text fields (address, etc.)
MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 500
MAX_AMOUNT = Decimal("99999999.99")  # fits Numeric(10, 2)

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
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


def _parse_required_date(s: str | None):
    """Returns (date, None) on success, (None, error_message) on failure."""
    if not s:
        return None, "Missing date."
    try:
        return date.fromisoformat(s), None
    except ValueError:
        return None, "Invalid date."


def _build_invoice_context(inv: Invoice) -> dict:
    biller = dict(inv.biller_data or {})
    biller["initial"] = (biller.get("name") or "?")[:1].upper() or "?"

    bank = dict(inv.bank_data or {})
    # Backwards-compat: older invoices stored the bank name under "name".
    if "bank_name" not in bank and bank.get("name"):
        bank["bank_name"] = bank["name"]

    return {
        "invoice": inv,
        "invoice_number": inv.invoice_number,
        "issue_date": _fmt_long_date(inv.issue_date),
        "due_date": _fmt_long_date(inv.due_date),
        "biller": biller,
        "client": dict(inv.client_data or {}),
        "bank": bank,
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


# ---------- Form parsing ----------


def _parse_invoice_form(form) -> tuple[dict | None, str | None]:
    """Validate and parse the invoice form. Returns (data, None) on success, (None, error) on failure."""
    biller_name = (form.get("biller_name") or "").strip()
    if not biller_name:
        return None, "Biller name is required."
    if len(biller_name) > MAX_NAME_LENGTH:
        return None, f"Biller name must be {MAX_NAME_LENGTH} characters or less."

    biller_email = (form.get("biller_email") or "").strip()
    biller_address = (form.get("biller_address") or "").strip()
    if not biller_email:
        return None, "Biller email is required."
    if len(biller_email) > MAX_NAME_LENGTH:
        return None, f"Biller email must be {MAX_NAME_LENGTH} characters or less."
    if not biller_address:
        return None, "Biller address is required."
    if len(biller_address) > MAX_FIELD_LENGTH:
        return None, f"Biller address must be {MAX_FIELD_LENGTH} characters or less."

    client_name = (form.get("client_name") or "").strip()
    if not client_name:
        return None, "Client name is required."
    if len(client_name) > MAX_NAME_LENGTH:
        return None, f"Client name must be {MAX_NAME_LENGTH} characters or less."

    issue_date, err = _parse_required_date(form.get("issue_date"))
    if err:
        return None, f"Issue date: {err}"
    due_date, err = _parse_required_date(form.get("due_date"))
    if err:
        return None, f"Due date: {err}"
    if due_date < issue_date:
        return None, "Due date cannot be before the issue date."

    period_start = _parse_date_or_none(form.get("period_start") or "")
    period_end = _parse_date_or_none(form.get("period_end") or "")
    if period_start and period_end and period_end < period_start:
        return None, "Service period end cannot be before its start."

    descriptions = form.getlist("description")
    raw_amounts = form.getlist("amount")
    parsed_items: list[tuple[str, Decimal]] = []
    for desc, raw in zip(descriptions, raw_amounts):
        desc = (desc or "").strip()
        raw = (raw or "").strip()
        if not desc or not raw:
            continue
        if len(desc) > MAX_DESCRIPTION_LENGTH:
            return None, f"Line item description must be {MAX_DESCRIPTION_LENGTH} characters or less."
        try:
            amt = Decimal(raw)
        except (InvalidOperation, ValueError, ArithmeticError):
            return None, f"Invalid amount '{raw}' for line item '{desc}'."
        if amt < 0:
            return None, f"Negative amount not allowed for line item '{desc}'."
        if amt > MAX_AMOUNT:
            return None, f"Amount '{raw}' exceeds the {MAX_AMOUNT} maximum."
        parsed_items.append((desc, amt))

    if not parsed_items:
        return None, "At least one line item is required."
    if len(parsed_items) > MAX_LINE_ITEMS:
        return None, f"Too many line items (max {MAX_LINE_ITEMS})."

    total = sum((amt for _, amt in parsed_items), Decimal("0"))
    if total > MAX_AMOUNT:
        return None, f"Invoice total exceeds the {MAX_AMOUNT} maximum."

    biller_data = {
        "name": biller_name,
        "email": biller_email,
        "address": biller_address,
        "country": (form.get("biller_country") or "").strip(),
    }
    client_data = {
        "name": client_name,
        "email": (form.get("client_email") or "").strip(),
        "address": (form.get("client_address") or "").strip(),
        "country": (form.get("client_country") or "").strip(),
    }
    bank_data = {
        "account_name": (form.get("account_name") or "").strip(),
        "bank_name": (form.get("bank_name") or "").strip(),
        "account_number": (form.get("account_number") or "").strip(),
        "routing_number": (form.get("routing_number") or "").strip(),
        "account_address": (form.get("account_address") or "").strip(),
        "account_type": (form.get("account_type") or "").strip(),
    }

    return {
        "biller_name": biller_name,
        "biller_data": biller_data,
        "client_data": client_data,
        "bank_data": bank_data,
        "issue_date": issue_date,
        "due_date": due_date,
        "period_start": period_start,
        "period_end": period_end,
        "line_items": parsed_items,
        "total": total,
    }, None


def _persist_saved_entities(form, biller_data: dict, client_data: dict, bank_data: dict) -> None:
    """Optionally save the typed biller/client/bank as reusable saved entities."""
    if form.get("save_team") and biller_data["name"]:
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
    if form.get("save_client") and client_data["name"]:
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
    if form.get("save_bank") and any(bank_data.values()):
        label = bank_data["bank_name"] or bank_data["account_name"] or "Saved bank"
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
                    bank_name=bank_data["bank_name"],
                    account_number=bank_data["account_number"],
                    routing_number=bank_data["routing_number"],
                    account_address=bank_data["account_address"],
                    account_type=bank_data["account_type"],
                )
            )


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
    total_paid = sum((i.total for i in invoices if i.status == "paid"), Decimal("0"))
    total_unpaid = sum((i.total for i in invoices if i.status == "unpaid"), Decimal("0"))
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
        total_billed_fmt=f"${float(total_billed):,.2f}",
        total_paid_fmt=f"${float(total_paid):,.2f}",
        total_unpaid_fmt=f"${float(total_unpaid):,.2f}",
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
    bank = dict(inv.bank_data or {})
    if "bank_name" not in bank and bank.get("name"):
        bank["bank_name"] = bank["name"]
    prefill = {
        "biller": dict(inv.biller_data or {}),
        "client": dict(inv.client_data or {}),
        "bank": bank,
        "line_items": [
            {"description": item.description, "amount": f"{float(item.amount):.2f}"}
            for item in inv.line_items
        ],
    }
    return render_template("form.html", **_form_context(prefill=prefill))


@bp.route("/generate", methods=["POST"])
@login_required
def generate():
    parsed, err = _parse_invoice_form(request.form)
    if err:
        flash(err, "error")
        return render_template("form.html", **_form_context()), 400

    # Retry on the rare race where two concurrent requests pick the same
    # invoice_number. The unique constraint catches it; refresh + retry.
    for _ in range(3):
        try:
            invoice_number = current_user.next_invoice_number(parsed["biller_name"])
            invoice = Invoice(
                user_id=current_user.id,
                invoice_number=invoice_number,
                issue_date=parsed["issue_date"],
                due_date=parsed["due_date"],
                period_start=parsed["period_start"],
                period_end=parsed["period_end"],
                biller_data=parsed["biller_data"],
                client_data=parsed["client_data"],
                bank_data=parsed["bank_data"],
                total=parsed["total"],
                status="unpaid",
            )
            db.session.add(invoice)
            db.session.flush()

            for idx, (desc, amt) in enumerate(parsed["line_items"]):
                db.session.add(
                    InvoiceLineItem(
                        invoice_id=invoice.id,
                        position=idx,
                        description=desc,
                        amount=amt,
                    )
                )

            _persist_saved_entities(
                request.form,
                parsed["biller_data"],
                parsed["client_data"],
                parsed["bank_data"],
            )

            db.session.commit()
            return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))
        except IntegrityError:
            db.session.rollback()
            db.session.refresh(current_user)

    flash("Couldn't allocate an invoice number. Please try again.", "error")
    return render_template("form.html", **_form_context()), 500


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


@bp.route("/invoices/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id: int):
    inv = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first()
    if inv is None:
        abort(404)
    try:
        from weasyprint import CSS, HTML  # type: ignore
    except ImportError:
        current_app.logger.warning(
            "WeasyPrint not available — server-side PDF unavailable in this environment."
        )
        abort(503)

    html = render_template(
        "invoice.html",
        pdf_mode=True,
        **_build_invoice_context(inv),
    )
    # Apply PDF-specific layout overrides (swap CSS grid for floats etc.)
    pdf_override_path = (
        Path(current_app.static_folder) / "invoice_pdf.css"
        if current_app.static_folder
        else None
    )
    extra_stylesheets = []
    if pdf_override_path and pdf_override_path.exists():
        extra_stylesheets.append(CSS(filename=str(pdf_override_path)))

    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf(
        stylesheets=extra_stylesheets
    )
    filename = f"invoice-{inv.invoice_number}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    flash("Invoice deleted.", "success")
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
        bank = dict(inv.bank_data or {})
        if "bank_name" not in bank and bank.get("name"):
            bank["bank_name"] = bank["name"]
        prefill = {
            "biller": dict(inv.biller_data or {}),
            "client": dict(inv.client_data or {}),
            "bank": bank,
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
    parsed, err = _parse_invoice_form(request.form)
    if err:
        flash(err, "error")
        return redirect(url_for("invoices.edit_invoice", invoice_id=inv.id))

    inv.issue_date = parsed["issue_date"]
    inv.due_date = parsed["due_date"]
    inv.period_start = parsed["period_start"]
    inv.period_end = parsed["period_end"]
    inv.biller_data = parsed["biller_data"]
    inv.client_data = parsed["client_data"]
    inv.bank_data = parsed["bank_data"]
    inv.total = parsed["total"]

    # Replace line items wholesale (handles add/remove/reorder cleanly).
    for item in list(inv.line_items):
        db.session.delete(item)
    db.session.flush()
    for idx, (desc, amt) in enumerate(parsed["line_items"]):
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
