"""
The Finance Engine - Login Page Module
Premium dark trading dashboard login UI
Approach: CSS-only card that wraps Streamlit's own form elements via 
aggressive selector targeting — card is drawn as page background layer,
inputs float inside it using fixed positioning math via CSS transforms.
"""

import streamlit as st
import os
import json
import time
import base64
import requests
from datetime import datetime


# ── Helpers ──────────────────────────────────────────────────────────────────

def set_login_cookie(username, user_name):
    expiry = int(time.time()) + 86400
    cookie_data = base64.b64encode(json.dumps({
        "username": username, "user_name": user_name, "expiry": expiry
    }).encode()).decode()
    st.markdown(
        f'<script>document.cookie="tfengine_session={cookie_data};path=/;max-age=86400";</script>',
        unsafe_allow_html=True)


def clear_login_cookie():
    st.markdown(
        '<script>document.cookie="tfengine_session=;path=/;max-age=0";</script>',
        unsafe_allow_html=True)


def encrypt_session(data):
    return base64.b64encode(json.dumps(data).encode()).decode()


def decrypt_session(cookie_str):
    try:
        decoded = base64.b64decode(cookie_str.encode()).decode()
        data = json.loads(decoded)
        if data.get("expiry", 0) > time.time():
            return data
    except Exception:
        pass
    return None


def master_audit_log(action_type, details):
    try:
        url = "https://script.google.com/macros/s/AKfycbxtd5reNGnPATB7oCWRtwYYO_BKMb55HwdemU5nw5MwkguSIlL8uV1maT8BkcK0TElz6A/exec"
        requests.post(url, json={
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username": st.session_state.get("username", "System"),
            "name": st.session_state.get("user_name", "N/A"),
            "action": action_type, "details": details, "source": "Login Portal"
        }, timeout=5)
    except Exception:
        pass


def handle_login_request():
    entered_username = st.session_state.get("_lu", "")
    entered_password = st.session_state.get("_lp", "")

    user_db = None
    env_val = os.environ.get("USER_DB_JSON")
    if env_val:
        try:
            user_db = json.loads(env_val)
        except Exception:
            pass

    if not user_db:
        try:
            if os.path.exists("users.json"):
                with open("users.json") as f:
                    user_db = json.load(f)
            else:
                st.session_state._le = "db_missing"; return
        except Exception:
            st.session_state._le = "db_error"; return

    users = user_db.get("users", [])
    found = next((u for u in users
                  if u["username"] == entered_username and u["password"] == entered_password), None)

    if found:
        st.session_state.authenticated = True
        st.session_state.user_name = found.get("name", entered_username)
        st.session_state.username  = entered_username
        st.session_state._le       = None
        set_login_cookie(entered_username, found.get("name", entered_username))
        enc = encrypt_session({"username": entered_username,
                                "user_name": found.get("name", entered_username),
                                "expiry": int(time.time()) + 86400})
        st.session_state.encrypted_session = enc
        st.query_params["s"] = enc
        master_audit_log("LOGIN", f"User {entered_username} logged in")
        st.toast(f"Welcome back, {st.session_state.user_name}!")
        st.rerun()
    else:
        st.session_state._le = "bad_creds"


def handle_logout_request():
    clear_login_cookie()
    for k in ["authenticated", "_le", "_lu", "_lp", "encrypted_session", "username", "user_name"]:
        st.session_state.pop(k, None)
    st.rerun()


# ── The key insight: use Streamlit's block-container as the card itself ───────
# We paint the card visually behind the native Streamlit elements by making
# the main block-container styled as the card, and centering everything.

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&display=swap');

:root {
    --bg:       #0d1117;
    --card:     #161b22;
    --border:   #30363d;
    --gold:     #f0b429;
    --text:     #f0f6fc;
    --muted:    #8b949e;
    --muted2:   #6e7681;
    --ibg:      #0d1117;
    --err-bg:   rgba(239,68,68,0.1);
    --err-bd:   rgba(239,68,68,0.3);
    --err-tx:   #f87171;
}

/* ── Full page reset ── */
html, body, .stApp { 
    background: var(--bg) !important; 
    font-family: 'DM Sans', sans-serif;
    color: var(--text) !important;
}

header[data-testid="stHeader"],
.stToolbar, footer, #MainMenu, 
[data-testid="stDecoration"],
[data-testid="stStatusWidget"]          { display: none !important; }

/* ── Center the entire Streamlit app ── */
.appview-container, section[data-testid="stMain"] {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    min-height: 100vh !important;
    background: transparent !important;
}
section[data-testid="stMain"] > div {
    width: 100% !important;
    display: flex !important;
    justify-content: center !important;
}

/* ── The block-container IS the card ── */
.block-container {
    width: 440px !important;
    max-width: 440px !important;
    min-width: 320px !important;
    padding: 44px 40px 36px !important;
    margin: 0 auto !important;
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 22px !important;
    box-shadow:
        0 40px 80px rgba(0,0,0,0.65),
        0 0 0 1px rgba(255,255,255,0.025),
        inset 0 1px 0 rgba(255,255,255,0.04) !important;
    position: relative !important;
    z-index: 1 !important;
    /* top shimmer via outline trick */
    outline: none !important;
}
/* gold shimmer line at top of card */
.block-container::before {
    content: '';
    position: absolute; top: 0; left: 50%;
    transform: translateX(-50%);
    width: 48%; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(240,180,41,0.55), transparent);
    border-radius: 1px;
}
/* corner glow */
.block-container::after {
    content: '';
    position: absolute; top: -50px; right: -50px;
    width: 180px; height: 180px; border-radius: 50%;
    background: radial-gradient(circle, rgba(240,180,41,0.05) 0%, transparent 70%);
    pointer-events: none;
}

/* ── Logo row ── */
.tfe-logo-row {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 28px;
}
.tfe-logo-icon {
    width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
    background: linear-gradient(135deg,rgba(240,180,41,0.14),rgba(240,180,41,0.03));
    border: 1px solid rgba(240,180,41,0.2);
    display: flex; align-items: center; justify-content: center; font-size: 19px;
}
.tfe-logo-name {
    font-family: 'Syne',sans-serif; font-size: 16px; font-weight: 700;
    color: var(--text); letter-spacing: -0.2px;
}
.tfe-logo-name span { color: var(--gold); }
.tfe-logo-badge {
    margin-left: auto; font-size: 10px; font-weight: 500;
    letter-spacing: 0.9px; text-transform: uppercase; color: var(--muted2);
    background: rgba(255,255,255,0.04); border: 1px solid var(--border);
    padding: 3px 9px; border-radius: 20px;
}

/* ── Heading ── */
.tfe-h1 {
    font-family: 'Syne',sans-serif; font-size: 26px; font-weight: 700;
    color: var(--text); letter-spacing: -0.5px;
    margin-bottom: 5px; line-height: 1.2;
}
.tfe-sub { font-size: 14px; color: var(--muted); margin-bottom: 22px; line-height: 1.5; }

/* ── Status pill ── */
.tfe-status {
    display: inline-flex; align-items: center; gap: 7px;
    background: rgba(34,197,94,0.06); border: 1px solid rgba(34,197,94,0.15);
    border-radius: 20px; padding: 5px 13px; margin-bottom: 30px;
}
.tfe-dot {
    width: 6px; height: 6px; border-radius: 50%; background: #22c55e;
    box-shadow: 0 0 7px rgba(34,197,94,0.7);
    animation: dp 2.2s ease-in-out infinite;
}
@keyframes dp { 0%,100%{opacity:1} 50%{opacity:0.3} }
.tfe-status span { font-size: 11.5px; color: #4ade80; font-weight: 500; }

/* ── Error box ── */
.tfe-err {
    background: var(--err-bg); border: 1px solid var(--err-bd);
    border-radius: 10px; padding: 11px 14px; margin-bottom: 16px;
    color: var(--err-tx); font-size: 13px; font-weight: 500;
}

/* ── Field labels ── */
.tfe-lbl {
    display: block; font-size: 11px; font-weight: 500;
    letter-spacing: 0.9px; text-transform: uppercase;
    color: var(--muted); margin-bottom: 7px;
}
.tfe-gap { height: 16px; }

/* ── Inputs ── */
div[data-testid="stTextInput"] label { display: none !important; }
div[data-testid="stTextInput"] > div { margin-bottom: 0 !important; }
div[data-testid="stTextInput"] > div > div { gap: 0 !important; }
div[data-testid="stTextInput"] input {
    background:    var(--ibg)  !important;
    border:        1px solid rgba(255,255,255,0.09) !important;
    border-radius: 11px !important;
    padding:       13px 15px !important;
    font-family:   'DM Sans',sans-serif !important;
    font-size:     14px !important;
    color:         var(--text) !important;
    transition:    border-color 0.18s, box-shadow 0.18s !important;
    height:        auto !important;
    line-height:   1.4 !important;
    box-shadow:    none !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: rgba(240,180,41,0.5) !important;
    box-shadow:   0 0 0 3px rgba(240,180,41,0.1) !important;
    outline: none !important;
}
div[data-testid="stTextInput"] input::placeholder { color: var(--muted2) !important; }
div[data-testid="stTextInput"] input:-webkit-autofill {
    -webkit-box-shadow: 0 0 0 1000px var(--ibg) inset !important;
    -webkit-text-fill-color: var(--text) !important;
}

/* ── Submit button ── */
div[data-testid="stFormSubmitButton"] > button,
div[data-testid="stButton"] > button {
    width:         100% !important;
    background:    linear-gradient(135deg,#f0b429 0%,#f0b429 100%) !important;
    border:        none !important;
    border-radius: 11px !important;
    padding:       14px 24px !important;
    font-family:   'Syne',sans-serif !important;
    font-size:     15px !important;
    font-weight:   700 !important;
    color:         #0c0e14 !important;
    letter-spacing: 0.1px !important;
    margin-top:    8px !important;
    transition:    transform 0.14s, box-shadow 0.18s !important;
    box-shadow:    none !important;
}
div[data-testid="stFormSubmitButton"] > button:hover,
div[data-testid="stButton"] > button:hover {
    transform:  translateY(-1px) !important;
    box-shadow: 0 8px 26px rgba(240,180,41,0.3) !important;
}
div[data-testid="stFormSubmitButton"] > button:active { transform: translateY(0) !important; }

/* ── Strip form border ── */
div[data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}

/* ── Footer ── */
.tfe-footer {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    margin-top: 26px; padding-top: 20px; border-top: 1px solid var(--border);
}
.tfe-fdot { width:5px;height:5px;border-radius:50%;background:rgba(240,180,41,0.22); }
.tfe-footer p { font-size:11.5px; color:var(--muted2); letter-spacing:0.3px; }

/* ── Sidebar ── */
.tfe-user-card {
    background: rgba(240,180,41,0.05); border: 1px solid rgba(240,180,41,0.12);
    border-radius: 11px; padding: 11px 13px; margin-bottom: 10px;
}
.tfe-user-name { font-family:'Syne',sans-serif; font-size:15px; font-weight:700; color:#edf0f6; margin-bottom:2px; }
.tfe-user-role { font-size:11.5px; color:#6a7280; }

@media(max-width:520px) {
    .block-container { width:100% !important; border-radius:0 !important; padding:32px 20px 28px !important; }
}
</style>
"""


def render_login_page():
    # Defaults
    for k, v in [("authenticated",False),("encrypted_session",None),
                 ("_lu",""),("_lp",""),("_le",None)]:
        if k not in st.session_state:
            st.session_state[k] = v

    # URL session restore
    if "s" in st.query_params and not st.session_state.authenticated:
        token = st.query_params["s"]
        data = decrypt_session(token)
        if data and data.get("expiry",0) > time.time():
            st.session_state.authenticated     = True
            st.session_state.username          = data.get("username","")
            st.session_state.user_name         = data.get("user_name","")
            st.session_state.encrypted_session = token
            st.query_params.clear()

    if st.session_state.authenticated:
        return True

    # Inject CSS
    st.markdown(_CSS, unsafe_allow_html=True)

    # Card header — self-contained HTML block
    st.markdown("""
    <div class="tfe-logo-row">
      <div class="tfe-logo-icon">📈</div>
      <div class="tfe-logo-name">The Finance <span>Engine</span></div>
      <div class="tfe-logo-badge">v2.0</div>
    </div>
    <div class="tfe-h1">Welcome back.</div>
    <div class="tfe-sub">Sign in to access your trading dashboard.</div>
    <div class="tfe-status">
      <div class="tfe-dot"></div>
      <span>All systems operational</span>
    </div>
    """, unsafe_allow_html=True)

    # Error
    err = st.session_state.get("_le")
    if err == "bad_creds":
        st.markdown('<div class="tfe-err">✕ &nbsp;Invalid username or password.</div>', unsafe_allow_html=True)
    elif err == "db_missing":
        st.markdown('<div class="tfe-err">✕ &nbsp;User database not found.</div>', unsafe_allow_html=True)
    elif err == "db_error":
        st.markdown('<div class="tfe-err">✕ &nbsp;Error loading user database.</div>', unsafe_allow_html=True)

    # Form with inputs + button — all inside the same card (block-container)
    with st.form("login_form", clear_on_submit=False):
        st.markdown('<span class="tfe-lbl">Username</span>', unsafe_allow_html=True)
        st.text_input("u", label_visibility="collapsed",
                      placeholder="Enter your username", key="_lu")

        st.markdown('<div class="tfe-gap"></div>', unsafe_allow_html=True)
        st.markdown('<span class="tfe-lbl">Password</span>', unsafe_allow_html=True)
        st.text_input("p", type="password", label_visibility="collapsed",
                      placeholder="••••••••••••", key="_lp")

        if st.form_submit_button("Sign In →"):
            handle_login_request()

    # Footer
    st.markdown("""
    <div class="tfe-footer">
      <div class="tfe-fdot"></div>
      <p>Secured · The Finance Engine</p>
      <div class="tfe-fdot"></div>
    </div>
    """, unsafe_allow_html=True)

    return False


def render_sidebar_user():
    with st.sidebar:
        name     = st.session_state.get("user_name", "User")
        username = st.session_state.get("username", "")
        st.markdown(f"""
        <div class="tfe-user-card">
          <div class="tfe-user-name">👤 {name}</div>
          <div class="tfe-user-role">@{username}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Sign Out", key="logout_btn"):
            handle_logout_request()
        st.markdown("---")
        st.caption("🔒 The Finance Engine")


def check_auth():
    """Main auth guard — call at the top of every page in app.py."""
    if not st.session_state.get("authenticated", False):
        render_login_page()
        st.stop()
    render_sidebar_user()
    return True