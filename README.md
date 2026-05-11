# Invoice Generator

A simple Flask web app for generating clean, Resend-style invoices. Fill in the form, get a printable invoice, save it as PDF via the browser.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
.venv\Scripts\Activate.ps1
python app.py
```

Then open <http://127.0.0.1:5000> in your browser.

## How it works

1. **Home** → click **Generate Invoice**
2. **Form** → fill in From, Bill to, description, amount, dates
3. **Invoice** → click **Print to PDF** and save via your browser's print dialog

Invoice numbers auto-generate as `{INITIALS}-{YEAR}-{COUNTER}` (e.g. `TD-2026-0001`). The counter is persisted to `counter.json` and increments per year.
