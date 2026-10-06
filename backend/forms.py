"""Validazione sul server, condivisa dai form HTML e dalla API segnalazioni."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional


def strip_text(value):
    return value.strip() if isinstance(value, str) else ""


def normalize_email(value):
    return strip_text(value).lower()


class LoginForm(FlaskForm):
    email = StringField("Email", filters=[normalize_email], validators=[
        DataRequired("Inserisci l'email."), Email("Inserisci un'email valida."), Length(max=254)
    ])
    password = PasswordField("Password", validators=[
        DataRequired("Inserisci la password."), Length(max=128)
    ])


class RegisterForm(LoginForm):
    nome = StringField("Nome", filters=[strip_text], validators=[
        DataRequired("Inserisci il nome."), Length(max=100)
    ])
    cognome = StringField("Cognome", filters=[strip_text], validators=[
        DataRequired("Inserisci il cognome."), Length(max=100)
    ])
    password = PasswordField("Password", validators=[
        DataRequired("Inserisci la password."),
        Length(min=12, max=128, message="Usa una password da 12 a 128 caratteri.")
    ])
    password_confirm = PasswordField("Conferma password", validators=[
        DataRequired("Ripeti la password."),
        EqualTo("password", message="Le password non coincidono.")
    ])


class ReportForm(FlaskForm):
    tipo = SelectField("Tipo", choices=[
        ("segnalazione", "Segnalazione"), ("proposta", "Proposta")
    ], validators=[DataRequired("Scegli il tipo.")])
    titolo = StringField("Titolo", filters=[strip_text], validators=[
        DataRequired("Inserisci il titolo."),
        Length(min=3, max=200, message="Il titolo deve contenere da 3 a 200 caratteri.")
    ])
    descrizione = TextAreaField("Descrizione", filters=[strip_text], validators=[
        DataRequired("Inserisci la descrizione."),
        Length(min=10, max=5000, message="La descrizione deve contenere da 10 a 5000 caratteri.")
    ])
    indirizzo = StringField("Indirizzo (facoltativo)", filters=[strip_text], validators=[
        Optional(), Length(max=255, message="L'indirizzo non può superare 255 caratteri.")
    ])

    def report_data(self):
        # Non includiamo campi extra inviati dal browser (autore, stato, visibilità...).
        return {name: self[name].data for name in ("tipo", "titolo", "descrizione", "indirizzo")}
