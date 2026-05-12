from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from extensions import db
from forms import BankProfileForm
from models import BankProfile

bp = Blueprint("bank_profiles", __name__, url_prefix="/bank-profiles")


def _own_or_404(profile_id: int) -> BankProfile:
    profile = BankProfile.query.filter_by(
        id=profile_id, user_id=current_user.id
    ).first()
    if profile is None:
        abort(404)
    return profile


def _duplicate_of(label: str, account_number: str, exclude_id: int | None = None) -> BankProfile | None:
    """A bank profile is a duplicate if it shares the same label OR the same account number (when present)."""
    label_match = func.lower(BankProfile.label) == label.strip().lower()
    conditions = [label_match]
    account_number = (account_number or "").strip()
    if account_number:
        conditions.append(BankProfile.account_number == account_number)
    q = BankProfile.query.filter(
        BankProfile.user_id == current_user.id,
        or_(*conditions),
    )
    if exclude_id is not None:
        q = q.filter(BankProfile.id != exclude_id)
    return q.first()


@bp.route("/")
@login_required
def index():
    items = (
        BankProfile.query.filter_by(user_id=current_user.id)
        .order_by(BankProfile.label)
        .all()
    )
    return render_template("bank_list.html", profiles=items)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = BankProfileForm()
    if form.validate_on_submit():
        dup = _duplicate_of(form.label.data, form.account_number.data)
        if dup:
            flash(
                f"A bank profile with the same label or account number already exists ('{dup.label}').",
                "error",
            )
            return render_template("bank_form.html", form=form, mode="new")
        profile = BankProfile(user_id=current_user.id)
        form.populate_obj(profile)
        db.session.add(profile)
        db.session.commit()
        return redirect(url_for("bank_profiles.index"))
    return render_template("bank_form.html", form=form, mode="new")


@bp.route("/<int:profile_id>/edit", methods=["GET", "POST"])
@login_required
def edit(profile_id: int):
    profile = _own_or_404(profile_id)
    form = BankProfileForm(obj=profile)
    if form.validate_on_submit():
        dup = _duplicate_of(form.label.data, form.account_number.data, exclude_id=profile.id)
        if dup:
            flash(
                f"A bank profile with the same label or account number already exists ('{dup.label}').",
                "error",
            )
            return render_template("bank_form.html", form=form, mode="edit", item=profile)
        form.populate_obj(profile)
        db.session.commit()
        return redirect(url_for("bank_profiles.index"))
    return render_template(
        "bank_form.html", form=form, mode="edit", item=profile
    )


@bp.route("/<int:profile_id>/delete", methods=["POST"])
@login_required
def delete(profile_id: int):
    profile = _own_or_404(profile_id)
    db.session.delete(profile)
    db.session.commit()
    return redirect(url_for("bank_profiles.index"))
