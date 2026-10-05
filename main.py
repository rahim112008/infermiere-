import streamlit as st
import sqlite3
import os
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

st.set_page_config(page_title="Nexus Care", page_icon="🏥", layout="wide")

# ---------- BASE DE DONNÉES ----------
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "nexus_care.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE, password_hash TEXT,
        first_name TEXT, last_name TEXT, role TEXT, wilaya TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER, first_name TEXT, last_name TEXT,
        phone TEXT, wilaya TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        practitioner_id INTEGER, patient_id INTEGER,
        date TEXT, type TEXT, duration INTEGER, status TEXT)""")
    conn.commit()
    # Admin par défaut
    c.execute("SELECT * FROM users WHERE email=?", ("admin@nexuscare.dz",))
    if not c.fetchone():
        c.execute("INSERT INTO users (email, password_hash, first_name, last_name, role) VALUES (?,?,?,?,?)",
                  ("admin@nexuscare.dz", generate_password_hash("admin123"),
                   "Admin", "Nexus", "admin"))
        conn.commit()
    conn.close()

init_db()

# ---------- SESSION ----------
if "user" not in st.session_state:
    st.session_state.user = None

# ---------- PAGE LOGIN ----------
def login_page():
    st.title("🏥 Nexus Care")
    st.subheader("Connexion")
    email = st.text_input("Email")
    password = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter", type="primary"):
        conn = get_conn()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            st.session_state.user = dict(user)
            st.rerun()
        else:
            st.error("Email ou mot de passe incorrect")
    st.caption("Admin : admin@nexuscare.dz / admin123")

# ---------- PAGE DASHBOARD ----------
def dashboard_page():
    user = st.session_state.user
    st.title(f"Bonjour, {user['first_name']} 👋")
    st.caption(f"{user.get('wilaya', 'Algérie')} — {user['role']}")

    conn = get_conn()
    nb_patients = conn.execute("SELECT COUNT(*) FROM patients WHERE owner_id=?",
                                (user["id"],)).fetchone()[0]
    nb_rdv = conn.execute("SELECT COUNT(*) FROM appointments WHERE practitioner_id=?",
                          (user["id"],)).fetchone()[0]
    conn.close()

    col1, col2 = st.columns(2)
    col1.metric("Patients", nb_patients)
    col2.metric("Rendez-vous", nb_rdv)

# ---------- PAGE PATIENTS ----------
def patients_page():
    user = st.session_state.user
    st.title("👥 Mes Patients")

    with st.form("new_patient"):
        st.subheader("Ajouter un patient")
        c1, c2 = st.columns(2)
        first = c1.text_input("Prénom")
        last = c2.text_input("Nom")
        phone = c1.text_input("Téléphone")
        wilaya = c2.text_input("Wilaya")
        if st.form_submit_button("Enregistrer"):
            if first and last:
                conn = get_conn()
                conn.execute("INSERT INTO patients (owner_id, first_name, last_name, phone, wilaya) VALUES (?,?,?,?,?)",
                             (user["id"], first, last, phone, wilaya))
                conn.commit()
                conn.close()
                st.success("Patient ajouté")
                st.rerun()

    conn = get_conn()
    rows = conn.execute("SELECT * FROM patients WHERE owner_id=? ORDER BY id DESC",
                        (user["id"],)).fetchall()
    conn.close()
    if rows:
        st.dataframe([dict(r) for r in rows], use_container_width=True)
    else:
        st.info("Aucun patient")

# ---------- PAGE AGENDA ----------
def agenda_page():
    user = st.session_state.user
    st.title("📅 Mon Agenda")

    conn = get_conn()
    patients = conn.execute("SELECT id, first_name, last_name FROM patients WHERE owner_id=?",
                            (user["id"],)).fetchall()

    with st.form("new_appt"):
        if patients:
            options = {f"{p['first_name']} {p['last_name']}": p["id"] for p in patients}
            patient_label = st.selectbox("Patient", list(options.keys()))
            date_appt = st.date_input("Date", value=date.today())
            time_appt = st.time_input("Heure")
            typ = st.selectbox("Type", ["consultation", "soin", "urgence"])
            if st.form_submit_button("Planifier"):
                dt = datetime.combine(date_appt, time_appt).isoformat()
                conn.execute("INSERT INTO appointments (practitioner_id, patient_id, date, type, duration, status) VALUES (?,?,?,?,?,?)",
                             (user["id"], options[patient_label], dt, typ, 30, "scheduled"))
                conn.commit()
                st.success("RDV planifié")
                st.rerun()
        else:
            st.warning("Ajoutez d'abord un patient")

    rows = conn.execute("""SELECT a.id, a.date, a.type, a.status,
                                  p.first_name || ' ' || p.last_name AS patient
                           FROM appointments a
                           JOIN patients p ON p.id = a.patient_id
                           WHERE a.practitioner_id=?
                           ORDER BY a.date DESC""", (user["id"],)).fetchall()
    conn.close()
    if rows:
        st.dataframe([dict(r) for r in rows], use_container_width=True)
    else:
        st.info("Aucun rendez-vous")

# ---------- ROUTAGE ----------
if st.session_state.user is None:
    login_page()
else:
    with st.sidebar:
        st.markdown(f"**{st.session_state.user['first_name']} {st.session_state.user['last_name']}**")
        st.caption(st.session_state.user["role"])
        page = st.radio("Navigation", ["🏠 Tableau de bord", "👥 Patients", "📅 Agenda"])
        if st.button("Déconnexion"):
            st.session_state.user = None
            st.rerun()

    if page == "🏠 Tableau de bord":
        dashboard_page()
    elif page == "👥 Patients":
        patients_page()
    elif page == "📅 Agenda":
        agenda_page()
