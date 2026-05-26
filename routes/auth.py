from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from extensions import db, limiter
from forms import (
    ForgotPasswordForm,
    LoginForm,
    ResetPasswordForm,
    SignupForm,
    VerifyCodeForm,
)
from mailer import send_password_reset_email, send_verification_email
from models import User

bp = Blueprint("auth", __name__)

PASSWORD_RESET_TTL_SECONDS = 60 * 60  # 1 hour
_RESET_TOKEN_SALT = "password-reset-v1"


def _reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_RESET_TOKEN_SALT)


def _mask_email(email: str) -> str:
    """Mask an email for display, e.g. 'oluwaseyi@gmail.com' -> 'o***i@gmail.com'."""
    if not email or "@" not in email:
        return email or ""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return "*" * len(local) + "@" + domain
    return local[0] + "***" + local[-1] + "@" + domain


def _is_safe_next_url(target: str) -> bool:
    """Allow only same-origin paths. Reject absolute URLs, protocol-relative paths, and backslash tricks."""
    if not target:
        return False
    if "\\" in target:
        return False
    if target.startswith("//"):
        return False
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    return target.startswith("/")


def _send_code(user: User) -> bool:
    """Generate a fresh code, persist its hash, and email it. Returns True if email sent."""
    code = user.generate_verification_code()
    db.session.commit()
    try:
        send_verification_email(user.email, user.name, code)
        return True
    except Exception:
        current_app.logger.exception("Failed to send verification email")
        return False


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("invoices.home"))
    form = SignupForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data,
            name=form.name.data.strip(),
            invoice_counters={},
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        if not _send_code(user):
            flash(
                "We couldn't send your verification email. Try resending below.",
                "error",
            )
        return redirect(url_for("auth.verify"))
    return render_template("auth/signup.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("invoices.home"))
    form = LoginForm()
    if form.validate_on_submit():
        normalized = (form.email.data or "").strip().lower()
        user = User.query.filter_by(email=normalized).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login"))
        login_user(user, remember=form.remember.data)
        next_url = request.args.get("next") or ""
        if not _is_safe_next_url(next_url):
            next_url = url_for("invoices.home")
        return redirect(next_url)
    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/verify", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", methods=["POST"])
def verify():
    if current_user.email_verified:
        return redirect(url_for("invoices.home"))
    form = VerifyCodeForm()
    if form.validate_on_submit():
        if current_user.verify_code(form.code.data):
            db.session.commit()
            flash("Email verified.", "success")
            return redirect(url_for("invoices.home"))
        flash("Invalid or expired code. Try again or resend.", "error")
    return render_template("auth/verify.html", form=form, email=current_user.email)


@bp.route("/forgot", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot():
    if current_user.is_authenticated:
        return redirect(url_for("invoices.home"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        normalized = (form.email.data or "").strip().lower()
        user = User.query.filter_by(email=normalized).first()
        if user is not None:
            token = _reset_serializer().dumps(user.id)
            reset_link = url_for("auth.reset", token=token, _external=True)
            try:
                send_password_reset_email(user.email, user.name, reset_link)
            except Exception:
                current_app.logger.exception("Failed to send password reset email")
        # Same response whether or not the email exists — no enumeration.
        flash(
            "If an account exists for that email, we just sent a reset link. "
            "Check your inbox.",
            "success",
        )
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html", form=form)


@bp.route("/reset/<token>", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def reset(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("invoices.home"))
    try:
        uid = _reset_serializer().loads(token, max_age=PASSWORD_RESET_TTL_SECONDS)
    except SignatureExpired:
        flash("This password reset link has expired. Request a new one.", "error")
        return redirect(url_for("auth.forgot"))
    except BadSignature:
        flash("Invalid password reset link.", "error")
        return redirect(url_for("auth.forgot"))

    user = db.session.get(User, uid)
    if user is None:
        flash("That account no longer exists.", "error")
        return redirect(url_for("auth.forgot"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Password updated. Sign in with your new password.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", form=form, email=_mask_email(user.email))


@bp.route("/verify/resend", methods=["POST"])
@login_required
@limiter.limit("3 per hour")
def resend_code():
    if current_user.email_verified:
        return redirect(url_for("invoices.home"))
    if _send_code(current_user):
        flash("New code sent. Check your inbox.", "success")
    else:
        flash("Couldn't send email. Try again in a moment.", "error")
    return redirect(url_for("auth.verify"))
