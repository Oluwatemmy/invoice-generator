from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from extensions import db
from forms import ClientForm
from models import Client

bp = Blueprint("clients", __name__, url_prefix="/clients")


def _own_or_404(client_id: int) -> Client:
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first()
    if client is None:
        abort(404)
    return client


def _name_taken(name: str, exclude_id: int | None = None) -> bool:
    q = Client.query.filter(
        Client.user_id == current_user.id,
        func.lower(Client.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        q = q.filter(Client.id != exclude_id)
    return q.first() is not None


@bp.route("/")
@login_required
def index():
    items = (
        Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()
    )
    return render_template("clients_list.html", clients=items)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = ClientForm()
    if form.validate_on_submit():
        if _name_taken(form.name.data):
            flash(f"A client named '{form.name.data.strip()}' already exists.", "error")
            return render_template("client_form.html", form=form, mode="new")
        client = Client(user_id=current_user.id)
        form.populate_obj(client)
        db.session.add(client)
        db.session.commit()
        return redirect(url_for("clients.index"))
    return render_template("client_form.html", form=form, mode="new")


@bp.route("/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def edit(client_id: int):
    client = _own_or_404(client_id)
    form = ClientForm(obj=client)
    if form.validate_on_submit():
        if _name_taken(form.name.data, exclude_id=client.id):
            flash(f"A client named '{form.name.data.strip()}' already exists.", "error")
            return render_template("client_form.html", form=form, mode="edit", item=client)
        form.populate_obj(client)
        db.session.commit()
        return redirect(url_for("clients.index"))
    return render_template("client_form.html", form=form, mode="edit", item=client)


@bp.route("/<int:client_id>/delete", methods=["POST"])
@login_required
def delete(client_id: int):
    client = _own_or_404(client_id)
    db.session.delete(client)
    db.session.commit()
    return redirect(url_for("clients.index"))
