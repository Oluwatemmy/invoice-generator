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

from extensions import db
from forms import LoginForm, SignupForm, VerifyCodeForm
from mailer import send_verification_email
from models import User

bp = Blueprint("auth", __name__)


def _send_code(user: User) -> bool:
    """Generate a fresh code, persist, and email it. Returns True if email sent."""
    code = user.generate_verification_code()
    db.session.commit()
    try:
        send_verification_email(user.email, user.name, code)
        return True
    except Exception:
        current_app.logger.exception("Failed to send verification email")
        return False


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("invoices.home"))
    form = SignupForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data.lower().strip(),
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
def login():
    if current_user.is_authenticated:
        return redirect(url_for("invoices.home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login"))
        login_user(user, remember=form.remember.data)
        next_url = request.args.get("next")
        if not next_url or urlparse(next_url).netloc != "":
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


@bp.route("/verify/resend", methods=["POST"])
@login_required
def resend_code():
    if current_user.email_verified:
        return redirect(url_for("invoices.home"))
    if _send_code(current_user):
        flash("New code sent. Check your inbox.", "success")
    else:
        flash("Couldn't send email. Try again in a moment.", "error")
    return redirect(url_for("auth.verify"))
