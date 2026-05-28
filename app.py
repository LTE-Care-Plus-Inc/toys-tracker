import json
import base64
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="Toys Budget Dashboard", layout="wide")

# =====================================================
# AUTH
# =====================================================
if "auth_ok" not in st.session_state:
    st.session_state["auth_ok"] = False

APP_PASSWORD = st.secrets.get("APP_PASSWORD")

if not APP_PASSWORD:
    st.error("APP_PASSWORD missing in secrets")
    st.stop()

if not st.session_state["auth_ok"]:
    st.title("🔐 Login")
    pw = st.text_input("Password", type="password")
    if st.button("Enter"):
        if pw == APP_PASSWORD:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()

# =====================================================
# SETTINGS
# =====================================================
SHEET_ID = st.secrets.get("SHEET_ID")
RAW_SHEET_NAME = st.secrets.get("RAW_SHEET_NAME", "Toys")
AUTH_SHEET_NAME = st.secrets.get("AUTH_SHEET_NAME", "Client List")
BUDGET = float(st.secrets.get("BUDGET", 25))
CACHE_TTL = int(st.secrets.get("CACHE_TTL_SECONDS", 60))
SERVICE_ACCOUNT_B64 = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_B64")

missing = []
if not SHEET_ID:
    missing.append("SHEET_ID")
if not SERVICE_ACCOUNT_B64:
    missing.append("GOOGLE_SERVICE_ACCOUNT_B64")

if missing:
    st.error(
        "Missing required secrets:\n\n- " + "\n- ".join(missing)
    )
    st.stop()

# =====================================================
# HELPERS
# =====================================================
TRUE_VALUES = {"true", "yes", "1", "y", "checked", "x"}

def to_bool(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(TRUE_VALUES)
    )

def normalize_name(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

def to_money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.fillna("")
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce"
    ).fillna(0.0)

def first_matching_column(df: pd.DataFrame, candidates: list[str], *, required_label: str) -> pd.Series:
    """
    Return first matching column as a Series.
    If duplicate headers exist, select the left-most matching column.
    """
    for name in candidates:
        if name in df.columns:
            col = df[name]
            if isinstance(col, pd.DataFrame):
                return col.iloc[:, 0]
            return col
    raise ValueError(f"{required_label} column missing. Found: {df.columns.tolist()}")

# =====================================================
# LOAD DATA
# =====================================================
@st.cache_data(ttl=CACHE_TTL)
def load_data():
    decoded = base64.b64decode(SERVICE_ACCOUNT_B64).decode("utf-8")
    creds_info = json.loads(decoded)

    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    # ================= TOYS SHEET =================
    toys_ws = sh.worksheet(RAW_SHEET_NAME)
    toys_values = toys_ws.get_all_values()

    if not toys_values or len(toys_values) < 2:
        raise ValueError(f"No data found in worksheet '{RAW_SHEET_NAME}'")

    toys_headers = [h.strip() for h in toys_values[0]]
    toys_rows = toys_values[1:]

    toys_fixed_rows = []
    n_cols = len(toys_headers)
    for row in toys_rows:
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        toys_fixed_rows.append(row)

    toys = pd.DataFrame(toys_fixed_rows, columns=toys_headers)
    toys.columns = toys.columns.str.strip()
    toys = toys.loc[:, toys.columns != ""]

    # Flexible client column (safe with duplicate headers)
    toys["Client"] = first_matching_column(
        toys, ["Clients", "Client Name"], required_label="Client (Toys sheet)"
    )

    # ================= CLIENT LIST SHEET =================
    try:
        auth_ws = sh.worksheet(AUTH_SHEET_NAME)
    except Exception:
        available = [ws.title for ws in sh.worksheets()]
        raise ValueError(
            f"Worksheet '{AUTH_SHEET_NAME}' not found. Available sheets: {available}"
        )

    auth_values = auth_ws.get_all_values()

    if not auth_values or len(auth_values) < 2:
        raise ValueError(f"No data found in worksheet '{AUTH_SHEET_NAME}'")

    auth_headers = [h.strip() for h in auth_values[0]]
    auth_rows = auth_values[1:]

    auth_fixed_rows = []
    n_cols = len(auth_headers)
    for row in auth_rows:
        if len(row) < n_cols:
            row = row + [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        auth_fixed_rows.append(row)

    auth = pd.DataFrame(auth_fixed_rows, columns=auth_headers)
    auth.columns = auth.columns.str.strip()
    auth = auth.loc[:, auth.columns != ""]

    return toys, auth

# =====================================================
# BUILD SUMMARY
# =====================================================
def build_summary(toys: pd.DataFrame, auth: pd.DataFrame) -> pd.DataFrame:
    toys = toys.copy()
    auth = auth.copy()

    # Clean toy sheet
    toys["Client"] = normalize_name(toys["Client"]).str.lower()
    toys["Purchased_bool"] = to_bool(toys["Purchased"]) if "Purchased" in toys.columns else False
    toys["Inactive_bool"] = to_bool(toys["Inactive"]) if "Inactive" in toys.columns else False
    toys["Timestamp_dt"] = pd.to_datetime(toys["Timestamp"], errors="coerce")

    if "Clean Cost" in toys.columns:
        toys["Amount"] = to_money(toys["Clean Cost"])
    elif "Cost" in toys.columns:
        toys["Amount"] = to_money(toys["Cost"])
    else:
        raise ValueError(f"No cost column found in Toys sheet. Found: {toys.columns.tolist()}")

    toys = toys[toys["Inactive_bool"] == False].copy()

    # Flexible auth client column (safe with duplicate headers)
    auth["Client"] = first_matching_column(
        auth, ["Client", "Client Name"], required_label="Client (Client List sheet)"
    )

    auth["Client"] = normalize_name(auth["Client"]).str.lower()

    # Flexible start/end detection
    start_col = None
    end_col = None
    status_col = None

    for col in auth.columns:
        lower = col.lower()
        if start_col is None and "start" in lower:
            start_col = col
        if end_col is None and "end" in lower:
            end_col = col
        if status_col is None and "status" in lower:
            status_col = col

    if not start_col or not end_col:
        raise ValueError(
            f"Could not find authorization start/end columns in Client List sheet. Found: {auth.columns.tolist()}"
        )

    auth["Auth Start"] = pd.to_datetime(auth[start_col], errors="coerce")
    auth["Auth End"] = pd.to_datetime(auth[end_col], errors="coerce")
    auth["Status"] = auth[status_col] if status_col else ""

    today = pd.Timestamp.today().normalize()
    rows = []

    for _, row in auth.iterrows():
        client = row["Client"]
        auth_start = row["Auth Start"]
        auth_end = row["Auth End"]
        status = row["Status"]

        if pd.isna(auth_start) or pd.isna(auth_end):
            rows.append({
                "Client": client.title(),
                "Auth Start": pd.NaT,
                "Auth End": pd.NaT,
                "Status": status,
                "Purchased": 0.0,
                "Pending": 0.0,
                "Balance": 0.0,
                "Action": "Missing Authorization Dates"
            })
            continue

        client_data = toys[toys["Client"] == client].copy()

        purchases = client_data[
            (client_data["Purchased_bool"] == True) &
            (client_data["Timestamp_dt"] >= auth_start) &
            (client_data["Timestamp_dt"] <= auth_end)
        ]

        pending = client_data[
            (client_data["Purchased_bool"] == False) &
            (client_data["Timestamp_dt"] >= auth_start) &
            (client_data["Timestamp_dt"] <= auth_end)
        ]

        purchased = float(purchases["Amount"].sum())
        pending_total = float(pending["Amount"].sum())
        balance = max(BUDGET - purchased, 0.0)

        if today > auth_end:
            action = "Not Eligible — Await New Authorization"
            balance = 0.0
        else:
            if pending_total > 0:
                action = "Over Budget — Pending" if pending_total > balance else "Place Order"
            else:
                if purchased == 0:
                    action = "Eligible"
                elif balance == 0:
                    action = "Budget Used"
                else:
                    action = "Purchased"

        rows.append({
            "Client": client.title(),
            "Auth Start": auth_start,
            "Auth End": auth_end,
            "Status": status,
            "Purchased": purchased,
            "Pending": pending_total,
            "Balance": balance,
            "Action": action
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Client").reset_index(drop=True)
    return out

# =====================================================
# RUN
# =====================================================
try:
    toys, auth = load_data()
    summary = build_summary(toys, auth)
except Exception as e:
    st.error("❌ Failed to load data")
    st.exception(e)
    st.stop()

# =====================================================
# SIDEBAR
# =====================================================
st.sidebar.header("Filters")

if st.sidebar.button("Logout"):
    st.session_state["auth_ok"] = False
    st.rerun()

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

statuses = sorted(summary["Action"].dropna().unique().tolist()) if not summary.empty else []
selected_status = st.sidebar.multiselect("Action Status", statuses, default=statuses)

filtered = summary.copy()
if selected_status:
    filtered = filtered[filtered["Action"].isin(selected_status)].copy()

selected_client = st.sidebar.selectbox(
    "Client",
    ["(All)"] + (sorted(filtered["Client"].dropna().unique().tolist()) if not filtered.empty else [])
)

if selected_client != "(All)":
    filtered = filtered[filtered["Client"] == selected_client].copy()

# =====================================================
# KPI DISPLAY
# =====================================================
st.title("🎁 Toys Budget Dashboard (Authorization Model)")

total_purchased = float(summary["Purchased"].sum()) if not summary.empty else 0.0
total_pending = float(summary["Pending"].sum()) if not summary.empty else 0.0
not_eligible = int((summary["Action"] == "Not Eligible — Await New Authorization").sum()) if not summary.empty else 0
active_clients = int(len(summary)) if not summary.empty else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Purchased", f"${total_purchased:,.2f}")
col2.metric("Total Pending", f"${total_pending:,.2f}")
col3.metric("Clients Not Eligible", not_eligible)
col4.metric("Clients in Summary", active_clients)

# =====================================================
# DISPLAY TABLE
# =====================================================
if filtered.empty:
    st.info("No clients match the selected filters.")
    st.stop()

display = filtered.copy()
display["Auth Start"] = pd.to_datetime(display["Auth Start"], errors="coerce").dt.strftime("%m/%d/%Y").fillna("")
display["Auth End"] = pd.to_datetime(display["Auth End"], errors="coerce").dt.strftime("%m/%d/%Y").fillna("")
display["Purchased"] = display["Purchased"].map("${:,.2f}".format)
display["Pending"] = display["Pending"].map("${:,.2f}".format)
display["Balance"] = display["Balance"].map("${:,.2f}".format)

st.dataframe(
    display[
        [
            "Client",
            "Auth Start",
            "Auth End",
            "Status",
            "Purchased",
            "Pending",
            "Balance",
            "Action",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)