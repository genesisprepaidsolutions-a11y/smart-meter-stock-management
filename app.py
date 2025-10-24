# app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
from io import BytesIO
from PIL import Image
import os
import zipfile

# ----------------------- Config -----------------------
st.set_page_config(page_title="Smart Meter Stock Management", page_icon="📦", layout="wide")
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PHOTOS_DIR = ROOT / "photos"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "stock_ledger.csv"

# ----------------------- Load / Initialize Ledger -----------------------
if DATA_FILE.exists():
    try:
        df = pd.read_csv(DATA_FILE)
    except Exception:
        # fallback to blank df if corrupted
        df = pd.DataFrame(columns=[
            "Date", "Transaction_ID", "Action", "Meter_Type", "Meter_Quantity",
            "CIU_Quantity", "Stock_Issued_To", "Photo_Path", "Status", "Notes"
        ])
else:
    df = pd.DataFrame(columns=[
        "Date", "Transaction_ID", "Action", "Meter_Type", "Meter_Quantity",
        "CIU_Quantity", "Stock_Issued_To", "Photo_Path", "Status", "Notes"
    ])

def save_data(df_):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df_.to_csv(DATA_FILE, index=False)

def generate_txn_id():
    return f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}"

# ----------------------- UI -----------------------
st.title("📦 Smart Meter Stock Management System")
st.write("Installers submit Stock Out forms (with serial-number photos). Admins can approve, reject, and export data.")

tabs = st.tabs(["Installer: Stock Out Form", "Admin Dashboard", "Reconciliation & Exports"])

# ----------------------- Installer Form -----------------------
with tabs[0]:
    st.header("Installer — Stock Out (Acceptance)")
    st.write("Complete this form when taking stock out for installation. Upload photos showing serial numbers.")

    acceptance = st.radio("Acceptance of Stock*", ["Stock Out"], index=0)

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
        "Photo(s) of each meter — show serial numbers (jpg/png) *",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )

    if st.button("Submit Stock Out"):
        # Validation
        if not meter_type:
            st.warning("Please select at least one Meter Type.")
        elif not stock_issued_to:
            st.warning("Please enter who stock was issued to.")
        else:
            txn_id = generate_txn_id()
            saved_photo_paths = []

            for f in uploaded_photos:
                # make a safe file name
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

# ----------------------- Admin Dashboard -----------------------
with tabs[1]:
    st.header("Admin Dashboard — Review Stock Out Requests")
    if df.empty:
        st.info("No transactions recorded yet.")
    else:
        status_filter = st.selectbox("Filter by Status", ["All", "Pending Approval", "Approved", "Rejected"])
        if status_filter == "All":
            display_df = df.copy()
        else:
            display_df = df[df["Status"] == status_filter].copy()

        display_df = display_df.sort_values(by="Date", ascending=False)
        st.dataframe(display_df.reset_index(drop=True), use_container_width=True)

        st.markdown("---")
        st.subheader("Approve / Reject Transactions")
        col_a, col_b = st.columns(2)

        with col_a:
            approve_id = st.text_input("Transaction ID to Approve", key="approve")
            if st.button("Approve Transaction"):
                if approve_id and approve_id in df["Transaction_ID"].values:
                    df.loc[df["Transaction_ID"] == approve_id, "Status"] = "Approved"
                    save_data(df)
                    st.success(f"Transaction {approve_id} Approved.")
                else:
                    st.error("Transaction ID not found or empty.")

        with col_b:
            reject_id = st.text_input("Transaction ID to Reject", key="reject")
            if st.button("Reject Transaction"):
                if reject_id and reject_id in df["Transaction_ID"].values:
                    df.loc[df["Transaction_ID"] == reject_id, "Status"] = "Rejected"
                    save_data(df)
                    st.error(f"Transaction {reject_id} Rejected.")
                else:
                    st.error("Transaction ID not found or empty.")

        st.markdown("---")
        st.subheader("View Photos for a Transaction")
        txn_options = [""] + df["Transaction_ID"].tolist()
        view_txn = st.selectbox("Select Transaction ID to view photos", options=txn_options, key="view_photos")
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

# ----------------------- Reconciliation & Exports -----------------------
with tabs[2]:
    st.header("Reconciliation & Exports")
    if df.empty:
        st.info("No data to reconcile.")
    else:
        st.subheader("Quick Summary")
        try:
            summary = df.groupby(["Meter_Type", "Status"], as_index=False)[["Meter_Quantity", "CIU_Quantity"]].sum()
            st.dataframe(summary, use_container_width=True)
        except Exception:
            st.warning("Could not generate summary. Check ledger data format.")

        st.markdown("---")
        st.subheader("Download full ledger")
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", csv_bytes, "stock_ledger.csv", "text/csv")

        st.subheader("Download photos as ZIP (all photos)")
        # Create zip in memory
        def make_photos_zip():
            buf = BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for p in PHOTOS_DIR.glob("*"):
                    # add file with just file name (no folders)
                    z.write(p, arcname=p.name)
            buf.seek(0)
            return buf

        if any(PHOTOS_DIR.iterdir()):
            zip_buf = make_photos_zip()
            st.download_button("📦 Download photos.zip", zip_buf, file_name="photos.zip", mime="application/zip")
        else:
            st.info("No photos available yet.")

    st.markdown("---")
    st.markdown("*Tip: `data/stock_ledger.csv` and the `photos/` folder are created next to the app. Back them up regularly.*")
