# Invoice Generator

A minimal Flask app for generating clean, Resend-style invoices. Fill in a form, get a printable invoice, save it as a PDF via your browser. No external PDF library, no database, no accounts.

Built for freelancers and small teams who want to bill clients quickly without signing up for a SaaS.

---

## Features

- **One-page flow** — Home → Form → Rendered invoice → Print
- **Multi-line items** — add as many `Description + Amount` rows as you need; totals sum automatically
- **Auto-generated invoice numbers** — format `{INITIALS}-{YEAR}-{NNNN}`, where initials come from the biller's name and the counter persists across sessions
- **Editable date of issue** — defaults to today, but you can backdate or forward-date
- **Service period** — optional date range that appears in the invoice metadata
- **Bank details section** — Account name, Bank name, Account number, Routing number, Account type, Account address (all optional, individually hidden when blank)
- **Multi-biller support** — the From info is typed per invoice, so any team member can use the same instance
- **Print-friendly** — `@media print` rules compress spacing so the invoice fits on a single A4 page
- **Zero install on the client** — open in any modern browser, save to PDF via the native print dialog

---

## Quick start

### Requirements
- Python 3.10+
- A modern browser (Chrome, Edge, Firefox, Safari)

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

(On macOS/Linux, replace the activation line with `source .venv/bin/activate`.)

### Run

```powershell
python app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## How it works

1. **Home** ([/](http://127.0.0.1:5000)) — A landing page with a single **"Generate Invoice"** button.
2. **Form** ([/new](http://127.0.0.1:5000/new)) — Four sections:
   - **From** — your name, email, address, country
   - **Bill to** — your client's details
   - **Details** — issue date, due date, optional service period, and one or more line items (`Description + Amount`). A **+ Add line** button inserts more rows; each row has an `×` to remove (hidden when only one line remains).
   - **Bank details** *(optional)* — bank info for the client to pay you
3. **Generate** — Submitting the form POSTs to `/generate`, which:
   - Sums all line items to compute the total
   - Generates the next invoice number from the biller's initials + year + persistent counter
   - Renders the Resend-style invoice
4. **Print to PDF** — On the invoice page, click **Print to PDF** to open the browser's print dialog. Choose **Save as PDF** as the destination.

> **Tip:** In Chrome/Edge's print dialog, expand **More settings** and uncheck **"Headers and footers"** to remove the auto-added date / URL / page numbers. Chrome remembers this setting.

---

## Invoice numbering

Format: **`{INITIALS}-{YEAR}-{NNNN}`** (e.g. `TD-2026-0007`)

- **Initials** — first letter of each word in the From name, uppercased, max 3 characters (`Tolga Doksanbir` → `TD`)
- **Year** — current calendar year
- **NNNN** — zero-padded sequential counter

The counter is stored in `counter.json` at the project root, keyed by year:

```json
{ "2026": 7 }
```

The counter increments by 1 every time an invoice is generated, regardless of who the biller is. To reset, delete `counter.json` (or edit it manually).

---

## Project structure

```
invoice-generator/
├── app.py                 # Flask routes + invoice number/counter logic
├── counter.json           # Persistent invoice counter (auto-created)
├── requirements.txt       # flask
├── README.md
├── templates/
│   ├── base.html          # Shared HTML skeleton
│   ├── home.html          # Landing page
│   ├── form.html          # Input form + line-item JS
│   └── invoice.html       # Rendered invoice
└── static/
    └── style.css          # All styling (screen + print)
```

---

## Customization

All customization happens in a few well-defined places:

| What | Where | How |
|---|---|---|
| Accent color | [static/style.css](static/style.css) | Edit the `--accent`, `--accent-hover`, `--accent-soft`, `--accent-ring` CSS variables in `:root` |
| Invoice number prefix logic | [app.py](app.py) → `_next_invoice_number()` | Change how initials are derived or hardcode a different prefix |
| Default due date | [app.py](app.py) → `new_invoice()` | Currently `today + 14 days`; adjust the `timedelta(days=14)` |
| Currency | [app.py](app.py) → `generate()` and [templates/invoice.html](templates/invoice.html) | Replace `USD` and the `$` symbol |
| Print page size / margins | [static/style.css](static/style.css) → `@media print` | Edit the `@page` block (`size: A4`, `margin: 12mm 14mm`) |
| Top-of-form section labels | [templates/form.html](templates/form.html) | Edit the `<h2>` text in each section |
| Logo content | [templates/invoice.html](templates/invoice.html) | The logo box uses the biller's first letter; change `.logo` background/styling in `static/style.css` |

---

## Tech stack

- **Backend:** Python 3 + [Flask](https://flask.palletsprojects.com/) (single file, ~80 lines)
- **Templates:** Jinja2 (Flask's default)
- **Styling:** Plain CSS with custom properties — no preprocessor, no framework
- **JavaScript:** Vanilla JS, only for the dynamic "+ Add line" / "× Remove" buttons on the form
- **Persistence:** A single JSON file (`counter.json`) for the invoice counter
- **PDF output:** Browser's native print-to-PDF — no `weasyprint`, `reportlab`, or headless Chrome involved

---

## FAQ

**Why no database?**
The only persistent state is a single integer (the invoice counter). A JSON file is simpler than running SQLite or Postgres for one number.

**Why no PDF library?**
Adding `weasyprint` or `wkhtmltopdf` means dealing with native dependencies (GTK/Cairo/Pango on Windows is painful). The browser's print-to-PDF produces identical output from the same HTML/CSS, so the library adds complexity without improving the result.

**Can multiple people use the same instance?**
Yes. The From fields are typed per invoice, so anyone can bill from this app. The counter is shared across all billers — invoices increment globally regardless of who creates them.

**The invoice spills onto two pages when printing.**
If you have many line items (typically 4+), the content may exceed one A4 page. The `@media print` rules in `static/style.css` already compress spacing — for very long invoices, reduce font sizes further or split into multiple invoices.

**Can I email invoices automatically?**
Not currently. That would require integrating a PDF library + an SMTP/Resend/Postmark API. The current setup is intentionally just a browser-driven generator.

---

## License

MIT — see `LICENSE` if included, or feel free to add one.
