"""
SAPS E-Docket System - Durban Central
BIPJ702 Business Intelligence Project - Group 9

The electronic docket management system that replaces the paper-based
process. Officers log in, create and search dockets electronically,
update status, and view live counts - all in this one application.

Run with:
    streamlit run app.py
"""
import socket
import sqlite3
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import qrcode
import streamlit as st

DB_PATH = "police_dockets.db"

# -----------------------------------------------------------------
# PAGE CONFIG - must be the first Streamlit command that runs
# -----------------------------------------------------------------
st.set_page_config(
    page_title="SAPS E-Docket System",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------
# BRAND STYLING
# DUT navy / blue / gold palette, a custom font, a subtle shield
# watermark pattern in the background, and card-style panels for
# the main content - built entirely from CSS/SVG (no external
# images), so there's nothing to break and nothing to license.
# -----------------------------------------------------------------
SHIELD_SVG = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' width='90' height='90'%3E"
    "%3Cpath d='M45 6 L78 18 L78 42 C78 64 62 78 45 84 "
    "C28 78 12 64 12 42 L12 18 Z' fill='none' stroke='white' "
    "stroke-width='1.4' opacity='0.5'/%3E%3C/svg%3E"
)

st.markdown(
    f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    /* Full-page navy gradient with a faint tiled shield watermark */
    .stApp {{
        background:
            url("{SHIELD_SVG}"),
            linear-gradient(135deg, #001526 0%, #003865 55%, #001d3d 100%);
        background-repeat: repeat, no-repeat;
        background-size: 90px 90px, cover;
        background-attachment: fixed;
    }}

    /* Main content sits on a clean white card, floating over the gradient */
    .block-container {{
        background: rgba(255, 255, 255, 0.98);
        border-radius: 18px;
        padding: 2.2rem 2.8rem 2.6rem 2.8rem;
        margin-top: 1.6rem;
        margin-bottom: 1.6rem;
        box-shadow: 0 12px 40px rgba(0, 10, 30, 0.35);
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #003865 0%, #001d3d 100%);
    }}
    [data-testid="stSidebar"] * {{
        color: #FFFFFF !important;
    }}
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div {{
        background-color: #FFFFFF;
        color: #003865 !important;
        border-radius: 6px;
    }}
    [data-testid="stSidebar"] .stButton button {{
        background-color: #E0004D;
        color: #FFFFFF !important;
        border: none;
        border-radius: 6px;
        font-weight: 600;
    }}
    [data-testid="stSidebar"] .stButton button:hover {{
        background-color: #ff1a63;
    }}

    /* Headings */
    h1, h2, h3 {{
        color: #003865;
        font-weight: 700;
    }}

    /* Buttons in the main content area */
    .stButton>button {{
        background-color: #0085CA;
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        padding: 0.5rem 1.4rem;
        transition: background-color 0.15s ease;
    }}
    .stButton>button:hover {{
        background-color: #003865;
        color: white;
    }}

    /* Metrics */
    [data-testid="stMetric"] {{
        background: #F0F5FA;
        border: 1px solid #D9E2EC;
        border-radius: 12px;
        padding: 0.8rem 1rem;
    }}
    [data-testid="stMetricValue"] {{
        color: #0085CA;
    }}

    /* Hero banner at the top of the main app */
    .app-banner {{
        background: linear-gradient(120deg, #003865 0%, #0085CA 100%);
        padding: 26px 32px;
        border-radius: 14px;
        margin-bottom: 24px;
        box-shadow: 0 6px 20px rgba(0, 56, 101, 0.35);
    }}
    .app-banner h1 {{
        color: #FFFFFF !important;
        margin: 0;
        font-size: 30px;
        letter-spacing: 0.3px;
    }}
    .app-banner p {{
        color: #CADCFC;
        margin: 6px 0 0 0;
        font-size: 14.5px;
    }}

    /* Login card */
    .login-card {{
        background: #FFFFFF;
        border-radius: 16px;
        padding: 2.4rem 2.6rem;
        box-shadow: 0 10px 35px rgba(0, 10, 30, 0.3);
        max-width: 420px;
        margin: 2rem auto 0 auto;
        text-align: center;
    }}
    .login-card h1 {{
        font-size: 24px;
        margin-bottom: 4px;
    }}
    .login-card p {{
        color: #5A6472;
        font-size: 14px;
        margin-bottom: 1.2rem;
    }}

    /* Dataframes */
    [data-testid="stDataFrame"] {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #D9E2EC;
    }}
</style>
""",
    unsafe_allow_html=True,
)


def get_local_ip():
    """Best-effort LAN IP, so QR codes work when scanned from a phone
    on the same Wi-Fi network. Falls back to localhost if it fails
    (e.g. no network access) - localhost QR codes just won't open on
    a separate phone, only on the same machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


LOCAL_IP = get_local_ip()

# -----------------------------------------------------------------
# DATABASE SETUP
# -----------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dockets (
            docket_id TEXT PRIMARY KEY,
            crime_type TEXT,
            officer TEXT,
            station TEXT,
            status TEXT,
            date_opened TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            full_name TEXT,
            rank TEXT
        )
    """)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        demo_users = [
            ("s.ndlovu", "docket123", "Sipho Ndlovu", "Sergeant"),
            ("t.naidoo", "docket123", "Thandeka Naidoo", "Captain"),
        ]
        conn.executemany(
            "INSERT INTO users (username, password, full_name, rank) VALUES (?,?,?,?)",
            demo_users,
        )
        conn.commit()
    return conn


conn = get_conn()

# -----------------------------------------------------------------
# LOGIN
# -----------------------------------------------------------------
def login_screen():
    st.markdown(
        """<div class="login-card">
            <div style="font-size:44px;">🛡️</div>
            <h1>SAPS E-Docket System</h1>
            <p>Durban Central Cluster — Electronic Docket Management</p>
        </div>""",
        unsafe_allow_html=True,
    )

    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        with st.form("login_form"):
            username = st.text_input("Officer Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            row = conn.execute(
                "SELECT full_name, rank FROM users WHERE username = ? AND password = ?",
                (username, password),
            ).fetchone()
            if row:
                st.session_state["logged_in"] = True
                st.session_state["officer_name"] = row[0]
                st.session_state["officer_rank"] = row[1]
                st.rerun()
            else:
                st.error("Invalid username or password.")

        

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_screen()
    st.stop()

# -----------------------------------------------------------------
# MAIN APP (only reached once logged in)
# -----------------------------------------------------------------
st.sidebar.success(f"Logged in as {st.session_state['officer_name']} ({st.session_state['officer_rank']})")
if st.sidebar.button("Log out"):
    st.session_state["logged_in"] = False
    st.rerun()

# If a QR code was scanned, the URL will contain ?docket=DBN-CAS-2026-XXX -
# jump straight to Search Docket with that ID already filled in.
scanned_docket = st.query_params.get("docket", None)

# -----------------------------------------------------------------
# ROLE-BASED ACCESS
# Front-line officers (e.g. Sergeant) handle day-to-day casework.
# Station command (e.g. Captain) additionally gets status-change
# authority and the analytics dashboard - a basic segregation of
# duties, so the person who opens a case isn't automatically the
# same person who can close it or see cross-station analytics.
# -----------------------------------------------------------------
ROLE_PERMISSIONS = {
    "Sergeant": ["Add Docket", "View Dockets", "Search Docket"],
    "Constable": ["Add Docket", "View Dockets", "Search Docket"],
    "Captain": ["Add Docket", "View Dockets", "Search Docket", "Update Status", "Dashboard"],
    "Lieutenant Colonel": ["Add Docket", "View Dockets", "Search Docket", "Update Status", "Dashboard"],
    "Colonel": ["Add Docket", "View Dockets", "Search Docket", "Update Status", "Dashboard"],
    "Brigadier": ["Add Docket", "View Dockets", "Search Docket", "Update Status", "Dashboard"],
}
DEFAULT_PERMISSIONS = ["Add Docket", "View Dockets", "Search Docket"]  # safest default for any unlisted rank

officer_rank = st.session_state["officer_rank"]
menu_options = ROLE_PERMISSIONS.get(officer_rank, DEFAULT_PERMISSIONS)

is_command_rank = "Update Status" in menu_options
badge_color = "#F2A900" if is_command_rank else "#0085CA"
badge_text = "Station Command Access" if is_command_rank else "Front-Line Access"
st.sidebar.markdown(
    f"""<div style="background:{badge_color};color:#003865;font-weight:600;
        font-size:12px;padding:6px 10px;border-radius:6px;margin-bottom:12px;
        text-align:center;">{badge_text}</div>""",
    unsafe_allow_html=True,
)

default_index = menu_options.index("Search Docket") if scanned_docket and "Search Docket" in menu_options else 0
menu = st.sidebar.selectbox("Menu", menu_options, index=default_index)

st.markdown(
    """<div class="app-banner">
        <h1>🛡️ SAPS E-Docket System</h1>
        <p>Durban Central Cluster — Electronic Docket Management</p>
    </div>""",
    unsafe_allow_html=True,
)

# ---------------- ADD DOCKET ----------------
if menu == "Add Docket":
    st.subheader("Create New Docket")

    docket_id = st.text_input("Docket ID (e.g. DBN-CAS-2026-201)")
    crime_type = st.selectbox(
        "Crime Type", ["Theft", "Burglary", "Assault", "Robbery", "Murder", "GBV",
                        "Vehicle Theft (Hijacking)", "Fraud", "Drug Possession", "Domestic Violence"]
    )
    station = st.selectbox(
        "Station", ["Durban Central", "Umlazi", "Cato Manor", "Sydenham",
                     "Point", "Chatsworth", "KwaMashu", "Berea"]
    )
    status = st.selectbox("Status", ["Open", "In Court", "Closed"])

    if st.button("Save Docket"):
        if not docket_id:
            st.error("Docket ID is required.")
        else:
            existing = conn.execute(
                "SELECT 1 FROM dockets WHERE docket_id = ?", (docket_id,)
            ).fetchone()
            if existing:
                st.error(f"Docket {docket_id} already exists. Use 'Update Status' instead.")
            else:
                conn.execute(
                    """INSERT INTO dockets
                       (docket_id, crime_type, officer, station, status, date_opened, last_updated)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        docket_id,
                        crime_type,
                        st.session_state["officer_name"],
                        station,
                        status,
                        str(date.today()),
                        str(datetime.now()),
                    ),
                )
                conn.commit()
                st.success(f"Docket {docket_id} saved electronically. It cannot go missing from a filing cabinet.")

                docket_url = f"http://{LOCAL_IP}:8501/?docket={docket_id}"
                qr_img = qrcode.make(docket_url)
                buf = BytesIO()
                qr_img.save(buf, format="PNG")
                st.image(buf.getvalue(), caption=f"Scan to open {docket_id}", width=180)
                st.caption(f"Encoded link: {docket_url}")
                st.download_button("Download QR Code", buf.getvalue(), file_name=f"{docket_id}_qr.png")

# ---------------- VIEW DOCKETS ----------------
elif menu == "View Dockets":
    st.subheader("All Dockets")
    df = pd.read_sql("SELECT * FROM dockets ORDER BY last_updated DESC", conn)
    st.dataframe(df, use_container_width=True)
    st.caption(f"{len(df)} dockets on file.")

# ---------------- SEARCH DOCKET ----------------
elif menu == "Search Docket":
    st.subheader("Search Docket")
    st.write("Type a Docket ID, or scan its QR code with your phone camera — "
             "it will open this page with the ID already filled in.")
    search = st.text_input("Enter Docket ID", value=scanned_docket or "")

    if search:
        result = pd.read_sql(
            "SELECT * FROM dockets WHERE docket_id = ?", conn, params=(search,)
        )
        if result.empty:
            st.warning("No docket found with that ID.")
        else:
            st.dataframe(result, use_container_width=True)

# ---------------- UPDATE STATUS ----------------
elif menu == "Update Status":
    st.subheader("Update Docket Status")
    all_ids = pd.read_sql("SELECT docket_id FROM dockets", conn)["docket_id"].tolist()
    if not all_ids:
        st.info("No dockets yet. Add one first.")
    else:
        chosen_id = st.selectbox("Docket ID", all_ids)
        new_status = st.selectbox("New Status", ["Open", "In Court", "Closed"])
        if st.button("Update"):
            conn.execute(
                "UPDATE dockets SET status = ?, last_updated = ? WHERE docket_id = ?",
                (new_status, str(datetime.now()), chosen_id),
            )
            conn.commit()
            st.success(f"Docket {chosen_id} updated to '{new_status}'.")

# ---------------- DASHBOARD ----------------
elif menu == "Dashboard":
    st.subheader("Live Dashboard")
    df = pd.read_sql("SELECT * FROM dockets", conn)
 
    if df.empty:
        st.info("No dockets logged yet - add some first.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Dockets", len(df))
        col2.metric("Open", int((df["status"] == "Open").sum()))
        col3.metric("Closed", int((df["status"] == "Closed").sum()))

        st.bar_chart(df["station"].value_counts())
        st.caption("Dockets by station")

        st.bar_chart(df["crime_type"].value_counts())
        st.caption("Dockets by crime type")

        status_counts = df["status"].value_counts()
        st.write("Status breakdown:")
        st.dataframe(status_counts)



