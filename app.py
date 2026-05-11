import json
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, render_template, request

app = Flask(__name__)
COUNTER_FILE = Path(__file__).parent / "counter.json"


def _read_counter() -> dict:
    if not COUNTER_FILE.exists():
        return {}
    with open(COUNTER_FILE) as f:
        return json.load(f)


def _write_counter(data: dict) -> None:
    with open(COUNTER_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _next_invoice_number(biller_name: str) -> str:
    year = str(date.today().year)
    counter = _read_counter()
    next_num = counter.get(year, 0) + 1
    counter[year] = next_num
    _write_counter(counter)

    initials = "".join(word[0] for word in biller_name.split() if word)[:3].upper()
    if not initials:
        initials = "INV"
    return f"{initials}-{year}-{next_num:04d}"


def _fmt_long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _fmt_period(start: str, end: str) -> str:
    if not (start and end):
        return ""
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        return ""
    if s.year == e.year:
        return f"{s.strftime('%b')} {s.day} – {e.strftime('%b')} {e.day}, {e.year}"
    return (
        f"{s.strftime('%b')} {s.day}, {s.year} – "
        f"{e.strftime('%b')} {e.day}, {e.year}"
    )


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/new")
def new_invoice():
    today = date.today()
    return render_template(
        "form.html",
        default_issue=today.isoformat(),
        default_due=(today + timedelta(days=14)).isoformat(),
    )


@app.route("/generate", methods=["POST"])
def generate():
    biller_name = request.form["biller_name"].strip()
    issue_date = date.fromisoformat(request.form["issue_date"])
    due_date = date.fromisoformat(request.form["due_date"])

    descriptions = request.form.getlist("description")
    raw_amounts = request.form.getlist("amount")
    line_items = []
    for desc, raw in zip(descriptions, raw_amounts):
        desc = desc.strip()
        if not desc or not raw:
            continue
        try:
            amt = float(raw)
        except ValueError:
            continue
        line_items.append({
            "description": desc,
            "amount": amt,
            "amount_formatted": f"${amt:,.2f}",
        })

    if not line_items:
        return "At least one line item is required.", 400

    total = sum(item["amount"] for item in line_items)
    total_formatted = f"${total:,.2f}"

    context = {
        "invoice_number": _next_invoice_number(biller_name),
        "issue_date": _fmt_long_date(issue_date),
        "due_date": _fmt_long_date(due_date),
        "biller": {
            "name": biller_name,
            "email": request.form["biller_email"].strip(),
            "address": request.form["biller_address"].strip(),
            "country": request.form.get("biller_country", "").strip(),
            "initial": biller_name[0].upper() if biller_name else "?",
        },
        "client": {
            "name": request.form["client_name"].strip(),
            "email": request.form.get("client_email", "").strip(),
            "address": request.form.get("client_address", "").strip(),
            "country": request.form.get("client_country", "").strip(),
        },
        "line_items": line_items,
        "total_formatted": total_formatted,
        "period_range": _fmt_period(
            request.form.get("period_start", ""),
            request.form.get("period_end", ""),
        ),
        "bank": {
            "account_name": request.form.get("account_name", "").strip(),
            "name": request.form.get("bank_name", "").strip(),
            "account_number": request.form.get("account_number", "").strip(),
            "routing_number": request.form.get("routing_number", "").strip(),
            "account_address": request.form.get("account_address", "").strip(),
            "account_type": request.form.get("account_type", "").strip(),
        },
    }

    return render_template("invoice.html", **context)


if __name__ == "__main__":
    app.run(debug=True)
