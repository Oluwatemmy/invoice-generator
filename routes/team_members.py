from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from forms import TeamMemberForm
from models import TeamMember

bp = Blueprint("team_members", __name__, url_prefix="/team")


def _own_or_404(member_id: int) -> TeamMember:
    member = TeamMember.query.filter_by(
        id=member_id, user_id=current_user.id
    ).first()
    if member is None:
        abort(404)
    return member


def _name_taken(name: str, exclude_id: int | None = None) -> bool:
    q = TeamMember.query.filter(
        TeamMember.user_id == current_user.id,
        func.lower(TeamMember.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        q = q.filter(TeamMember.id != exclude_id)
    return q.first() is not None


@bp.route("/")
@login_required
def index():
    items = (
        TeamMember.query.filter_by(user_id=current_user.id)
        .order_by(TeamMember.name)
        .all()
    )
    return render_template("team_list.html", members=items)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = TeamMemberForm()
    if form.validate_on_submit():
        if _name_taken(form.name.data):
            flash(f"A team member named '{form.name.data.strip()}' already exists.", "error")
            return render_template("team_form.html", form=form, mode="new")
        member = TeamMember(user_id=current_user.id)
        form.populate_obj(member)
        db.session.add(member)
        db.session.commit()
        return redirect(url_for("team_members.index"))
    return render_template("team_form.html", form=form, mode="new")


@bp.route("/<int:member_id>/edit", methods=["GET", "POST"])
@login_required
def edit(member_id: int):
    member = _own_or_404(member_id)
    form = TeamMemberForm(obj=member)
    if form.validate_on_submit():
        if _name_taken(form.name.data, exclude_id=member.id):
            flash(f"A team member named '{form.name.data.strip()}' already exists.", "error")
            return render_template("team_form.html", form=form, mode="edit", item=member)
        form.populate_obj(member)
        db.session.commit()
        return redirect(url_for("team_members.index"))
    return render_template("team_form.html", form=form, mode="edit", item=member)


@bp.route("/<int:member_id>/delete", methods=["POST"])
@login_required
def delete(member_id: int):
    member = _own_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    return redirect(url_for("team_members.index"))
