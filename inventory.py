import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import os
import io
import re
from fpdf import FPDF
from PIL import Image
try:
    import pytesseract
    OCR_AVAILABLE = True
    # Windows installer does not add Tesseract to PATH by default —
    # point pytesseract directly at the default install location if found.
    _default_win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(_default_win_path):
        pytesseract.pytesseract.tesseract_cmd = _default_win_path
except ImportError:
    OCR_AVAILABLE = False

st.set_page_config(page_title="Atlantic Design — Inventory", page_icon="🧵", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0a0f1a; }
[data-testid="stHeader"] { background-color: #0a0f1a; }
h1,h2,h3,h4 { color: #d4a017 !important; }
[data-testid="metric-container"] {
    background: #131b2c;
    border: 1px solid #2a3550;
    border-radius: 10px;
    padding: 15px;
}
</style>
""", unsafe_allow_html=True)

INV_FILE   = "inventory.csv"
ISSUE_FILE = "issuance_log.csv"

def generate_inventory_pdf(data):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'ATLANTIC DESIGN', ln=True, align='C')
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, 'Inventory Report', ln=True, align='C')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d %b %Y %I:%M %p')}", ln=True, align='C')
    pdf.ln(4)

    headers    = ['Item Name','Category','Unit','Current','Minimum','Price (Rs)','Received','Status','Value (Rs)']
    col_widths = [58, 30, 20, 22, 22, 24, 26, 24, 30]

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(20, 30, 50)
    pdf.set_text_color(255, 255, 255)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Helvetica', '', 8)
    for _, row in data.iterrows():
        status_txt = row['Status'].split(' ', 1)[-1] if ' ' in row['Status'] else row['Status']
        values = [
            str(row['Item_Name']), str(row['Category']), str(row['Unit']),
            f"{row['Current_Stock']}", f"{row['Minimum_Stock']}",
            f"{row['Unit_Price']:.2f}", row['Received_Date'].strftime('%d %b %Y'),
            status_txt, f"{row['Total_Value']:,.0f}"
        ]
        for v, w in zip(values, col_widths):
            safe_v = v.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(w, 7, safe_v, border=1)
        pdf.ln()

    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 8, f"Total Stock Value: Rs {data['Total_Value'].sum():,.0f}", ln=True)

    return bytes(pdf.output())

def generate_daily_issuance_pdf(idf, report_date):
    """Builds a PDF for a single day: every issuance transaction that day,
    plus a per-worker total, so it's clear who took what and how much."""
    day_data = idf[idf['Date'].dt.date == report_date].copy() if len(idf) > 0 else idf.copy()
    day_data = day_data.sort_values(['Worker_Name', 'Date']) if len(day_data) > 0 else day_data

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'ATLANTIC DESIGN', ln=True, align='C')
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(0, 8, 'Daily Worker Issuance Report', ln=True, align='C')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f"Date: {report_date.strftime('%d %b %Y')}", ln=True, align='C')
    pdf.ln(4)

    if len(day_data) == 0:
        pdf.set_font('Helvetica', '', 11)
        pdf.cell(0, 10, 'No material was issued on this date.', ln=True, align='C')
        return bytes(pdf.output())

    headers    = ['Time', 'Worker Name', 'Item Name', 'Quantity', 'Unit', 'Order Ref', 'Remarks']
    col_widths = [25, 45, 60, 25, 25, 35, 62]

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(20, 30, 50)
    pdf.set_text_color(255, 255, 255)
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Helvetica', '', 8)
    for _, row in day_data.iterrows():
        values = [
            row['Date'].strftime('%I:%M %p'),
            str(row['Worker_Name']),
            str(row['Item_Name']),
            f"{row['Quantity']}",
            str(row['Unit']),
            str(row['Order_Ref']) if pd.notna(row['Order_Ref']) else '',
            str(row['Remarks']) if pd.notna(row['Remarks']) else ''
        ]
        for v, w in zip(values, col_widths):
            safe_v = v.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(w, 7, safe_v, border=1)
        pdf.ln()

    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 8, f"Total Transactions: {len(day_data)}  |  Total Quantity Issued: {day_data['Quantity'].sum():.0f}", ln=True)

    pdf.ln(2)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(0, 7, 'Worker-wise Summary for the Day:', ln=True)
    pdf.set_font('Helvetica', '', 8)
    day_summary = day_data.groupby('Worker_Name')['Quantity'].sum().reset_index()
    for _, r in day_summary.iterrows():
        pdf.cell(0, 6, f"  - {r['Worker_Name']}: {r['Quantity']:.0f} units taken", ln=True)

    return bytes(pdf.output())

def parse_ocr_lines(text):
    """Best-effort parser: turns messy OCR text lines into draft inventory rows.
    Anchors on a $/₹-prefixed number as the price (most reliable signal in noisy
    OCR text), treats leading words as the item name, and looks for the next
    plain integer after the price as the quantity."""
    rows = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        line = re.sub(r'^[>\-–—•\s]+', '', line)   # strip leading junk like '>', '-', bullets
        if not line or len(line) < 3:
            continue
        tokens = line.split()

        priced_idxs = [i for i, t in enumerate(tokens) if re.match(r'^[\$₹][\d,]+\.?\d*$', t)]
        if priced_idxs:
            price_idx = priced_idxs[0]
        else:
            decimal_idxs = [i for i, t in enumerate(tokens) if re.match(r'^\d+\.\d+$', t)]
            if not decimal_idxs:
                continue
            price_idx = decimal_idxs[0]

        name_tokens = tokens[:price_idx]
        # drop pure alphanumeric codes like IN0015 / Desc47 from the name
        name_tokens = [t for t in name_tokens if not re.match(r'^[A-Za-z]{1,4}\d{2,}$', t)]
        name = ' '.join(name_tokens).strip(' .,:-')
        if not name:
            continue

        def clean_num(t):
            try:
                return float(t.replace('$', '').replace('₹', '').replace(',', ''))
            except ValueError:
                return None

        price = clean_num(tokens[price_idx])

        qty = None
        for t in tokens[price_idx + 1:]:
            if re.match(r'^\d+$', t):
                qty = float(t)
                break

        rows.append({
            'Item_Name': name.title(),
            'Category': 'Other',
            'Unit': 'Pieces',
            'Current_Stock': qty if qty is not None else 0,
            'Minimum_Stock': 10,
            'Unit_Price': price if price is not None else 0.0,
            'Received_Date': pd.Timestamp(date.today())
        })
    return pd.DataFrame(rows)

def get_default_inventory():
    return pd.DataFrame({
        'Item_Name'    : ['Cotton Poplin Fabric','Polyester Thread - Black','Denim Fabric 12oz',
                          'YKK Zippers 7"','Metal Buttons 15mm','Woven Care Labels',
                          'Fusible Interlining','Poly Bags (Garment)','Corrugated Cartons',
                          'Elastic Band 1"'],
        'Category'     : ['Fabric','Thread','Fabric','Trims','Trims','Labels',
                          'Interlining','Packaging','Packaging','Trims'],
        'Unit'         : ['Meters','Rolls','Meters','Pieces','Pieces','Pieces',
                          'Meters','Pieces','Pieces','Meters'],
        'Current_Stock': [1200,45,600,3000,8000,5000,300,10000,400,150],
        'Minimum_Stock': [500,50,300,2000,5000,4000,200,5000,300,200],
        'Unit_Price'   : [180,35,320,4,1,0.8,25,2,15,6],
        'Received_Date': ['2026-05-10','2026-04-01','2026-06-15','2026-03-20',
                          '2026-06-25','2026-02-10','2026-05-28','2026-06-01',
                          '2026-01-15','2026-04-18']
    })

def get_default_issuance():
    return pd.DataFrame(columns=['Date','Worker_Name','Item_Name','Quantity','Unit','Order_Ref','Remarks'])

def load_inventory():
    df = pd.read_csv(INV_FILE) if os.path.exists(INV_FILE) else get_default_inventory()
    df['Received_Date'] = pd.to_datetime(df['Received_Date'], errors='coerce')
    df['Days_In_Stock']  = (pd.Timestamp.now() - df['Received_Date']).dt.days
    df['Status']      = df.apply(lambda r: '🚨 Critical' if r['Current_Stock'] <= r['Minimum_Stock']*0.5
                                 else ('⚠️ Low' if r['Current_Stock'] <= r['Minimum_Stock'] else '✅ OK'), axis=1)
    df['Total_Value'] = df['Current_Stock'] * df['Unit_Price']
    return df

def save_inventory(df):
    out = df[['Item_Name','Category','Unit','Current_Stock','Minimum_Stock','Unit_Price','Received_Date']].copy()
    out['Received_Date'] = pd.to_datetime(out['Received_Date']).dt.strftime('%Y-%m-%d')
    out.to_csv(INV_FILE, index=False)

def load_issuance():
    if os.path.exists(ISSUE_FILE):
        idf = pd.read_csv(ISSUE_FILE)
    else:
        idf = get_default_issuance()
    if len(idf) > 0:
        idf['Date'] = pd.to_datetime(idf['Date'], errors='coerce')
    return idf

def save_issuance(idf):
    out = idf.copy()
    out['Date'] = pd.to_datetime(out['Date']).dt.strftime('%Y-%m-%d %H:%M')
    out.to_csv(ISSUE_FILE, index=False)

df  = load_inventory()
idf = load_issuance()
CATS = ['Fabric','Thread','Trims','Labels','Interlining','Packaging','Dyes & Chemicals','Other']
UNITS = ['Meters','Rolls','Pieces','Kg','Dozen','Boxes']

# ── HEADER ──────────────────────────────────────────────────────────────────
st.markdown("# ATLANTIC DESIGN")
st.caption("Fabric, Trims, Packaging Stock & Worker Material Issuance")

st.markdown("---")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Dashboard", "📋 Inventory", "➕ Add Material", "✏️ Update Stock",
    "👷 Worker Issuance", "📸 Upload Photo"
])

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
with tab1:
    today_issue = idf[idf['Date'].dt.date == date.today()] if len(idf) > 0 else idf

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("🧾 Total SKUs",        len(df))
    c2.metric("🚨 Critical Stock",    len(df[df['Status']=='🚨 Critical']))
    c3.metric("📦 Ageing >180 days",  len(df[df['Days_In_Stock']>180]))
    c4.metric("💰 Total Stock Value", f"₹{df['Total_Value'].sum():,.0f}")
    c5.metric("👷 Issued Today",      f"{today_issue['Quantity'].sum():.0f}" if len(today_issue)>0 else "0")

    if len(today_issue) > 0:
        st.markdown("#### ⚡ Live — Material Issued Today")
        tshow_top = today_issue.sort_values('Date', ascending=False).copy()
        tshow_top['Date'] = tshow_top['Date'].dt.strftime('%I:%M %p')
        for _, r in tshow_top.iterrows():
            st.markdown(
                f"🟢 `{r['Date']}` **{r['Worker_Name']}** took **{r['Quantity']} {r['Unit']}** of **{r['Item_Name']}**"
                + (f" · Ref: {r['Order_Ref']}" if pd.notna(r['Order_Ref']) and str(r['Order_Ref']).strip() else "")
            )

    st.markdown("---")
    cat_grp = df.groupby('Category')['Current_Stock'].sum().reset_index()

    l,r = st.columns(2)
    with l:
        st.markdown("#### Stock by Category")
        fig = px.bar(cat_grp, x='Category', y='Current_Stock', color='Category',
                     template='plotly_dark', color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_layout(plot_bgcolor='#131b2c', paper_bgcolor='#131b2c',
                          showlegend=False, height=280, margin=dict(l=5,r=5,t=5,b=5))
        st.plotly_chart(fig, use_container_width=True)

    with r:
        st.markdown("#### Category Split")
        fig2 = px.pie(cat_grp, names='Category', values='Current_Stock', hole=0.45,
                      template='plotly_dark', color_discrete_sequence=px.colors.qualitative.Bold)
        fig2.update_layout(plot_bgcolor='#131b2c', paper_bgcolor='#131b2c',
                           height=280, margin=dict(l=5,r=5,t=5,b=5))
        st.plotly_chart(fig2, use_container_width=True)

    l2,r2 = st.columns(2)
    with l2:
        st.markdown("#### Current vs Minimum Stock")
        low6 = df.sort_values('Current_Stock').head(6)
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(name='Current', x=low6['Item_Name'], y=low6['Current_Stock'], marker_color='#d4a017'))
        fig3.add_trace(go.Bar(name='Minimum', x=low6['Item_Name'], y=low6['Minimum_Stock'], marker_color='#ff3d5a'))
        fig3.update_layout(barmode='group', template='plotly_dark',
                           plot_bgcolor='#131b2c', paper_bgcolor='#131b2c',
                           height=280, margin=dict(l=5,r=5,t=5,b=5))
        st.plotly_chart(fig3, use_container_width=True)

    with r2:
        st.markdown("#### Top Workers by Material Taken (All Time)")
        if len(idf) > 0:
            wk = idf.groupby('Worker_Name')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=True).tail(6)
            fig5 = px.bar(wk, x='Quantity', y='Worker_Name', orientation='h',
                          color='Quantity', color_continuous_scale='Oranges', template='plotly_dark')
            fig5.update_layout(plot_bgcolor='#131b2c', paper_bgcolor='#131b2c',
                               height=280, margin=dict(l=5,r=5,t=5,b=5), coloraxis_showscale=False)
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.info("No material issued yet. Use the 'Worker Issuance' tab to log an issue.")

    st.markdown("---")
    st.markdown("#### 🔔 Alerts")
    crits = df[df['Status']=='🚨 Critical']
    lows  = df[df['Status']=='⚠️ Low']
    aging = df[df['Days_In_Stock']>180]

    if len(crits)==0 and len(lows)==0 and len(aging)==0:
        st.success("✅ All stock levels are healthy. No alerts.")
    for _,row in crits.iterrows():
        st.error(f"🚨 **{row['Item_Name']}** — Only {row['Current_Stock']} {row['Unit']} left | Min required: {row['Minimum_Stock']} {row['Unit']} | CRITICAL")
    for _,row in lows.iterrows():
        st.warning(f"⚠️ **{row['Item_Name']}** — {row['Current_Stock']} {row['Unit']} | Min required: {row['Minimum_Stock']} {row['Unit']} | LOW STOCK")
    for _,row in aging.iterrows():
        st.warning(f"📦 **{row['Item_Name']}** — In stock for {int(row['Days_In_Stock'])} days (received {row['Received_Date'].strftime('%d %b %Y')}) — check for slow-moving/dead stock")

# ── INVENTORY TABLE ───────────────────────────────────────────────────────────
with tab2:
    st.markdown("#### 📋 Full Inventory")
    s1,s2,s3 = st.columns(3)
    search = s1.text_input("🔍 Search", placeholder="Item name...")
    f_cat  = s2.selectbox("Category", ["All"]+sorted(df['Category'].unique().tolist()))
    f_stat = s3.selectbox("Status",   ["All","✅ OK","⚠️ Low","🚨 Critical"])

    res = df.copy()
    if search:       res = res[res['Item_Name'].str.contains(search, case=False, na=False)]
    if f_cat  != "All": res = res[res['Category']==f_cat]
    if f_stat != "All": res = res[res['Status']==f_stat]

    show = res[['Item_Name','Category','Unit','Current_Stock','Minimum_Stock',
                'Unit_Price','Received_Date','Days_In_Stock','Status','Total_Value']].copy()
    show['Received_Date'] = res['Received_Date'].dt.strftime('%d %b %Y').values
    show['Unit_Price']    = res['Unit_Price'].apply(lambda x: f"₹{x}").values
    show['Total_Value']   = res['Total_Value'].apply(lambda x: f"₹{x:,.0f}").values
    show['Days_In_Stock'] = res['Days_In_Stock'].apply(lambda x: f"{int(x)}d").values

    st.dataframe(show, use_container_width=True, height=400)
    st.caption(f"{len(res)} of {len(df)} records")

    pdf_bytes = generate_inventory_pdf(res if len(res) > 0 else df)
    st.download_button("⬇️ Download PDF", pdf_bytes, "atlantic_design_inventory.pdf", "application/pdf")

    st.markdown("---")
    with st.expander("🗑️ Delete a Material"):
        del_item = st.selectbox("Select Material to Delete", options=sorted(df['Item_Name'].unique()), key="inv_del_select")
        st.warning(f"Ye **{del_item}** ko poori tarah inventory se hata dega. Ye action undo nahi ho sakta.")
        confirm_inv_del = st.checkbox(f"Haan, main confirm karta/karti hoon", key="inv_confirm_delete")
        if st.button("🗑️ Delete Permanently", type="primary", disabled=not confirm_inv_del, key="inv_del_btn"):
            fresh = load_inventory()
            fresh = fresh[fresh['Item_Name'] != del_item]
            save_inventory(fresh)
            st.success(f"✅ {del_item} deleted from inventory.")
            st.rerun()

# ── ADD NEW MATERIAL ──────────────────────────────────────────────────────────
with tab3:
    st.markdown("#### ➕ Add New Material")
    st.info("Only use this to add a material that is not already in the inventory.")

    with st.form("add_form", clear_on_submit=True):
        a1,a2,a3 = st.columns(3)
        nm  = a1.text_input("Material Name *")
        cat = a2.selectbox("Category *", ['Select...']+CATS)
        unit = a3.selectbox("Unit *", ['Select...']+UNITS)
        b1,b2,b3 = st.columns(3)
        stk = b1.number_input("Current Stock *", min_value=0, step=1)
        mn  = b2.number_input("Minimum Stock *", min_value=1, step=1, value=100)
        prc = b3.number_input("Unit Price ₹ *",  min_value=0.0, step=0.5)
        rcv = st.date_input("Received Date *", value=date.today(), max_value=date.today())
        btn = st.form_submit_button("➕ Add Material", use_container_width=True)

    if btn:
        if not nm or cat == 'Select...' or unit == 'Select...':
            st.error("❌ Please fill all fields.")
        else:
            fresh = load_inventory()
            if (fresh['Item_Name'].str.lower() == nm.lower()).any():
                st.error(f"❌ **{nm}** already exists. Go to Update Stock tab.")
            else:
                new_row = pd.DataFrame([{'Item_Name':nm,'Category':cat,'Unit':unit,'Current_Stock':stk,
                                         'Minimum_Stock':mn,'Unit_Price':prc,'Received_Date':pd.Timestamp(rcv)}])
                fresh = pd.concat([fresh, new_row], ignore_index=True)
                save_inventory(fresh)
                st.success(f"✅ {nm} added successfully!")
                st.rerun()

# ── UPDATE EXISTING STOCK ──────────────────────────────────────────────────────
with tab4:
    st.markdown("#### ✏️ Update Stock")

    item = st.selectbox(
        "🔍 Search & Select Material",
        options=sorted(df['Item_Name'].unique())
    )

    row = df[df['Item_Name'] == item].iloc[0]

    col1, col2, col3 = st.columns([1,1,1])

    with col1:
        if st.button("➖", key="minus"):
            if row['Current_Stock'] > 0:
                df.loc[df['Item_Name']==item, 'Current_Stock'] -= 1
                save_inventory(df)
                st.rerun()

    with col2:
        st.markdown(
            f"<h3 style='text-align:center'>{row['Current_Stock']} {row['Unit']}</h3>",
            unsafe_allow_html=True
        )

    with col3:
        if st.button("➕", key="plus"):
            df.loc[df['Item_Name']==item, 'Current_Stock'] += 1
            save_inventory(df)
            st.rerun()

    new_stock = st.number_input("Or Enter Exact Stock", value=int(row['Current_Stock']))

    if st.button("Update Exact Value"):
        df.loc[df['Item_Name']==item, 'Current_Stock'] = new_stock
        save_inventory(df)
        st.success("Updated successfully")
        st.rerun()

    st.markdown("---")
    with st.expander("🗑️ Delete this Material"):
        st.warning(f"Ye **{item}** ko poori tarah inventory se hata dega. Ye action undo nahi ho sakta.")
        confirm_del = st.checkbox(f"Haan, main confirm karta/karti hoon ki **{item}** delete karna hai", key="confirm_delete")
        if st.button("🗑️ Delete Permanently", type="primary", disabled=not confirm_del):
            fresh = load_inventory()
            fresh = fresh[fresh['Item_Name'] != item]
            save_inventory(fresh)
            st.success(f"✅ {item} deleted from inventory.")
            st.rerun()

# ── WORKER ISSUANCE ─────────────────────────────────────────────────────────────
with tab5:
    st.markdown("#### 👷 Issue Material to Worker")
    st.info("Jab bhi koi worker material leke jaye, yaha entry karo — stock turant deduct ho jayega aur record neeche dikhega.")

    with st.form("issue_form", clear_on_submit=True):
        w1,w2 = st.columns(2)
        worker_name = w1.text_input("Worker Name *", placeholder="e.g. Ramesh Kumar")
        item_pick   = w2.selectbox("Material *", options=sorted(df['Item_Name'].unique()))

        avail = df[df['Item_Name']==item_pick].iloc[0]
        w3,w4 = st.columns(2)
        qty      = w3.number_input(f"Quantity to Issue ({avail['Unit']}) *", min_value=0.0, step=1.0)
        order_ref = w4.text_input("Order / Style Ref (optional)", placeholder="e.g. PO-2201")
        remarks  = st.text_input("Remarks (optional)")
        st.caption(f"Available stock: **{avail['Current_Stock']} {avail['Unit']}**")
        issue_btn = st.form_submit_button("👷 Issue Material", use_container_width=True, type="primary")

    if issue_btn:
        if not worker_name.strip():
            st.error("❌ Please enter worker name.")
        elif qty <= 0:
            st.error("❌ Quantity must be greater than 0.")
        else:
            fresh_df  = load_inventory()
            fresh_idf = load_issuance()
            cur_stock = fresh_df.loc[fresh_df['Item_Name']==item_pick, 'Current_Stock'].values[0]
            if qty > cur_stock:
                st.error(f"❌ Not enough stock. Only {cur_stock} {avail['Unit']} available.")
            else:
                fresh_df.loc[fresh_df['Item_Name']==item_pick, 'Current_Stock'] -= qty
                save_inventory(fresh_df)

                new_entry = pd.DataFrame([{
                    'Date': datetime.now(), 'Worker_Name': worker_name.strip(),
                    'Item_Name': item_pick, 'Quantity': qty, 'Unit': avail['Unit'],
                    'Order_Ref': order_ref, 'Remarks': remarks
                }])
                fresh_idf = pd.concat([fresh_idf, new_entry], ignore_index=True)
                save_issuance(fresh_idf)

                st.success(f"✅ {qty} {avail['Unit']} of **{item_pick}** issued to **{worker_name}**. Stock updated instantly — see below.")
                st.balloons()
                st.rerun()

    # Live "just happened" strip — always visible at the top of this tab
    live_idf = load_issuance()
    if len(live_idf) > 0:
        st.markdown("#### ⚡ Live — Most Recent Issues")
        recent = live_idf.sort_values('Date', ascending=False).head(5).copy()
        recent['Date'] = recent['Date'].dt.strftime('%d %b %Y %I:%M %p')
        for _, r in recent.iterrows():
            st.markdown(
                f"🟢 **{r['Worker_Name']}** took **{r['Quantity']} {r['Unit']}** of **{r['Item_Name']}** — {r['Date']}"
                + (f" · Ref: {r['Order_Ref']}" if pd.notna(r['Order_Ref']) and str(r['Order_Ref']).strip() else "")
            )

    # ── DAILY WORKER REPORT (PDF) ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🗓️ Daily Worker Report (PDF)")
    st.caption("Kisi bhi din ka pura record nikalo — kis worker ne us din kya-kya saman liya.")

    rep_col1, rep_col2 = st.columns([1, 2])
    report_date = rep_col1.date_input(
        "Report ke liye date chuno",
        value=date.today(),
        max_value=date.today(),
        key="daily_report_date"
    )

    day_count = len(idf[idf['Date'].dt.date == report_date]) if len(idf) > 0 else 0
    rep_col2.markdown(
        f"<div style='padding-top:28px'>📌 <b>{day_count}</b> transaction(s) is din ke liye mile.</div>",
        unsafe_allow_html=True
    )

    daily_pdf_bytes = generate_daily_issuance_pdf(idf, report_date)
    st.download_button(
        "⬇️ Download Daily Report PDF",
        daily_pdf_bytes,
        f"daily_issuance_report_{report_date.strftime('%Y-%m-%d')}.pdf",
        "application/pdf",
        type="primary"
    )

    st.markdown("---")
    st.markdown("#### 📜 Issuance History")

    if len(idf) == 0:
        st.info("Abhi tak koi material issue nahi hua hai.")
    else:
        h1,h2,h3 = st.columns(3)
        f_worker = h1.selectbox("Filter by Worker", ["All"]+sorted(idf['Worker_Name'].unique().tolist()))
        f_item   = h2.selectbox("Filter by Material", ["All"]+sorted(idf['Item_Name'].unique().tolist()))
        f_date   = h3.date_input("Filter by Date (optional)", value=None)

        hres = idf.copy()
        if f_worker != "All": hres = hres[hres['Worker_Name']==f_worker]
        if f_item   != "All": hres = hres[hres['Item_Name']==f_item]
        if f_date:            hres = hres[hres['Date'].dt.date == f_date]

        hshow = hres.sort_values('Date', ascending=False).copy()
        hshow['Date'] = hshow['Date'].dt.strftime('%d %b %Y %I:%M %p')
        st.dataframe(hshow, use_container_width=True, height=350)
        st.caption(f"{len(hres)} of {len(idf)} records")

        wk_summary = idf.groupby('Worker_Name').agg(
            Total_Items_Taken=('Quantity','sum'),
            Total_Transactions=('Quantity','count')
        ).reset_index().sort_values('Total_Items_Taken', ascending=False)
        st.markdown("##### 👷 Worker-wise Summary (All Time)")
        st.dataframe(wk_summary, use_container_width=True)

        st.download_button("⬇️ Download Issuance Log", idf.to_csv(index=False), "issuance_log.csv", "text/csv")

# ── UPLOAD PHOTO ──────────────────────────────────────────────────────────────
with tab6:
    st.markdown("#### 📸 Upload Photo to Add Stock")
    st.info("Stock register, bill, ya packing list ki photo upload karo. System usme se text nikaalne ki koshish karega, jise dekh kar aap neeche diye form se material add kar sakte ho.")

    photo = st.file_uploader("Choose Photo", type=['jpg','jpeg','png','webp'])

    if photo:
        image = Image.open(photo)
        st.image(image, caption="Uploaded Photo", use_container_width=True)

        if not OCR_AVAILABLE:
            st.warning("⚠️ OCR engine (pytesseract) install nahi hai. Photo dikh rahi hai, lekin text automatically nahi nikal payega.")
            st.code("pip install pytesseract pillow --break-system-packages", language="bash")
            st.caption("Windows par Tesseract-OCR bhi alag se install karna hoga: https://github.com/UB-Mannheim/tesseract/wiki")
        else:
            try:
                extracted_text = pytesseract.image_to_string(image)
                if extracted_text.strip():
                    st.success("✅ Photo se ye text nikla hai:")
                    st.text_area("Extracted Text (raw)", value=extracted_text, height=140)

                    draft = parse_ocr_lines(extracted_text)
                    if len(draft) > 0:
                        st.markdown("##### ✏️ Auto-detected Items — Check & Correct Below")
                        st.caption("System ne khud rows bana di hain. Galat values ko table mein hi edit kar do (double-click karke), Category/Unit set karo, aur jo row chahiye nahi use delete kar do. Fir 'Add All' dabao.")

                        edited = st.data_editor(
                            draft,
                            num_rows="dynamic",
                            use_container_width=True,
                            column_config={
                                "Category": st.column_config.SelectboxColumn("Category", options=CATS),
                                "Unit": st.column_config.SelectboxColumn("Unit", options=UNITS),
                                "Unit_Price": st.column_config.NumberColumn("Unit_Price (₹)", min_value=0.0, step=0.5),
                                "Current_Stock": st.column_config.NumberColumn("Current_Stock", min_value=0, step=1),
                                "Minimum_Stock": st.column_config.NumberColumn("Minimum_Stock", min_value=1, step=1),
                                "Received_Date": st.column_config.DateColumn("Received_Date"),
                            },
                            key="ocr_editor"
                        )

                        if st.button("✅ Add All to Inventory", type="primary", use_container_width=True):
                            fresh = load_inventory()
                            added, skipped = 0, 0
                            for _, r in edited.iterrows():
                                nm = str(r['Item_Name']).strip()
                                if not nm:
                                    continue
                                if (fresh['Item_Name'].str.lower() == nm.lower()).any():
                                    skipped += 1
                                    continue
                                new_row = pd.DataFrame([{
                                    'Item_Name': nm, 'Category': r['Category'], 'Unit': r['Unit'],
                                    'Current_Stock': r['Current_Stock'], 'Minimum_Stock': r['Minimum_Stock'],
                                    'Unit_Price': r['Unit_Price'], 'Received_Date': pd.Timestamp(r['Received_Date'])
                                }])
                                fresh = pd.concat([fresh, new_row], ignore_index=True)
                                added += 1
                            save_inventory(fresh)
                            msg = f"✅ {added} material(s) added to inventory."
                            if skipped:
                                msg += f" ⚠️ {skipped} skipped (already existed)."
                            st.success(msg)
                            st.rerun()
                    else:
                        st.warning("⚠️ Photo se items automatically detect nahi ho paaye. Neeche manual form use karo.")
                else:
                    st.warning("⚠️ Photo se koi text detect nahi hua. Saaf, sidhi aur achi roshni wali photo try karo.")
            except Exception:
                st.error("❌ Tesseract-OCR engine PC par nahi mila.")
                st.markdown("Install karo: https://github.com/UB-Mannheim/tesseract/wiki (Windows), phir app restart karo.")

        st.markdown("---")
        st.markdown("##### ➕ Or Add One Material Manually")
        with st.form("photo_add_form", clear_on_submit=True):
            p1,p2,p3 = st.columns(3)
            pnm  = p1.text_input("Material Name *")
            pcat = p2.selectbox("Category *", ['Select...']+CATS)
            punit = p3.selectbox("Unit *", ['Select...']+UNITS)
            p4,p5,p6 = st.columns(3)
            pstk = p4.number_input("Current Stock *", min_value=0, step=1, key="p_stk")
            pmn  = p5.number_input("Minimum Stock *", min_value=1, step=1, value=100, key="p_mn")
            pprc = p6.number_input("Unit Price ₹ *", min_value=0.0, step=0.5, key="p_prc")
            prcv = st.date_input("Received Date *", value=date.today(), max_value=date.today(), key="p_rcv")
            pbtn = st.form_submit_button("➕ Add to Inventory", use_container_width=True, type="primary")

        if pbtn:
            if not pnm or pcat == 'Select...' or punit == 'Select...':
                st.error("❌ Please fill all fields.")
            else:
                fresh = load_inventory()
                if (fresh['Item_Name'].str.lower() == pnm.lower()).any():
                    st.error(f"❌ **{pnm}** already exists. Go to Update Stock tab.")
                else:
                    new_row = pd.DataFrame([{'Item_Name':pnm,'Category':pcat,'Unit':punit,'Current_Stock':pstk,
                                             'Minimum_Stock':pmn,'Unit_Price':pprc,'Received_Date':pd.Timestamp(prcv)}])
                    fresh = pd.concat([fresh, new_row], ignore_index=True)
                    save_inventory(fresh)
                    st.success(f"✅ {pnm} added successfully!")
                    st.rerun()

st.markdown("---")
st.markdown("<p style='text-align:center;color:gray;font-size:12px'>Atlantic Design • Garment Production Inventory</p>",
            unsafe_allow_html=True)
