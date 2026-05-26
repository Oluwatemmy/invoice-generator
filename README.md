# Invoice Generator

A self-hostable Flask app for generating clean, Resend-style invoices. Sign up, save your clients and bank details, then create and track invoices with one-click duplicate and paid/unpaid status. Print to PDF via your browser — no PDF library required.

---

## Features

**Core**
- Sign up / log in / log out — your data is isolated per account
- Email verification on signup (6-digit code via Resend, 15-min TTL, rate-limited)
- Forgot password flow — emailed reset link with 1-hour TTL
- One-page invoice form with multiple line items (auto-summed total)
- Resend-style invoice layout — clean, professional, A4 print-ready

**Speed-up workflows**
- **Saved clients** — pick from a dropdown instead of retyping
- **Saved team members** — for the "From" side when multiple people bill
- **Saved bank profiles** — for the bank details section
- **"Save as new"** checkboxes on the form — persist a one-off entry into the saved list
- **Duplicate** any past invoice with one click; form pre-fills with the prior data

**Tracking**
- **Dashboard** — total billed / paid / outstanding with counts + recent invoices
- **Invoice history** at `/invoices` with paid/unpaid filter
- **Paid/Unpaid toggle** — flip status from the list or the invoice page
- **Auto-generated invoice numbers** — format `{INITIALS}-{YEAR}-{NNNN}`, per-user counter

**Production-ready**
- **SQLite for local dev, Postgres in production** — same code, `DATABASE_URL` decides
- CSRF protection on all forms
- Password hashing via Werkzeug
- Env-var secrets (no hardcoded credentials)
- Print-friendly CSS — fits one A4 page with typical content

---

## Quick start

### Requirements
- Python 3.10+
- A modern browser

### Setup (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

On macOS/Linux, swap the activate line for `source .venv/bin/activate` and copy → `cp`.

Optionally edit `.env` to set a real `SECRET_KEY` (generate with `python -c "import secrets; print(secrets.token_hex(32))"`). The default works for local dev.

### Run

```powershell
python app.py
```

Open <http://127.0.0.1:5000>. You'll be redirected to the login page — create an account, then you're in.

---

## How it works

### First time

1. Sign up with email + password → land on the empty dashboard
2. (Optional) Add a few saved entities to skip retyping later:
   - **Team** → add yourself (name, email, address — used as the "From" on invoices)
   - **Clients** → add the people you bill
   - **Banks** → add a payment profile (account number, routing, etc.)

### Creating an invoice

1. Click **+ New invoice**
2. Pick a saved team member from the **From** dropdown (or type fresh)
3. Pick a saved client from the **Bill to** dropdown (or type fresh)
4. Fill in dates, description(s), amount(s) — add more line items with **+ Add line**
5. Pick a saved bank profile from the **Bank details** dropdown (or type fresh, or leave blank)
6. Optionally tick any "Save as new …" checkbox to persist your typed info for next time
7. Click **Generate Invoice** → land on the rendered invoice page

### Print to PDF

On the invoice page, click **Print to PDF** → your browser's print dialog opens → choose "Save as PDF".

> **Tip:** In Chrome/Edge's print dialog → **More settings** → uncheck **"Headers and footers"** to remove the auto-added date/URL/page numbers. The setting is sticky.

### Tracking & re-use

- **Dashboard** (`/`) shows total billed, paid, outstanding + the last 5 invoices
- **Invoices** (`/invoices`) lists everything, filter by Paid / Unpaid via the chips
- From either page:
  - **View** opens the full invoice (printable)
  - **Mark paid / Mark unpaid** flips status (no page reload navigation hop)
  - **Duplicate** opens a new-invoice form pre-filled with that invoice's data — adjust dates/amounts and submit

---

## Invoice numbering

Format: **`{INITIALS}-{YEAR}-{NNNN}`** — e.g. `TD-2026-0007`

- **INITIALS** — first letter of each word in the From name, uppercased, max 3 (`Tolga Doksanbir` → `TD`)
- **YEAR** — current calendar year
- **NNNN** — zero-padded sequential counter, **per user, per year**

The counter is stored in `users.invoice_counters` as a JSON column keyed by year (e.g. `{"2026": 7}`). To reset, edit the user row directly or open the database.

---

## Project structure

```
invoice-generator/
├── app.py                       # create_app() factory + entry point
├── extensions.py                # db, login_manager, csrf init
├── models.py                    # SQLAlchemy models
├── forms.py                     # Flask-WTF form classes
├── routes/
│   ├── auth.py                  # /signup, /login, /logout
│   ├── invoices.py              # /, /new, /generate, /invoices, /invoices/<id>, …
│   ├── clients.py               # /clients/* CRUD
│   ├── team_members.py          # /team/* CRUD
│   └── bank_profiles.py         # /bank-profiles/* CRUD
├── templates/
│   ├── base.html                # Shared shell + top nav
│   ├── dashboard.html
│   ├── auth/
│   │   ├── login.html
│   │   └── signup.html
│   ├── form.html                # The invoice form (handles new + duplicate flows)
│   ├── invoice.html             # Rendered invoice (Resend-style, print-friendly)
│   ├── invoices_list.html
│   ├── clients_list.html        # + client_form.html
│   ├── team_list.html           # + team_form.html
│   └── bank_list.html           # + bank_form.html
├── static/
│   └── style.css                # All styling (screen + @media print)
├── instance/                    # Auto-created. Holds SQLite DB. Gitignored.
│   └── invoices.db
├── .env                         # Local secrets (gitignored)
├── .env.example                 # Template — commit this
├── requirements.txt
└── README.md
```

---

## Database

SQLAlchemy + SQLite for dev, Postgres for prod. The `DATABASE_URL` env var picks the backend:

- **Unset** → SQLite at `instance/invoices.db` (default for local dev)
- **`postgresql://...`** → Postgres (used in production)

Schema (all per-user where applicable):

- `users` — id, email, password_hash, name, invoice_counters (JSON)
- `clients` — id, user_id, name, email, address, country
- `team_members` — id, user_id, name, email, address, country
- `bank_profiles` — id, user_id, label, account_name, bank_name, account_number, routing_number, account_address, account_type
- `invoices` — id, user_id, invoice_number, issue_date, due_date, biller_data (JSON snapshot), client_data (JSON snapshot), bank_data (JSON snapshot), total, status
- `invoice_line_items` — id, invoice_id, position, description, amount

> **Why JSON snapshots?** Past invoices need to show what the client/biller/bank info looked like at the moment of creation. If you later edit a saved client, you don't want their old invoices to retroactively change. The saved-entity tables exist only to speed up filling out *new* invoices.

Schema is managed by **Alembic** via [Flask-Migrate](https://flask-migrate.readthedocs.io/). The first migration creates every table; new model changes get their own migration.

### Migration workflow

```powershell
# First-time setup on a fresh DB (local or prod): apply all migrations
flask --app app:create_app db upgrade

# After you change a model in models.py:
flask --app app:create_app db migrate -m "Describe the change"
flask --app app:create_app db upgrade

# Check the current revision a DB is at
flask --app app:create_app db current

# Roll back one revision
flask --app app:create_app db downgrade -1
```

On production, the [`Procfile`](Procfile) runs `flask db upgrade` automatically before each release on Render/Railway/Heroku.

> Already had a DB before Alembic landed? It's been stamped at the initial revision (`b104108bb31f`). Future model changes just need a new migration on top.

---

## Tech stack

- **Backend:** Python 3.10+, [Flask](https://flask.palletsprojects.com/), [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/), [Flask-Login](https://flask-login.readthedocs.io/), [Flask-WTF](https://flask-wtf.readthedocs.io/) (CSRF), [psycopg](https://www.psycopg.org/) (Postgres driver)
- **Templates:** Jinja2 (Flask's default)
- **Styling:** Plain CSS — no preprocessor, no framework
- **JavaScript:** Vanilla JS, just for the form's dynamic line items and saved-entity picker auto-fill
- **PDF output:** Browser's native print-to-PDF — no PDF library needed
- **Config:** Env vars via `python-dotenv` (loads `.env` automatically in dev)

---

## Deploying to production

The same code that ran on SQLite locally runs on Postgres in production. Generic recipe:

1. Provision a Postgres database (Neon, Supabase, Render, Railway — all have free tiers).
2. Set env vars on your host:
   - `FLASK_ENV=production` — turns on prod cookie flags + ProxyFix
   - `SECRET_KEY` — a real random string (`python -c "import secrets; print(secrets.token_hex(32))"`)
   - `DATABASE_URL` — connection string from your provider
   - `RESEND_API_KEY` + `FROM_EMAIL` — for verification & reset emails
3. The included `Procfile` handles the rest:
   - `release: flask --app app:create_app db upgrade` — runs migrations on each deploy
   - `web: gunicorn 'app:create_app()' ...` — boots the server
4. Open the deployed URL, sign up, and you're live.

---

## Customization

| What | Where | How |
|---|---|---|
| Accent color | [static/style.css](static/style.css) | Edit `--accent`, `--accent-hover`, `--accent-soft`, `--accent-ring` in `:root` |
| Invoice number format | [models.py](models.py) → `User.next_invoice_number` | Change the format string or how initials are derived |
| Default due date | [routes/invoices.py](routes/invoices.py) → `_form_context` | Currently `today + 14 days` |
| Currency | [routes/invoices.py](routes/invoices.py) + [templates/invoice.html](templates/invoice.html) | Replace `USD` and `$` (no per-invoice currency picker yet) |
| Print page size / margins | [static/style.css](static/style.css) → `@media print { @page { … } }` | A4 by default |
| Account-type options | [forms.py](forms.py) → `BankProfileForm.account_type.choices` | Currently `Checking` / `Savings` |

---

## FAQ

**Can multiple people share one instance?**
Yes — sign up gives each person their own isolated invoices, clients, team members, and bank profiles. The auth flow keeps them separated.

**What if I add a model field?**
You'll need to update the DB. Easiest path: delete `instance/invoices.db` (in dev) so it gets recreated. For production, add Alembic for migrations.

**Why no email-the-invoice feature?**
Out of scope for this iteration. It would require SMTP credentials and a PDF library. Browser-print-to-PDF + manual email works fine for low volume.

**Local emails fail with `SSLCertVerificationError` on Windows.**
Python on Windows sometimes can't validate Resend's TLS cert. For local dev, set `MAIL_TO_CONSOLE=1` in `.env` to print emails to your terminal instead of calling Resend. Production on Linux is fine.

**The invoice overflows to 2 pages when printing.**
Typical 1–3 line-item invoices fit on one A4 page. With many items (4+), reduce font sizes in `@media print` or split into multiple invoices.

---

## License

MIT (or your choice — add a `LICENSE` file).
