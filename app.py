# app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
from io import BytesIO
from PIL import Image
import os
import zipfile
import streamlit_authenticator as stauth

# ----------------------- Config -----------------------
st.set_page_config(page_title="WS7761 - Smart Meter Project Status", page_icon="📦", layout="wide")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PHOTOS_DIR = ROOT / "photos"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "stock_records.csv"

# ----------------------- Credentials (example users) -----------------------
# NOTE: For production, replace/add users and use environment variables or a secure store.
names = ["Installer One", "Admin User", "Manager User"]
usernames = ["installer1", "admin1", "manager1"]
# Use simple demo passwords here; recommend replacing them and/or using hashed values
passwords = ["install123", "admin123", "manager123"]
roles = ["installer", "admin", "manager"]

# Hash passwords for streamlit-authenticator
hashed_passwords = stauth.Hasher(passwords).generate()

credentials = {"usernames": {}}
for i, uname in enumerate(usernames):
    credentials["usernames"][uname] = {
        "name": names[i],
        "password": hashed_passwords[i],
        "role": roles[i]
    }

# Create the authenticator
authenticator = stauth.Authenticate(
    credentials,
    cookie_name="stock_app_cookie",
    key="stock_app_signature_key",  # change for production
    cookie_expiry_days=1
)

# ----------------------- Data helpers -----------------------
def load_data():
    if DATA_FILE.exists():
        try:
            df_ = pd.read_csv(DATA_FILE)
            return df_
        except Exception:
            # if file is corrupted, return empty dataframe with expected columns
            return pd.DataFrame(columns=[
                "Date", "Transaction_ID", "Action", "Meter_Type", "Meter_Quantity",
                "CIU_Quantity", "Stock_Issued_To", "Photo_Path", "Status", "Notes"
            ])
    else:
        return pd.DataFrame(columns=[
            "Date", "Transaction_ID", "Action", "Meter_Type", "Meter_Quantity",
            "CIU_Quantity", "Stock_Issued_To", "Photo_Path", "Status", "Notes"
        ])

def save_data(df_):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df_.to_csv(DATA_FILE, index=False)

def generate_txn_id():
    return f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"

# ----------------------- Login -----------------------
name, auth_status, username = authenticator.login("Login", "main")

if auth_status is False:
    st.error("❌ Username/password incorrect")
    st.stop()
if auth_status is None:
    st.warning("🔑 Please enter your username and password")
    st.stop()

# User is authenticated
authenticator.logout("Logout", "sidebar")
st.sidebar.write(f"Signed in as **{name}**")
user_role = credentials["usernames"][username]["role"]

# ----------------------- Installer (Stock Out) -----------------------
def installer_ui():
    st.title("Installer — Stock Out Form")
    st.write("Complete this form when taking stock out for installation. Upload photos showing serial numbers.")

    meter_type = st.multiselect(
        "Meter Type*",
        [
            "DN15 - 15mm LXC Blue Meter (inside blue & white meter box)",
            "CIU - White keypad with red button"
        ]
    )

    col1, col2 = st.columns(2)
    with col1:
        meter_qty = st.number_input("Meter Quantity*", min_value=0, step=1, value=0)
    with col2:
        ciu_qty = st.number_input("CIU Quantity*", min_value=0, step=1, value=0)

    stock_issued_to = st.text_input("Stock Issued To* (Installer name / team)")
    notes = st.text_area("Notes (optional)")

    uploaded_photos = st.file_uploader(
        "Photo(s) of each meter — show serial numbers (jpg/png)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if st.button("Submit Stock Out"):
        # Validation
        if not meter_type:
            st.warning("Please select at least one Meter Type.")
            return
        if not stock_issued_to:
            st.warning("Please enter who stock was issued to.")
            return

        df = load_data()
        txn_id = generate_txn_id()
        saved_photo_paths = []

        for f in uploaded_photos:
            safe_name = f"{txn_id}_{f.name}"
            dest = PHOTOS_DIR / safe_name
            with open(dest, "wb") as out:
                out.write(f.getbuffer())
            saved_photo_paths.append(str(dest))

        entry = {
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Transaction_ID": txn_id,
            "Action": "Stock Out",
            "Meter_Type": ", ".join(meter_type),
            "Meter_Quantity": int(meter_qty),
            "CIU_Quantity": int(ciu_qty),
            "Stock_Issued_To": stock_issued_to,
            "Photo_Path": "|".join(saved_photo_paths),
            "Status": "Pending Approval",
            "Notes": notes or ""
        }

        df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
        save_data(df)
        st.success(f"Stock Out recorded. Transaction ID: {txn_id}")
        if saved_photo_paths:
            st.info(f"{len(saved_photo_paths)} photo(s) saved to `photos/`.")

# ----------------------- Admin (Approve/Reject) -----------------------
def admin_ui():
    st.title("Admin Dashboard — Review Stock Out Requests")
    df = load_data()

    if df.empty:
        st.info("No transactions recorded yet.")
        return

    status_filter = st.selectbox("Filter by Status", ["All", "Pending Approval", "Approved", "Rejected"])
    if status_filter == "All":
        display_df = df.copy()
    else:
        display_df = df[df["Status"] == status_filter].copy()

    display_df = display_df.sort_values(by="Date", ascending=False).reset_index(drop=True)
    st.dataframe(display_df, use_container_width=True)

    st.markdown("---")
    st.subheader("Approve / Reject")
    txn_options = [""] + df["Transaction_ID"].tolist()
    selected_txn = st.selectbox("Select Transaction to act on", txn_options)
    if selected_txn:
        row = df[df["Transaction_ID"] == selected_txn].iloc[0]
        st.write("**Selected transaction details:**")
        st.write(row.to_dict())

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Approve Transaction"):
                df.loc[df["Transaction_ID"] == selected_txn, "Status"] = "Approved"
                save_data(df)
                st.success(f"Transaction {selected_txn} Approved.")
        with col2:
            if st.button("Reject Transaction"):
                df.loc[df["Transaction_ID"] == selected_txn, "Status"] = "Rejected"
                save_data(df)
                st.error(f"Transaction {selected_txn} Rejected.")

    st.markdown("---")
    st.subheader("View Photos")
    view_txn = st.selectbox("Select Transaction to view photos", options=[""] + df["Transaction_ID"].tolist(), key="view_photos")
    if view_txn:
        row = df[df["Transaction_ID"] == view_txn].iloc[0]
        photo_field = row.get("Photo_Path", "")
        if pd.isna(photo_field) or not photo_field:
            st.info("No photos uploaded for this transaction.")
        else:
            paths = photo_field.split("|")
            for p in paths:
                if os.path.exists(p):
                    try:
                        img = Image.open(p)
                        st.image(img, caption=os.path.basename(p), use_column_width=True)
                    except Exception as e:
                        st.warning(f"Could not open image {p}: {e}")
                else:
                    st.warning(f"Photo file missing: {p}")

# ----------------------- Manager (Reconciliation & Exports) -----------------------
def manager_ui():
    st.title("Manager — Reconciliation & Exports")
    df = load_data()
    if df.empty:
        st.info("No data to reconcile.")
        return

    st.subheader("Quick Summary")
    try:
        summary = df.groupby(["Meter_Type", "Status"], as_index=False)[["Meter_Quantity", "CIU_Quantity"]].sum()
        st.dataframe(summary, use_container_width=True)
    except Exception:
        st.warning("Could not generate summary. Check ledger data format.")

    st.markdown("---")
    st.subheader("Download full ledger (CSV)")
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download CSV", csv_bytes, "stock_records.csv", "text/csv")

    st.subheader("Download photos as ZIP (all photos)")
    def make_photos_zip():
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in PHOTOS_DIR.glob("*"):
                z.write(p, arcname=p.name)
        buf.seek(0)
        return buf

    if any(PHOTOS_DIR.iterdir()):
        zip_buf = make_photos_zip()
        st.download_button("📦 Download photos.zip", zip_buf, file_name="photos.zip", mime="application/zip")
    else:
        st.info("No photos available yet.")

# ----------------------- Route to the right UI based on role -----------------------
if user_role == "installer":
    installer_ui()
elif user_role == "admin":
    admin_ui()
elif user_role == "manager":
    manager_ui()
else:
    st.error("User role not recognized. Contact the system administrator.")
