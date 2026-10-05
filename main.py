"""
=====================================================================
NEXUS CARE - Plateforme pour Infirmiers et Sages-Femmes
Version : 2.0 — Support PostgreSQL (Neon/Supabase) + SQLite fallback
Monnaie : Dinar Algérien (DZD)
=====================================================================
Lancement local :
    pip install -r requirements.txt
    python app.py

Déploiement Streamlit Cloud / Render / Railway :
    1. Créer une base PostgreSQL (Neon, Supabase, etc.)
    2. Ajouter la variable d'environnement DATABASE_URL
    3. Déployer
=====================================================================
"""

import os
from datetime import datetime, date

from flask import (Flask, render_template_string, redirect, url_for,
                   flash, request, jsonify, abort)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, SubmitField, TextAreaField,
                     FloatField, DateField, SelectField)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional
from werkzeug.security import generate_password_hash, check_password_hash

# Chargement du .env en local (ignoré si absent)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# =====================================================================
# CONFIGURATION BASE DE DONNÉES (PostgreSQL prioritaire, SQLite fallback)
# =====================================================================

def get_database_uri():
    """
    Priorité :
    1. Variable d'environnement DATABASE_URL (Streamlit Secrets, Render, Railway...)
    2. Fichier .env local (DATABASE_URL)
    3. Fallback SQLite avec chemin ABSOLU (mode développement)
    """
    # 1. Essayer les secrets Streamlit (si déployé sur Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'DATABASE_URL' in st.secrets:
            db_url = st.secrets['DATABASE_URL']
            print("✅ Base détectée via Streamlit Secrets")
        else:
            db_url = os.environ.get('DATABASE_URL')
    except ImportError:
        db_url = os.environ.get('DATABASE_URL')

    # 2. Si DATABASE_URL trouvée, la normaliser
    if db_url:
        # SQLAlchemy 1.4+ exige le préfixe "postgresql://" et non "postgres://"
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        print(f"✅ Connexion PostgreSQL/SQLAlchemy externe détectée")
        return db_url

    # 3. Sinon, fallback SQLite avec chemin absolu (évite l'erreur OperationalError)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(BASE_DIR, 'nexus_care.db')
    print(f"⚠️  Aucune DATABASE_URL trouvée. Utilisation de SQLite : {db_path}")
    print(f"    (Les données ne persisteront PAS sur Streamlit Cloud / Render)")
    return f'sqlite:///{db_path}'


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nexus-care-secret-key-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,   # Vérifie la connexion avant chaque requête
    'pool_recycle': 280,      # Recycle les connexions après 280s (limite Neon)
}
app.config['WTF_CSRF_ENABLED'] = True
app.config['CURRENCY'] = 'DZD'

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Veuillez vous connecter.'


# =====================================================================
# MODÈLES
# =====================================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='nurse')
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    wilaya = db.Column(db.String(50))
    commune = db.Column(db.String(50))
    language = db.Column(db.String(5), default='fr')
    verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profile = db.relationship('ProfessionalProfile', backref='user',
                              uselist=False, cascade='all, delete-orphan')
    patients = db.relationship('Patient', backref='owner',
                               cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='practitioner',
                                   cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def initials(self):
        return f"{self.first_name[0]}{self.last_name[0]}".upper()

    @property
    def role_label(self):
        return {'nurse': 'Infirmier(ère)', 'midwife': 'Sage-femme',
                'admin': 'Administrateur'}.get(self.role, self.role)


class ProfessionalProfile(db.Model):
    __tablename__ = 'professional_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        unique=True, nullable=False)
    profession = db.Column(db.String(20))
    speciality = db.Column(db.String(100))
    experience_years = db.Column(db.Integer, default=0)
    bio = db.Column(db.Text)
    hourly_rate = db.Column(db.Float, default=0.0)
    diploma_verified = db.Column(db.Boolean, default=False)
    completion_score = db.Column(db.Integer, default=20)
    rating = db.Column(db.Float, default=0.0)


class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    wilaya = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship('Appointment', backref='patient',
                                   cascade='all, delete-orphan')


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    practitioner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=30)
    type = db.Column(db.String(50))
    location = db.Column(db.String(200))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='scheduled')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Mission(db.Model):
    __tablename__ = 'missions'
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    speciality = db.Column(db.String(100))
    location = db.Column(db.String(200))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    hourly_rate = db.Column(db.Float)
    status = db.Column(db.String(20), default='open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[creator_id])


class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =====================================================================
# FORMULAIRES
# =====================================================================

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    submit = SubmitField('Se connecter')


class RegisterForm(FlaskForm):
    first_name = StringField('Prénom', validators=[DataRequired(), Length(2, 50)])
    last_name = StringField('Nom', validators=[DataRequired(), Length(2, 50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Téléphone', validators=[Optional(), Length(8, 20)])
    role = SelectField('Profession', choices=[('nurse', 'Infirmier(ère)'),
                                               ('midwife', 'Sage-femme')])
    wilaya = StringField('Wilaya', validators=[Optional()])
    password = PasswordField('Mot de passe',
                             validators=[DataRequired(), Length(6, 100)])
    confirm = PasswordField('Confirmer',
                            validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Créer mon compte')


class PatientForm(FlaskForm):
    first_name = StringField('Prénom', validators=[DataRequired()])
    last_name = StringField('Nom', validators=[DataRequired()])
    phone = StringField('Téléphone', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    address = TextAreaField('Adresse', validators=[Optional()])
    wilaya = StringField('Wilaya', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Enregistrer')


class AppointmentForm(FlaskForm):
    patient_id = SelectField('Patient', coerce=int, validators=[DataRequired()])
    date = DateField('Date', validators=[DataRequired()])
    time = StringField('Heure (HH:MM)', validators=[DataRequired()],
                       default='09:00')
    duration_minutes = SelectField('Durée', coerce=int,
                                    choices=[(15, '15 min'), (30, '30 min'),
                                             (45, '45 min'), (60, '1h'),
                                             (90, '1h30')],
                                    default=30)
    type = SelectField('Type', choices=[('consultation', 'Consultation'),
                                         ('soin', 'Soin à domicile'),
                                         ('urgence', 'Urgence')])
    location = StringField('Lieu', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Planifier')


class MissionForm(FlaskForm):
    title = StringField('Titre', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    speciality = StringField('Spécialité', validators=[Optional()])
    location = StringField('Lieu', validators=[Optional()])
    start_date = DateField('Date de début', validators=[DataRequired()])
    end_date = DateField('Date de fin', validators=[DataRequired()])
    hourly_rate = FloatField('Tarif horaire (DZD)', validators=[DataRequired()])
    submit = SubmitField('Publier la mission')


# =====================================================================
# CSS GLOBAL
# =====================================================================

CSS = """
:root {
    --primary: #0066CC; --primary-dark: #004d99; --secondary: #00A86B;
    --danger: #E63946; --warning: #F4A261;
    --bg: #F5F7FA; --card: #FFFFFF; --text: #1F2937;
    --text-light: #6B7280; --border: #E5E7EB;
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
    --shadow-lg: 0 4px 12px rgba(0,0,0,0.1);
    --radius: 10px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: var(--bg); color: var(--text); line-height: 1.6; }
.sidebar { position: fixed; left: 0; top: 0; bottom: 0; width: 240px;
           background: var(--card); border-right: 1px solid var(--border);
           display: flex; flex-direction: column; padding: 1.25rem 0; z-index: 100; }
.logo { display: flex; align-items: center; gap: 0.5rem; padding: 0 1.5rem 1.5rem;
        font-size: 1.25rem; font-weight: 700; color: var(--primary);
        border-bottom: 1px solid var(--border); margin-bottom: 1rem; }
.logo i { font-size: 1.5rem; }
.sidebar nav { flex: 1; display: flex; flex-direction: column; gap: 0.25rem;
               padding: 0 0.75rem; }
.sidebar nav a { display: flex; align-items: center; gap: 0.75rem;
                 padding: 0.75rem 1rem; color: var(--text-light);
                 text-decoration: none; border-radius: var(--radius);
                 font-weight: 500; transition: all 0.2s; }
.sidebar nav a:hover { background: var(--bg); color: var(--primary); }
.sidebar nav a.active { background: var(--primary); color: white; }
.sidebar-footer { padding: 1rem 1.25rem; border-top: 1px solid var(--border); }
.user-info { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }
.avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--primary);
          color: white; display: flex; align-items: center; justify-content: center;
          font-weight: 700; }
.user-name { font-weight: 600; font-size: 0.9rem; }
.user-role { font-size: 0.75rem; color: var(--text-light); }
.logout-btn { display: flex; align-items: center; gap: 0.5rem;
              padding: 0.5rem 0.75rem; color: var(--danger);
              text-decoration: none; border-radius: var(--radius);
              font-size: 0.9rem; }
.logout-btn:hover { background: #fee; }
main { padding: 2rem; max-width: 1400px; margin: 0 auto; }
main.with-sidebar { margin-left: 240px; }
.page-header { display: flex; justify-content: space-between; align-items: center;
               margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; }
.page-header h1 { font-size: 1.75rem; }
.page-header p { color: var(--text-light); }
.flash { padding: 0.75rem 1rem; border-radius: var(--radius); margin-bottom: 0.5rem;
         display: flex; align-items: center; gap: 0.5rem; }
.flash-success { background: #d1fae5; color: #065f46; }
.flash-danger { background: #fee2e2; color: #991b1b; }
.flash-warning { background: #fef3c7; color: #92400e; }
.flash-info { background: #dbeafe; color: #1e40af; }
.card { background: var(--card); border-radius: var(--radius);
        box-shadow: var(--shadow); padding: 1.5rem; margin-bottom: 1.5rem; }
.card-header { display: flex; justify-content: space-between; align-items: center;
               margin-bottom: 1rem; padding-bottom: 1rem;
               border-bottom: 1px solid var(--border); }
.card-header h2 { font-size: 1.1rem; }
.stats-grid { display: grid;
              grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
              gap: 1rem; margin-bottom: 2rem; }
.stat-card { background: var(--card); border-radius: var(--radius);
             padding: 1.25rem; display: flex; align-items: center; gap: 1rem;
             box-shadow: var(--shadow); }
.stat-icon { width: 48px; height: 48px; border-radius: var(--radius);
             display: flex; align-items: center; justify-content: center;
             color: white; font-size: 1.25rem; }
.stat-icon.blue { background: #0066CC; }
.stat-icon.green { background: #00A86B; }
.stat-icon.orange { background: #F4A261; }
.stat-icon.purple { background: #8B5CF6; }
.stat-value { font-size: 1.75rem; font-weight: 700; }
.stat-label { color: var(--text-light); font-size: 0.85rem; }
.grid-2 { display: grid;
          grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
          gap: 1.5rem; }
.list { list-style: none; }
.list-item { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 0;
             border-bottom: 1px solid var(--border); }
.list-item:last-child { border-bottom: none; }
.list-item .time { font-weight: 700; color: var(--primary); min-width: 80px; }
.list-item .info span { display: block; font-size: 0.85rem;
                        color: var(--text-light); }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { padding: 0.75rem 1rem; text-align: left;
                       border-bottom: 1px solid var(--border); }
.table th { background: var(--bg); font-weight: 600; font-size: 0.85rem;
            text-transform: uppercase; color: var(--text-light); }
.badge { padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.75rem;
         font-weight: 600; display: inline-block; }
.badge-scheduled, .badge-open { background: #dbeafe; color: #1e40af; }
.badge-completed { background: #d1fae5; color: #065f46; }
.badge-cancelled { background: #fee2e2; color: #991b1b; }
.badge-assigned { background: #fef3c7; color: #92400e; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; margin-bottom: 0.35rem;
                    font-weight: 500; font-size: 0.9rem; }
.form-control { width: 100%; padding: 0.65rem 0.85rem;
                border: 1px solid var(--border); border-radius: var(--radius);
                font-size: 0.95rem; font-family: inherit;
                transition: border-color 0.2s; background: white; }
.form-control:focus { outline: none; border-color: var(--primary);
                      box-shadow: 0 0 0 3px rgba(0,102,204,0.1); }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.btn { display: inline-flex; align-items: center; justify-content: center;
       gap: 0.5rem; padding: 0.65rem 1.25rem; border: 1px solid var(--border);
       background: var(--card); color: var(--text); border-radius: var(--radius);
       font-size: 0.9rem; font-weight: 500; cursor: pointer;
       text-decoration: none; transition: all 0.2s; font-family: inherit; }
.btn:hover { background: var(--bg); }
.btn-primary { background: var(--primary); color: white;
               border-color: var(--primary); }
.btn-primary:hover { background: var(--primary-dark); }
.btn-success { background: var(--secondary); color: white;
               border-color: var(--secondary); }
.btn-danger { background: var(--danger); color: white;
              border-color: var(--danger); }
.btn-block { width: 100%; }
.btn-sm { padding: 0.4rem 0.75rem; font-size: 0.85rem; }
.auth-container { min-height: 100vh; display: flex; align-items: center;
                  justify-content: center; padding: 2rem;
                  background: linear-gradient(135deg, #0066CC 0%, #00A86B 100%); }
.auth-card { background: white; padding: 2.5rem; border-radius: 16px;
             box-shadow: var(--shadow-lg); width: 100%; max-width: 420px; }
.auth-card.wide { max-width: 700px; }
.auth-logo { text-align: center; margin-bottom: 2rem; }
.auth-logo i { font-size: 3rem; color: var(--primary); }
.auth-logo h1 { margin: 0.5rem 0; color: var(--primary); }
.auth-logo p { color: var(--text-light); font-size: 0.9rem; }
.auth-footer { text-align: center; margin-top: 1.5rem; font-size: 0.9rem; }
.auth-footer a { color: var(--primary); text-decoration: none;
                 font-weight: 600; }
.hint { color: var(--text-light); font-size: 0.8rem; margin-top: 0.5rem; }
.quick-actions { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 2rem; }
.quick-btn { display: flex; align-items: center; gap: 0.5rem;
             padding: 1rem 1.5rem; background: var(--card);
             border: 1px dashed var(--border); border-radius: var(--radius);
             text-decoration: none; color: var(--text); font-weight: 500;
             transition: all 0.2s; }
.quick-btn:hover { border-color: var(--primary); color: var(--primary); }
.missions-grid { display: grid;
                 grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                 gap: 1.25rem; margin-bottom: 2rem; }
.mission-card { background: var(--card); border-radius: var(--radius);
                padding: 1.25rem; box-shadow: var(--shadow);
                border-left: 4px solid var(--primary); }
.mission-card.mine { border-left-color: var(--secondary); }
.mission-header { display: flex; justify-content: space-between;
                  align-items: start; margin-bottom: 0.75rem; gap: 0.5rem; }
.mission-header h3 { font-size: 1.05rem; }
.mission-meta { display: flex; flex-direction: column; gap: 0.35rem;
                margin: 1rem 0; font-size: 0.85rem;
                color: var(--text-light); }
.mission-meta i { color: var(--primary); width: 16px; }
.mission-meta .rate { color: var(--secondary); font-weight: 700;
                      font-size: 1rem; }
.section-title { font-size: 1.1rem; margin: 1.5rem 0 1rem; }
.empty { color: var(--text-light); text-align: center; padding: 2rem;
         font-style: italic; }
.empty a { color: var(--primary); }
.errors { color: var(--danger); font-size: 0.8rem; margin-top: 0.25rem; }
.db-banner { background: #fef3c7; color: #92400e; padding: 0.5rem 1rem;
             border-radius: var(--radius); margin-bottom: 1rem;
             font-size: 0.85rem; text-align: center; }
@media (max-width: 768px) {
    .sidebar { transform: translateX(-100%); transition: transform 0.3s; }
    .sidebar.open { transform: translateX(0); }
    main.with-sidebar { margin-left: 0; }
    .form-row { grid-template-columns: 1fr; }
    .page-header { flex-direction: column; align-items: flex-start; }
    .menu-toggle { display: block !important; }
}
.menu-toggle { display: none; position: fixed; top: 1rem; left: 1rem;
               z-index: 200; background: var(--primary); color: white;
               border: none; padding: 0.5rem 0.75rem;
               border-radius: var(--radius); cursor: pointer; font-size: 1.2rem; }
"""


# =====================================================================
# BASE TEMPLATE
# =====================================================================

BASE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}Nexus Care{% endblock %} — Plateforme Santé</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>{{ css|safe }}</style>
</head>
<body>

{% if show_sidebar and current_user.is_authenticated %}
<button class="menu-toggle" onclick="document.querySelector('.sidebar').classList.toggle('open')">
    <i class="fas fa-bars"></i>
</button>

<aside class="sidebar">
    <div class="logo">
        <i class="fas fa-heart-pulse"></i>
        <span>Nexus Care</span>
    </div>
    <nav>
        <a href="{{ url_for('dashboard') }}" class="{% if request.endpoint == 'dashboard' %}active{% endif %}">
            <i class="fas fa-home"></i> Tableau de bord
        </a>
        <a href="{{ url_for('agenda') }}" class="{% if 'agenda' in (request.endpoint or '') %}active{% endif %}">
            <i class="fas fa-calendar"></i> Agenda
        </a>
        <a href="{{ url_for('patients') }}" class="{% if 'patient' in (request.endpoint or '') %}active{% endif %}">
            <i class="fas fa-users"></i> Patients
        </a>
        <a href="{{ url_for('missions') }}" class="{% if 'mission' in (request.endpoint or '') %}active{% endif %}">
            <i class="fas fa-briefcase"></i> Missions
        </a>
        <a href="{{ url_for('profile') }}" class="{% if request.endpoint == 'profile' %}active{% endif %}">
            <i class="fas fa-user"></i> Profil
        </a>
    </nav>
    <div class="sidebar-footer">
        <div class="user-info">
            <div class="avatar">{{ current_user.initials }}</div>
            <div>
                <div class="user-name">{{ current_user.full_name }}</div>
                <div class="user-role">{{ current_user.role_label }}</div>
            </div>
        </div>
        <a href="{{ url_for('logout') }}" class="logout-btn">
            <i class="fas fa-sign-out-alt"></i> Déconnexion
        </a>
    </div>
</aside>
{% endif %}

<main class="{% if show_sidebar and current_user.is_authenticated %}with-sidebar{% endif %}">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="flash flash-{{ category }}">
                    <i class="fas fa-info-circle"></i> {{ message }}
                </div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    {% block content %}{% endblock %}
</main>

<script>
async function completeAppt(id) {
    if (!confirm('Marquer ce rendez-vous comme terminé ?')) return;
    const res = await fetch('/agenda/' + id + '/complete', { method: 'POST' });
    if (res.ok) location.reload();
}
async function applyMission(id) {
    if (!confirm('Postuler à cette mission ?')) return;
    const res = await fetch('/missions/' + id + '/apply', { method: 'POST' });
    const data = await res.json();
    if (res.ok) { alert('OK : ' + data.message); location.reload(); }
    else { alert('Erreur : ' + (data.error || 'inconnue')); }
}
async function deletePatient(id) {
    if (!confirm('Supprimer ce patient ?')) return;
    const res = await fetch('/patients/' + id + '/delete', { method: 'POST' });
    if (res.ok) location.reload();
}
setTimeout(() => {
    document.querySelectorAll('.flash').forEach(el => {
        el.style.transition = 'opacity 0.5s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 500);
    });
}, 4000);
</script>
</body>
</html>
"""


# =====================================================================
# TEMPLATES
# =====================================================================

LOGIN_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="auth-container">
    <div class="auth-card">
        <div class="auth-logo">
            <i class="fas fa-heart-pulse"></i>
            <h1>Nexus Care</h1>
            <p>La plateforme des infirmiers et sages-femmes</p>
        </div>
        <form method="POST">
            {{ form.hidden_tag() }}
            <div class="form-group">
                <label><i class="fas fa-envelope"></i> Email</label>
                {{ form.email(class="form-control", placeholder="votre@email.dz") }}
                {% for e in form.email.errors %}<div class="errors">{{ e }}</div>{% endfor %}
            </div>
            <div class="form-group">
                <label><i class="fas fa-lock"></i> Mot de passe</label>
                {{ form.password(class="form-control", placeholder="........") }}
            </div>
            <button type="submit" class="btn btn-primary btn-block">
                <i class="fas fa-sign-in-alt"></i> Se connecter
            </button>
        </form>
        <div class="auth-footer">
            <p>Pas encore de compte ? <a href="{{ url_for('register') }}">Créer un compte</a></p>
            <p class="hint">Admin : admin@nexuscare.dz / admin123</p>
        </div>
    </div>
</div>
{% endblock %}""")


REGISTER_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="auth-container">
    <div class="auth-card wide">
        <div class="auth-logo">
            <i class="fas fa-user-plus"></i>
            <h1>Créer un compte</h1>
            <p>Rejoignez la communauté Nexus Care</p>
        </div>
        <form method="POST">
            {{ form.hidden_tag() }}
            <div class="form-row">
                <div class="form-group"><label>Prénom</label>{{ form.first_name(class="form-control") }}</div>
                <div class="form-group"><label>Nom</label>{{ form.last_name(class="form-control") }}</div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>Email</label>{{ form.email(class="form-control") }}</div>
                <div class="form-group"><label>Téléphone</label>{{ form.phone(class="form-control") }}</div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>Profession</label>{{ form.role(class="form-control") }}</div>
                <div class="form-group"><label>Wilaya</label>{{ form.wilaya(class="form-control") }}</div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>Mot de passe</label>{{ form.password(class="form-control") }}</div>
                <div class="form-group"><label>Confirmer</label>{{ form.confirm(class="form-control") }}</div>
            </div>
            <button type="submit" class="btn btn-primary btn-block">
                <i class="fas fa-check"></i> Créer mon compte
            </button>
        </form>
        <div class="auth-footer">
            <p>Déjà inscrit ? <a href="{{ url_for('login') }}">Se connecter</a></p>
        </div>
    </div>
</div>
{% endblock %}""")


DASHBOARD_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
    <div>
        <h1>Bonjour, {{ current_user.first_name }}</h1>
        <p>{{ current_user.wilaya or 'Algérie' }} — {{ current_user.role_label }}</p>
    </div>
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-icon blue"><i class="fas fa-users"></i></div>
        <div><div class="stat-value">{{ stats.total_patients }}</div>
             <div class="stat-label">Patients</div></div>
    </div>
    <div class="stat-card">
        <div class="stat-icon green"><i class="fas fa-calendar-check"></i></div>
        <div><div class="stat-value">{{ stats.today_appointments }}</div>
             <div class="stat-label">RDV aujourd'hui</div></div>
    </div>
    <div class="stat-card">
        <div class="stat-icon orange"><i class="fas fa-briefcase"></i></div>
        <div><div class="stat-value">{{ stats.open_missions }}</div>
             <div class="stat-label">Missions ouvertes</div></div>
    </div>
    <div class="stat-card">
        <div class="stat-icon purple"><i class="fas fa-envelope"></i></div>
        <div><div class="stat-value">{{ stats.unread_messages }}</div>
             <div class="stat-label">Messages</div></div>
    </div>
</div>

<div class="grid-2">
    <div class="card">
        <div class="card-header">
            <h2><i class="fas fa-clock"></i> Rendez-vous du jour</h2>
            <a href="{{ url_for('agenda') }}" class="btn btn-sm">Voir tout</a>
        </div>
        {% if today_appointments %}
            <ul class="list">
            {% for appt in today_appointments %}
                <li class="list-item">
                    <div class="time">{{ appt.date.strftime('%H:%M') }}</div>
                    <div class="info">
                        <strong>{{ appt.patient.first_name }} {{ appt.patient.last_name }}</strong>
                        <span>{{ appt.type }} — {{ appt.duration_minutes }} min</span>
                    </div>
                </li>
            {% endfor %}
            </ul>
        {% else %}
            <p class="empty">Aucun rendez-vous aujourd'hui.</p>
        {% endif %}
    </div>

    <div class="card">
        <div class="card-header"><h2><i class="fas fa-hourglass-half"></i> Prochains RDV</h2></div>
        {% if upcoming %}
            <ul class="list">
            {% for appt in upcoming %}
                <li class="list-item">
                    <div class="time">{{ appt.date.strftime('%d/%m %H:%M') }}</div>
                    <div class="info">
                        <strong>{{ appt.patient.first_name }} {{ appt.patient.last_name }}</strong>
                        <span>{{ appt.type }}</span>
                    </div>
                </li>
            {% endfor %}
            </ul>
        {% else %}
            <p class="empty">Aucun rendez-vous à venir.</p>
        {% endif %}
    </div>
</div>

<div class="quick-actions">
    <a href="{{ url_for('new_patient') }}" class="quick-btn">
        <i class="fas fa-user-plus"></i> Nouveau patient</a>
    <a href="{{ url_for('new_appointment') }}" class="quick-btn">
        <i class="fas fa-calendar-plus"></i> Nouveau RDV</a>
    <a href="{{ url_for('new_mission') }}" class="quick-btn">
        <i class="fas fa-plus-circle"></i> Publier une mission</a>
</div>
{% endblock %}""")


AGENDA_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
    <h1><i class="fas fa-calendar"></i> Mon Agenda</h1>
    <a href="{{ url_for('new_appointment') }}" class="btn btn-primary">
        <i class="fas fa-plus"></i> Nouveau RDV</a>
</div>

<div class="card">
{% if appointments %}
<table class="table">
    <thead>
        <tr><th>Date</th><th>Patient</th><th>Type</th><th>Durée</th>
            <th>Lieu</th><th>Statut</th><th>Actions</th></tr>
    </thead>
    <tbody>
    {% for appt in appointments %}
        <tr>
            <td>{{ appt.date.strftime('%d/%m/%Y %H:%M') }}</td>
            <td>{{ appt.patient.first_name }} {{ appt.patient.last_name }}</td>
            <td>{{ appt.type }}</td>
            <td>{{ appt.duration_minutes }} min</td>
            <td>{{ appt.location or '—' }}</td>
            <td><span class="badge badge-{{ appt.status }}">{{ appt.status }}</span></td>
            <td>
                {% if appt.status == 'scheduled' %}
                <button onclick="completeAppt({{ appt.id }})" class="btn btn-sm btn-success">
                    <i class="fas fa-check"></i>
                </button>
                {% endif %}
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% else %}
<p class="empty">Aucun rendez-vous.
   <a href="{{ url_for('new_appointment') }}">Créer le premier</a></p>
{% endif %}
</div>
{% endblock %}""")


PATIENTS_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
    <h1><i class="fas fa-users"></i> Mes Patients</h1>
    <a href="{{ url_for('new_patient') }}" class="btn btn-primary">
        <i class="fas fa-plus"></i> Nouveau patient</a>
</div>

<div class="card">
{% if patients %}
<table class="table">
    <thead>
        <tr><th>Nom</th><th>Téléphone</th><th>Wilaya</th>
            <th>Ajouté le</th><th>Actions</th></tr>
    </thead>
    <tbody>
    {% for p in patients %}
        <tr>
            <td><strong>{{ p.first_name }} {{ p.last_name }}</strong></td>
            <td>{{ p.phone or '—' }}</td>
            <td>{{ p.wilaya or '—' }}</td>
            <td>{{ p.created_at.strftime('%d/%m/%Y') }}</td>
            <td>
                <button onclick="deletePatient({{ p.id }})" class="btn btn-sm btn-danger">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% else %}
<p class="empty">Aucun patient enregistré.
   <a href="{{ url_for('new_patient') }}">Ajouter le premier</a></p>
{% endif %}
</div>
{% endblock %}""")


MISSIONS_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
    <h1><i class="fas fa-briefcase"></i> Missions & Remplacements</h1>
    <a href="{{ url_for('new_mission') }}" class="btn btn-primary">
        <i class="fas fa-plus"></i> Publier une mission</a>
</div>

<h2 class="section-title">Missions ouvertes</h2>
<div class="missions-grid">
{% for m in missions %}
    <div class="mission-card">
        <div class="mission-header">
            <h3>{{ m.title }}</h3>
            <span class="badge badge-open">{{ m.status }}</span>
        </div>
        <p>{{ m.description or 'Pas de description' }}</p>
        <div class="mission-meta">
            <span><i class="fas fa-map-marker-alt"></i> {{ m.location or '—' }}</span>
            <span><i class="fas fa-calendar"></i> {{ m.start_date }} → {{ m.end_date }}</span>
            <span class="rate"><i class="fas fa-coins"></i> {{ m.hourly_rate }} DZD/h</span>
            <span><i class="fas fa-user"></i> {{ m.creator.full_name }}</span>
        </div>
        <button onclick="applyMission({{ m.id }})" class="btn btn-primary btn-block">
            <i class="fas fa-paper-plane"></i> Postuler
        </button>
    </div>
{% else %}
    <p class="empty">Aucune mission disponible.</p>
{% endfor %}
</div>

{% if my_missions %}
<h2 class="section-title">Mes missions publiées</h2>
<div class="missions-grid">
{% for m in my_missions %}
    <div class="mission-card mine">
        <div class="mission-header">
            <h3>{{ m.title }}</h3>
            <span class="badge badge-{{ m.status }}">{{ m.status }}</span>
        </div>
        <p>{{ m.hourly_rate }} DZD/h — {{ m.location or '—' }}</p>
    </div>
{% endfor %}
</div>
{% endif %}
{% endblock %}""")


PROFILE_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header"><h1><i class="fas fa-user"></i> Mon Profil</h1></div>

<div class="card">
<form method="POST">
    <h2>Informations personnelles</h2>
    <div class="form-row">
        <div class="form-group"><label>Prénom</label>
            <input type="text" name="first_name" value="{{ current_user.first_name }}" class="form-control"></div>
        <div class="form-group"><label>Nom</label>
            <input type="text" name="last_name" value="{{ current_user.last_name }}" class="form-control"></div>
    </div>
    <div class="form-row">
        <div class="form-group"><label>Téléphone</label>
            <input type="text" name="phone" value="{{ current_user.phone or '' }}" class="form-control"></div>
        <div class="form-group"><label>Email</label>
            <input type="email" value="{{ current_user.email }}" class="form-control" disabled></div>
    </div>
    <div class="form-row">
        <div class="form-group"><label>Wilaya</label>
            <input type="text" name="wilaya" value="{{ current_user.wilaya or '' }}" class="form-control"></div>
        <div class="form-group"><label>Commune</label>
            <input type="text" name="commune" value="{{ current_user.commune or '' }}" class="form-control"></div>
    </div>

    {% if profile %}
    <h2 style="margin-top:1.5rem">Profil professionnel</h2>
    <div class="form-row">
        <div class="form-group"><label>Spécialité</label>
            <input type="text" name="speciality" value="{{ profile.speciality or '' }}" class="form-control"></div>
        <div class="form-group"><label>Années d'expérience</label>
            <input type="number" name="experience_years" value="{{ profile.experience_years }}" class="form-control"></div>
    </div>
    <div class="form-group"><label>Tarif horaire (DZD)</label>
        <input type="number" step="50" name="hourly_rate" value="{{ profile.hourly_rate }}" class="form-control"></div>
    <div class="form-group"><label>Bio</label>
        <textarea name="bio" rows="4" class="form-control">{{ profile.bio or '' }}</textarea></div>
    {% endif %}

    <button type="submit" class="btn btn-primary">
        <i class="fas fa-save"></i> Enregistrer</button>
</form>
</div>
{% endblock %}""")


NEW_PATIENT_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header"><h1><i class="fas fa-user-plus"></i> Nouveau patient</h1></div>
<div class="card">
<form method="POST">
    {{ form.hidden_tag() }}
    <div class="form-row">
        <div class="form-group"><label>Prénom</label>{{ form.first_name(class="form-control") }}</div>
        <div class="form-group"><label>Nom</label>{{ form.last_name(class="form-control") }}</div>
    </div>
    <div class="form-row">
        <div class="form-group"><label>Téléphone</label>{{ form.phone(class="form-control") }}</div>
        <div class="form-group"><label>Email</label>{{ form.email(class="form-control") }}</div>
    </div>
    <div class="form-group"><label>Adresse</label>{{ form.address(class="form-control", rows=2) }}</div>
    <div class="form-group"><label>Wilaya</label>{{ form.wilaya(class="form-control") }}</div>
    <div class="form-group"><label>Notes</label>{{ form.notes(class="form-control", rows=3) }}</div>
    <button type="submit" class="btn btn-primary">
        <i class="fas fa-save"></i> Enregistrer</button>
</form>
</div>
{% endblock %}""")


NEW_APPOINTMENT_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header"><h1><i class="fas fa-calendar-plus"></i> Nouveau rendez-vous</h1></div>
<div class="card">
<form method="POST">
    {{ form.hidden_tag() }}
    <div class="form-group"><label>Patient</label>{{ form.patient_id(class="form-control") }}</div>
    <div class="form-row">
        <div class="form-group"><label>Date</label>{{ form.date(class="form-control") }}</div>
        <div class="form-group"><label>Heure (HH:MM)</label>{{ form.time(class="form-control") }}</div>
    </div>
    <div class="form-row">
        <div class="form-group"><label>Durée</label>{{ form.duration_minutes(class="form-control") }}</div>
        <div class="form-group"><label>Type</label>{{ form.type(class="form-control") }}</div>
    </div>
    <div class="form-group"><label>Lieu</label>{{ form.location(class="form-control") }}</div>
    <div class="form-group"><label>Notes</label>{{ form.notes(class="form-control", rows=3) }}</div>
    <button type="submit" class="btn btn-primary">
        <i class="fas fa-save"></i> Planifier</button>
</form>
</div>
{% endblock %}""")


NEW_MISSION_TPL = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header"><h1><i class="fas fa-plus-circle"></i> Publier une mission</h1></div>
<div class="card">
<form method="POST">
    {{ form.hidden_tag() }}
    <div class="form-group"><label>Titre</label>{{ form.title(class="form-control") }}</div>
    <div class="form-group"><label>Description</label>{{ form.description(class="form-control", rows=4) }}</div>
    <div class="form-row">
        <div class="form-group"><label>Spécialité</label>{{ form.speciality(class="form-control") }}</div>
        <div class="form-group"><label>Lieu</label>{{ form.location(class="form-control") }}</div>
    </div>
    <div class="form-row">
        <div class="form-group"><label>Date de début</label>{{ form.start_date(class="form-control") }}</div>
        <div class="form-group"><label>Date de fin</label>{{ form.end_date(class="form-control") }}</div>
    </div>
    <div class="form-group"><label>Tarif horaire (DZD)</label>{{ form.hourly_rate(class="form-control") }}</div>
    <button type="submit" class="btn btn-primary">
        <i class="fas fa-check"></i> Publier</button>
</form>
</div>
{% endblock %}""")


# =====================================================================
# HELPERS DE RENDU
# =====================================================================

def render(template, show_sidebar=True, **ctx):
    return render_template_string(template, css=CSS,
                                  show_sidebar=show_sidebar, **ctx)


# =====================================================================
# ROUTES
# =====================================================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=True)
            flash(f'Bienvenue {user.first_name} !', 'success')
            return redirect(url_for('dashboard'))
        flash('Email ou mot de passe incorrect.', 'danger')
    return render(LOGIN_TPL, show_sidebar=False, form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Cet email est déjà utilisé.', 'danger')
            return render(REGISTER_TPL, show_sidebar=False, form=form)

        user = User(
            email=form.email.data.lower(),
            phone=form.phone.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            role=form.role.data,
            wilaya=form.wilaya.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()

        profile = ProfessionalProfile(
            user_id=user.id,
            profession=form.role.data,
            completion_score=20
        )
        db.session.add(profile)
        db.session.commit()

        login_user(user)
        flash('Compte créé avec succès !', 'success')
        return redirect(url_for('dashboard'))
    return render(REGISTER_TPL, show_sidebar=False, form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous êtes déconnecté.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    total_patients = Patient.query.filter_by(owner_id=current_user.id).count()
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    today_appointments = Appointment.query.filter(
        Appointment.practitioner_id == current_user.id,
        Appointment.date >= today_start,
        Appointment.date <= today_end
    ).order_by(Appointment.date).all()

    upcoming = Appointment.query.filter(
        Appointment.practitioner_id == current_user.id,
        Appointment.date > datetime.utcnow(),
        Appointment.status == 'scheduled'
    ).order_by(Appointment.date).limit(5).all()

    open_missions = Mission.query.filter_by(status='open').count()
    unread_messages = Message.query.filter_by(
        receiver_id=current_user.id, read=False).count()

    stats = {
        'total_patients': total_patients,
        'today_appointments': len(today_appointments),
        'open_missions': open_missions,
        'unread_messages': unread_messages
    }
    return render(DASHBOARD_TPL, stats=stats,
                  today_appointments=today_appointments, upcoming=upcoming)


@app.route('/agenda')
@login_required
def agenda():
    appointments = Appointment.query.filter_by(
        practitioner_id=current_user.id
    ).order_by(Appointment.date.desc()).all()
    return render(AGENDA_TPL, appointments=appointments)


@app.route('/agenda/new', methods=['GET', 'POST'])
@login_required
def new_appointment():
    form = AppointmentForm()
    patients_list = Patient.query.filter_by(owner_id=current_user.id).all()
    form.patient_id.choices = [(p.id, f"{p.first_name} {p.last_name}")
                                for p in patients_list]

    if not patients_list:
        flash("Veuillez d'abord ajouter un patient.", 'warning')
        return redirect(url_for('patients'))

    if form.validate_on_submit():
        try:
            hour, minute = map(int, form.time.data.split(':'))
            appt_datetime = datetime.combine(
                form.date.data,
                datetime.min.time().replace(hour=hour, minute=minute)
            )
            appt = Appointment(
                practitioner_id=current_user.id,
                patient_id=form.patient_id.data,
                date=appt_datetime,
                duration_minutes=form.duration_minutes.data,
                type=form.type.data,
                location=form.location.data,
                notes=form.notes.data
            )
            db.session.add(appt)
            db.session.commit()
            flash('Rendez-vous planifié !', 'success')
            return redirect(url_for('agenda'))
        except Exception as e:
            flash(f'Erreur de format heure (HH:MM attendu) : {e}', 'danger')
    return render(NEW_APPOINTMENT_TPL, form=form)


@app.route('/agenda/<int:appt_id>/complete', methods=['POST'])
@login_required
def complete_appointment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    if appt.practitioner_id != current_user.id:
        abort(403)
    appt.status = 'completed'
    db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/patients')
@login_required
def patients():
    patients_list = Patient.query.filter_by(owner_id=current_user.id)\
        .order_by(Patient.created_at.desc()).all()
    return render(PATIENTS_TPL, patients=patients_list)


@app.route('/patients/new', methods=['GET', 'POST'])
@login_required
def new_patient():
    form = PatientForm()
    if form.validate_on_submit():
        patient = Patient(
            owner_id=current_user.id,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            phone=form.phone.data,
            email=form.email.data,
            address=form.address.data,
            wilaya=form.wilaya.data or current_user.wilaya,
            notes=form.notes.data
        )
        db.session.add(patient)
        db.session.commit()
        flash('Patient ajouté !', 'success')
        return redirect(url_for('patients'))
    return render(NEW_PATIENT_TPL, form=form)


@app.route('/patients/<int:patient_id>/delete', methods=['POST'])
@login_required
def delete_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    if patient.owner_id != current_user.id:
        abort(403)
    db.session.delete(patient)
    db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/missions')
@login_required
def missions():
    all_missions = Mission.query.filter_by(status='open')\
        .order_by(Mission.created_at.desc()).all()
    my_missions = Mission.query.filter_by(creator_id=current_user.id)\
        .order_by(Mission.created_at.desc()).all()
    return render(MISSIONS_TPL, missions=all_missions, my_missions=my_missions)


@app.route('/missions/new', methods=['GET', 'POST'])
@login_required
def new_mission():
    form = MissionForm()
    if form.validate_on_submit():
        mission = Mission(
            creator_id=current_user.id,
            title=form.title.data,
            description=form.description.data,
            speciality=form.speciality.data,
            location=form.location.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            hourly_rate=form.hourly_rate.data
        )
        db.session.add(mission)
        db.session.commit()
        flash('Mission publiée !', 'success')
        return redirect(url_for('missions'))
    return render(NEW_MISSION_TPL, form=form)


@app.route('/missions/<int:mission_id>/apply', methods=['POST'])
@login_required
def apply_mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    if mission.creator_id == current_user.id:
        return jsonify({'error': 'Vous ne pouvez pas postuler à votre propre mission'}), 400
    mission.status = 'assigned'
    db.session.commit()
    return jsonify({'status': 'ok', 'message': 'Candidature envoyée'})


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    profile = current_user.profile
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name', current_user.first_name)
        current_user.last_name = request.form.get('last_name', current_user.last_name)
        current_user.phone = request.form.get('phone', current_user.phone)
        current_user.wilaya = request.form.get('wilaya', current_user.wilaya)
        current_user.commune = request.form.get('commune', current_user.commune)

        if profile:
            profile.speciality = request.form.get('speciality', profile.speciality)
            try:
                profile.experience_years = int(request.form.get('experience_years', 0) or 0)
                profile.hourly_rate = float(request.form.get('hourly_rate', 0) or 0)
            except ValueError:
                pass
            profile.bio = request.form.get('bio', profile.bio)

        db.session.commit()
        flash('Profil mis à jour !', 'success')
        return redirect(url_for('profile'))
    return render(PROFILE_TPL, profile=profile)


@app.route('/api/stats')
@login_required
def api_stats():
    return jsonify({
        'patients': Patient.query.filter_by(owner_id=current_user.id).count(),
        'appointments': Appointment.query.filter_by(
            practitioner_id=current_user.id).count(),
        'missions': Mission.query.filter_by(creator_id=current_user.id).count(),
    })


@app.route('/health')
def health():
    """Endpoint de santé pour vérifier la connexion BDD."""
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'ok', 'db': 'connected'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'db': str(e)}), 500


# =====================================================================
# INITIALISATION BASE DE DONNÉES
# =====================================================================

def init_db():
    """Crée les tables et l'admin par défaut."""
    with app.app_context():
        try:
            db.create_all()
            print("✅ Tables créées / vérifiées")
        except Exception as e:
            print(f"❌ Erreur création tables : {e}")
            raise

        try:
            if not User.query.filter_by(email='admin@nexuscare.dz').first():
                admin = User(
                    email='admin@nexuscare.dz',
                    first_name='Admin',
                    last_name='Nexus',
                    role='admin',
                    verified=True
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print('✅ Admin créé : admin@nexuscare.dz / admin123')
            else:
                print('ℹ️  Admin déjà existant')
        except Exception as e:
            db.session.rollback()
            print(f"⚠️  Erreur création admin : {e}")


# =====================================================================
# LANCEMENT
# =====================================================================

if __name__ == '__main__':
    init_db()
    print("=" * 60)
    print("NEXUS CARE v2.0")
    print("=" * 60)
    print("Accès   : http://localhost:5000")
    print("Admin   : admin@nexuscare.dz / admin123")
    print("Health  : http://localhost:5000/health")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
