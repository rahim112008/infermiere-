import streamlit as st
import streamlit.components.v1 as components
import os

# Configuration de la page
st.set_page_config(
    page_title="Nexus Care",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS pour retirer les marges Streamlit
st.markdown("""
<style>
    .main .block-container { padding: 0 !important; max-width: 100% !important; }
    header, #MainMenu, footer { visibility: hidden; }
    .stApp { margin: 0; padding: 0; }
    iframe { width: 100% !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

# Chargement du fichier index.html
html_path = os.path.join(os.path.dirname(__file__), "index.html")

try:
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    components.html(html_content, height=1000, scrolling=True)
except FileNotFoundError:
    st.error("❌ Fichier index.html introuvable")
    st.info("Assurez-vous que index.html est à la racine du dépôt.")
