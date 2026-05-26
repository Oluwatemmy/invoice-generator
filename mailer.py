"""Email sending via Resend."""
import os

import resend


def _mail_to_console() -> bool:
    """When MAIL_TO_CONSOLE=1, print emails to stdout instead of calling Resend.
    Useful for local dev on machines where Resend's TLS can't be verified."""
    return os.environ.get("MAIL_TO_CONSOLE", "").strip().lower() in {"1", "true", "yes"}


def _send(payload: dict) -> None:
    """Send an email — either via Resend or printed to console in dev."""
    if _mail_to_console():
        print("\n" + "=" * 60)
        print(f"  MAIL TO:    {payload['to']}")
        print(f"  FROM:       {payload['from']}")
        print(f"  SUBJECT:    {payload['subject']}")
        print("-" * 60)
        print(payload.get("text") or "")
        print("=" * 60 + "\n", flush=True)
        return
    resend.Emails.send(payload)


def _client_ready() -> tuple[str, str]:
    api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("FROM_EMAIL")
    # In console mode we still want a sender address, but the API key can be a stub.
    if not from_email:
        raise RuntimeError("FROM_EMAIL env var is not set.")
    if not _mail_to_console():
        if not api_key:
            raise RuntimeError("RESEND_API_KEY env var is not set.")
        resend.api_key = api_key
    return from_email, api_key or ""


def send_verification_email(to_email: str, name: str, code: str) -> None:
    from_email, _ = _client_ready()
    first_name = (name or "").split(" ", 1)[0] or "there"

    html = f"""<!doctype html>
<html>
  <body style="font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #f5f5f7; padding: 32px; margin: 0;">
    <div style="max-width: 480px; margin: 0 auto; background: #fff; padding: 36px 32px; border-radius: 12px; border: 1px solid #e5e7eb;">
      <h1 style="font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 12px; letter-spacing: -0.01em;">
        Verify your email
      </h1>
      <p style="font-size: 14px; color: #334155; margin: 0 0 28px; line-height: 1.55;">
        Hi {first_name}, enter this code in the verification page to finish setting up your account.
      </p>
      <div style="font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 32px; font-weight: 700; color: #4f46e5; letter-spacing: 0.18em; padding: 18px 0; background: #eef2ff; border-radius: 10px; text-align: center; margin: 0 0 24px;">
        {code}
      </div>
      <p style="font-size: 13px; color: #64748b; margin: 0; line-height: 1.55;">
        This code expires in 15 minutes. If you didn't sign up, just ignore this email.
      </p>
    </div>
  </body>
</html>"""

    text = (
        f"Hi {first_name},\n\n"
        f"Your verification code is: {code}\n\n"
        f"It expires in 15 minutes.\n\n"
        f"If you didn't sign up, just ignore this email."
    )

    _send({
        "from": from_email,
        "to": to_email,
        "subject": "Your verification code",
        "html": html,
        "text": text,
    })


def send_password_reset_email(to_email: str, name: str, reset_link: str) -> None:
    from_email, _ = _client_ready()
    first_name = (name or "").split(" ", 1)[0] or "there"

    html = f"""<!doctype html>
<html>
  <body style="font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #f5f5f7; padding: 32px; margin: 0;">
    <div style="max-width: 480px; margin: 0 auto; background: #fff; padding: 36px 32px; border-radius: 12px; border: 1px solid #e5e7eb;">
      <h1 style="font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 12px; letter-spacing: -0.01em;">
        Reset your password
      </h1>
      <p style="font-size: 14px; color: #334155; margin: 0 0 24px; line-height: 1.55;">
        Hi {first_name}, click the button below to choose a new password. The link expires in 1 hour.
      </p>
      <div style="margin: 0 0 28px;">
        <a href="{reset_link}" style="display: inline-block; background: #4f46e5; color: #fff; text-decoration: none; font-weight: 600; font-size: 14px; padding: 12px 22px; border-radius: 8px;">
          Reset password
        </a>
      </div>
      <p style="font-size: 13px; color: #64748b; margin: 0 0 8px; line-height: 1.55;">
        Or copy and paste this URL into your browser:
      </p>
      <p style="font-size: 12px; color: #475569; margin: 0 0 24px; line-height: 1.55; word-break: break-all;">
        {reset_link}
      </p>
      <p style="font-size: 13px; color: #64748b; margin: 0; line-height: 1.55;">
        If you didn't request this, you can safely ignore this email — your password won't change.
      </p>
    </div>
  </body>
</html>"""

    text = (
        f"Hi {first_name},\n\n"
        f"Use this link to reset your password (expires in 1 hour):\n"
        f"{reset_link}\n\n"
        f"If you didn't request this, you can safely ignore this email."
    )

    _send({
        "from": from_email,
        "to": to_email,
        "subject": "Reset your password",
        "html": html,
        "text": text,
    })
