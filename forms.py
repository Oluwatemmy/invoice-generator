from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    ValidationError,
)

from models import User


class SignupForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=255)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    confirm = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )

    def validate_email(self, field):
        normalized = (field.data or "").strip().lower()
        existing = User.query.filter_by(email=normalized).first()
        if existing:
            raise ValidationError("An account with that email already exists.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class VerifyCodeForm(FlaskForm):
    code = StringField(
        "Verification code",
        validators=[DataRequired(), Length(min=6, max=6)],
    )


class _PartyForm(FlaskForm):
    """Shared fields for Client and TeamMember."""

    name = StringField("Name", validators=[DataRequired(), Length(max=255)])
    email = StringField(
        "Email", validators=[Optional(), Email(), Length(max=255)]
    )
    address = TextAreaField("Address", validators=[Optional()])
    country = StringField("Country", validators=[Optional(), Length(max=120)])


class ClientForm(_PartyForm):
    pass


class TeamMemberForm(_PartyForm):
    pass


class BankProfileForm(FlaskForm):
    label = StringField(
        "Label", validators=[DataRequired(), Length(max=255)],
        description="A short name to recognize this profile (e.g. 'Chase Checking').",
    )
    account_name = StringField(
        "Account name", validators=[Optional(), Length(max=255)]
    )
    bank_name = StringField(
        "Bank name", validators=[Optional(), Length(max=255)]
    )
    account_number = StringField(
        "Account number", validators=[Optional(), Length(max=120)]
    )
    routing_number = StringField(
        "Routing number", validators=[Optional(), Length(max=120)]
    )
    account_address = TextAreaField("Account address", validators=[Optional()])
    account_type = SelectField(
        "Account type",
        choices=[("", "—"), ("Checking", "Checking"), ("Savings", "Savings")],
        validators=[Optional()],
    )
