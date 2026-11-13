import os
import socket
import time
from pathlib import Path
from io import BytesIO
from urllib.parse import urlencode

import pymupdf
import qrcode
import streamlit as st
import streamlit.components.v1 as components

from rag import (
    authenticate_patient,
    create_access_code,
    delete_document,
    generate_answer,
    get_patient_timeline,
    get_patient_records,
    list_patient_documents,
    register_patient,
    revoke_access_code,
    search_records,
    store_document,
    verify_access_code,
)

st.set_page_config(page_title="One Patient, Many Records", page_icon="🏥", layout="wide", initial_sidebar_state="collapsed")

def default_app_address():
    configured_url = os.environ.get("APP_BASE_URL", "").strip()
    if configured_url:
        return configured_url.rstrip("/")
    port = st.get_option("server.port") or 8501
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_probe:
            route_probe.connect(("8.8.8.8", 80))
            local_ip = route_probe.getsockname()[0]
        if local_ip and not local_ip.startswith("127."):
            return f"http://{local_ip}:{port}"
    except OSError:
        pass
    return f"http://localhost:{port}"

def render_doctor_portal(patient_id):
    st.markdown('<div class="doctor-banner"><span>DOCTOR PORTAL</span><h1>Shared patient records</h1><p>Read-only medical information shared by the patient.</p></div>', unsafe_allow_html=True)
    patient_metric, access_metric = st.columns(2)
    patient_metric.metric("Patient ID", patient_id)
    access_metric.metric("Access level", "Read only")
    st.caption("Temporary access · This page is separate from the patient workspace.")
    records_tab, timeline_tab, search_tab = st.tabs(["Shared records", "Timeline", "Search records"])
    records = get_patient_records(patient_id)
    with records_tab:
        st.subheader("Shared records")
        if records:
            for record in records:
                with st.expander(record["document_id"]):
                    st.write(record["text"])
        else:
            st.info("No records have been added to this patient workspace.")
    with timeline_tab:
        st.subheader("Patient timeline")
        timeline = get_patient_timeline(patient_id)
        if timeline:
            for event_date, title, description, source in reversed(timeline):
                with st.container(border=True):
                    heading = title if event_date == "Date not recorded" else f"{event_date} · {title}"
                    st.markdown(f"**{heading}**")
                    st.write(description)
                    st.caption(f"Source: {source}")
        else:
            st.info("No timeline events were found in the shared records.")
    with search_tab:
        st.subheader("Search shared records")
        question = st.text_input("Question", placeholder="Ask about a medication, allergy, or visit", key=f"doctor_question_{patient_id}")
        if st.button("Search shared records", type="primary", key=f"doctor_search_{patient_id}"):
            if question.strip():
                st.info(generate_answer(question, patient_id))
                for match in search_records(question, patient_id)[:3]:
                    with st.expander(match["document_id"]):
                        st.write(match["text"])
            else:
                st.warning("Enter a question first.")
    st.divider()
    if st.button("Close doctor view", key="close_doctor_view"):
        st.session_state.pop("doctor_portal_patient_id", None)
        st.session_state.pop("doctor_portal_access_code", None)
        st.rerun()
    st.caption("Access expires automatically after 10 minutes or when the patient revokes the link.")
st.markdown("""
<style>
:root { color-scheme: light; }
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: #ffffff; color: #17324d; }
.block-container { max-width: 1500px; padding: 1.2rem 2.4rem 3rem; }
[data-testid="stSidebar"] { background: #f7faf9; border-right: 1px solid #e6eeeb; }
[data-testid="stSidebar"] > div:first-child { padding-top: 1.5rem; }
[data-testid="stSidebar"] h3 { color: #173d4a; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #6c7f88; }
.hero { display: flex; align-items: center; justify-content: space-between; gap: 2rem; min-height: 190px; padding: 1.7rem 2rem; margin: 0 0 1.25rem; overflow: hidden; border: 1px solid #e3efeb; border-radius: 22px; background: linear-gradient(112deg, #f1faf7 0%, #fbfefd 56%, #f5f8ff 100%); box-shadow: 0 8px 26px rgba(22, 61, 74, .045); }
.auth-banner { margin:.5rem 0 1.3rem; padding:1.6rem 1.8rem; border:1px solid #dcebe7; border-radius:20px; background:linear-gradient(115deg,#eef8f5,#f5f8ff); }
.auth-banner h1 { margin:.35rem 0; color:#173d4a; font-size:clamp(2rem,3vw,2.7rem); }
.auth-banner p { margin:0; color:#405966; font-size:1.05rem; }
.doctor-banner { margin: .5rem 0 1.4rem; padding: 1.8rem 2rem; border: 1px solid #dcebe7; border-radius: 20px; background: linear-gradient(115deg,#eef8f5,#f5f8ff); }
.doctor-banner span { color: #117c72; font-size: .75rem; font-weight: 750; letter-spacing: .14em; }
.doctor-banner h1 { margin: .45rem 0; color: #173d4a; font-size: clamp(2rem,3.2vw,2.8rem); }
.doctor-banner p { margin: 0; color: #405966; font-size: 1.05rem; }
.hero-copy { max-width: 700px; }
.eyebrow { display: inline-block; margin-bottom: .65rem; color: #147c73; font-size: .72rem; font-weight: 750; letter-spacing: .13em; }
.hero h1 { margin: 0 0 .55rem; color: #173d4a; font-size: clamp(2rem, 3.5vw, 3rem); line-height: 1.12; letter-spacing: -.035em; }
.hero p { max-width: 700px; margin: 0; color: #5c707b; font-size: 1.1rem; line-height: 1.6; }
.care-art { position: relative; display: flex; align-items: center; justify-content: center; min-width: 300px; height: 130px; }
.care-person { z-index: 1; display: flex; flex-direction: column; align-items: center; gap: .45rem; width: 92px; color: #48616b; font-size: .76rem; font-weight: 650; }
.care-avatar { display: grid; place-items: center; width: 68px; height: 68px; border: 4px solid #fff; border-radius: 50%; background: #dff3ed; box-shadow: 0 5px 18px rgba(27, 91, 87, .12); font-size: 2rem; }
.care-person.doctor .care-avatar { background: #e8edff; }
.care-link { width: 76px; height: 2px; margin: -1.15rem -.3rem 0; background: #9acfc4; }
.care-link:after { content: "✦"; position: relative; top: -13px; left: 31px; color: #19877c; font-size: 1.1rem; }
.care-badge { position: absolute; top: 0; right: 0; display: grid; place-items: center; width: 30px; height: 30px; border: 1px solid #d9e8ff; border-radius: 10px; background: #fff; color: #3870c4; font-weight: 800; }
[data-testid="stMetric"] { min-height: 108px; padding: 1.2rem 1.35rem; border: 1px solid #e8efee; border-radius: 15px; background: #fff; box-shadow: 0 4px 15px rgba(20, 55, 70, .035); }
[data-testid="stMetricLabel"] { color: #687e87; font-size: .82rem; }
[data-testid="stMetricValue"] { color: #173d4a; font-weight: 720; }
[data-baseweb="tab-list"] { gap: .35rem; border-bottom: 1px solid #e8efee; overflow-x: auto; }
button[data-baseweb="tab"] { flex: 0 0 auto; min-width: max-content; height: 3.6rem; padding: 0 1.15rem; color: #354e5b; font-size: 1.05rem; font-weight: 720; white-space: nowrap; }
button[data-baseweb="tab"][aria-selected="true"] { color: #075f58; }
[data-baseweb="tab-highlight"] { background-color: #14867b; }
.stButton > button[kind="primary"], .stButton > button { border-radius: 10px; transition: all .15s ease; }
.stButton > button[kind="primary"] { border: 1px solid #117c72; background: #117c72; color: #fff; }
.stButton > button[kind="primary"]:hover { border-color: #0d655e; background: #0d655e; }
.stButton > button:not([kind="primary"]) { border-color: #d9e5e3; color: #31515c; background: #fff; }
.stButton > button:not([kind="primary"]):hover { border-color: #83bdb3; color: #117c72; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea { border-color: #dce7e5; border-radius: 9px; }
[data-testid="stFileUploader"] section { border: 1px dashed #9bc9c0; border-radius: 13px; background: #fbfefd; }
[data-testid="stAlert"] { border-radius: 11px; }
[data-testid="stExpander"] { border-color: #e4ecea; border-radius: 12px; background: #fff; }
[data-testid="stCaptionContainer"] { color: #6b7e87; }
h2, h3, h4 { color: #1c4250; letter-spacing: -.015em; }
.workspace-label { margin: 0 0 .25rem; color: #173d4a; font-size: .95rem; font-weight: 740; }
.workspace-note { margin-top: 1.7rem; padding: .8rem 1rem; border: 1px solid #e3efeb; border-radius: 12px; background: #f7fbfa; color: #455f6a; font-size: .95rem; }
@media (max-width: 760px) { .block-container { padding: 1rem 1rem 2rem; } .workspace-note { display: none; margin-top: 0; } }
.small-note { color: #536a75; font-size: .9rem; }
/* Stronger, consistent text contrast on the white clinical theme. */
body, [data-testid="stAppViewContainer"], [data-testid="stMain"] { color: #233f4e; }
[data-testid="stMarkdownContainer"] p { color: #405966; }
.hero p { color: #405966; }
[data-testid="stCaptionContainer"], .small-note { color: #536a75 !important; opacity: 1; }
[data-testid="stMetricLabel"] { color: #4d6470 !important; font-size: .9rem; font-weight: 600; }
[data-testid="stMetricValue"] { color: #173d4a !important; }
[data-testid="stWidgetLabel"] p, label, [data-testid="stFileUploader"] { color: #304c59 !important; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-baseweb="select"] * { color: #233f4e !important; }
[data-testid="stTextInput"] input::placeholder, [data-testid="stTextArea"] textarea::placeholder { color: #657b86 !important; opacity: 1; }
button[data-baseweb="tab"] { color: #294653 !important; font-size: 1.05rem; font-weight: 740; }
button[data-baseweb="tab"][aria-selected="true"] { color: #075f58 !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p { color: #294653 !important; }
[data-testid="stAlert"] { color: #294653; }
/* Explicit light surfaces prevent dark Streamlit themes from hiding form text. */
[data-baseweb="input"] > div, [data-baseweb="textarea"] > div { background: #ffffff !important; border: 1px solid #bdcdd4 !important; box-shadow: none !important; }
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea { background: transparent !important; color: #173d4a !important; -webkit-text-fill-color: #173d4a !important; caret-color: #117c72; }
[data-baseweb="input"] input::placeholder, [data-baseweb="textarea"] textarea::placeholder { color: #526a75 !important; -webkit-text-fill-color: #526a75 !important; opacity: 1 !important; }
[data-testid="stSidebar"] [data-baseweb="input"] > div { background: #ffffff !important; }
.stButton > button { color: #294653 !important; }
.stButton > button[data-testid="baseButton-primary"], .stButton > button[kind="primary"] { background: #117c72 !important; border-color: #117c72 !important; color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }
.stButton > button[data-testid="baseButton-primary"] *, .stButton > button[kind="primary"] * { color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; }
.stButton > button[data-testid="baseButton-primary"]:hover, .stButton > button[kind="primary"]:hover { background: #0d655e !important; border-color: #0d655e !important; }
input[type="checkbox"] { accent-color: #117c72; }
/* Keep the PDF drop zone and record selector readable in the upload flow. */
[data-testid="stFileUploader"] section { background: #f7fbfa !important; border: 1px dashed #83bdb3 !important; opacity: 1 !important; }
[data-testid="stFileUploader"] section *, [data-testid="stFileUploader"] [data-testid="stMarkdownContainer"] *, [data-testid="stFileUploader"] small { color: #294653 !important; -webkit-text-fill-color: #294653 !important; opacity: 1 !important; }
[data-testid="stFileUploader"] section svg { color: #58717d !important; fill: #58717d !important; }
[data-testid="stFileUploader"] button { background: #e8f4f1 !important; border: 1px solid #a6ccc3 !important; color: #145b54 !important; -webkit-text-fill-color: #145b54 !important; }
[data-testid="stFileUploader"] button * { color: #145b54 !important; -webkit-text-fill-color: #145b54 !important; }
[data-baseweb="select"] > div { background: #ffffff !important; border-color: #bdcdd4 !important; }
[data-baseweb="select"] *, [role="listbox"] *, [role="option"] { color: #233f4e !important; -webkit-text-fill-color: #233f4e !important; }
[data-baseweb="select"] input { background: transparent !important; color: #173d4a !important; -webkit-text-fill-color: #173d4a !important; }
[role="listbox"] { background: #ffffff !important; border: 1px solid #bdcdd4 !important; }
[role="option"] { background: #ffffff !important; }
[role="option"]:hover { background: #eaf5f2 !important; }
@media (max-width: 760px) { .block-container { padding: 1rem 1rem 2rem; } .hero { min-height: unset; padding: 1.4rem; } .care-art { display: none; } }
</style>
""", unsafe_allow_html=True)

incoming_access_code = st.query_params.get("access_code", "")
incoming_patient_id = st.query_params.get("patient_id", "").strip()
if incoming_access_code:
    if incoming_patient_id and verify_access_code(incoming_patient_id, incoming_access_code):
        st.session_state["doctor_portal_patient_id"] = incoming_patient_id
        st.session_state["doctor_portal_access_code"] = incoming_access_code
        st.query_params.clear()
        st.rerun()
    st.markdown('<div class="doctor-banner"><span>DOCTOR PORTAL</span><h1>Access unavailable</h1><p>This sharing link is invalid, revoked, or expired.</p></div>', unsafe_allow_html=True)
    st.info("Ask the patient to create a new temporary QR link.")
    st.stop()

doctor_patient_id = st.session_state.get("doctor_portal_patient_id")
doctor_access_code = st.session_state.get("doctor_portal_access_code")
if doctor_patient_id:
    if verify_access_code(doctor_patient_id, doctor_access_code):
        render_doctor_portal(doctor_patient_id)
    else:
        st.session_state.pop("doctor_portal_patient_id", None)
        st.session_state.pop("doctor_portal_access_code", None)
        st.markdown('<div class="doctor-banner"><span>DOCTOR PORTAL</span><h1>Access expired</h1><p>The patient sharing link is no longer active.</p></div>', unsafe_allow_html=True)
        st.info("Ask the patient to create a new temporary QR link.")
    st.stop()

patient_account = st.session_state.get("patient_account")
if not patient_account:
    st.markdown('<div class="auth-banner"><span class="eyebrow">PATIENT ACCESS</span><h1>Sign in to your health records</h1><p>Your account keeps your records private and connected to your patient profile.</p></div>', unsafe_allow_html=True)
    login_tab, register_tab = st.tabs(["Sign in", "Create patient account"])
    with login_tab:
        with st.form("patient_sign_in_form"):
            login_email = st.text_input("Email address", autocomplete="email")
            login_password = st.text_input("Password", type="password", autocomplete="current-password")
            sign_in = st.form_submit_button("Sign in", type="primary")
        if sign_in:
            account = authenticate_patient(login_email, login_password)
            if account:
                st.session_state["patient_account"] = account
                st.session_state["patient_auth_method"] = "password"
                st.rerun()
            st.error("Email or password is incorrect.")
    with register_tab:
        with st.form("patient_register_form"):
            register_email = st.text_input("Email address", autocomplete="email", key="register_email")
            register_password = st.text_input("Create password", type="password", autocomplete="new-password")
            confirm_password = st.text_input("Confirm password", type="password", autocomplete="new-password")
            create_account = st.form_submit_button("Create account", type="primary")
        if create_account:
            if register_password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    st.session_state["patient_account"] = register_patient(register_email, register_password)
                    st.session_state["patient_auth_method"] = "password"
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    st.caption("Passwords are stored as salted hashes. Email verification and password reset are not configured in this prototype.")
    st.stop()
patient_id = patient_account["patient_id"]
with st.container():
    patient_col, workspace_note_col, signout_col = st.columns([1.5, 3.1, .7], vertical_alignment="center")
    with patient_col:
        st.markdown('<div class="workspace-label">Patient profile</div>', unsafe_allow_html=True)
        st.markdown(f"**{patient_account['email']}**")
    with workspace_note_col:
        st.markdown('<div class="workspace-note">Private workspace · your records stay grouped together</div>', unsafe_allow_html=True)
    with signout_col:
        if st.button("Sign out", key="patient_sign_out"):
            st.session_state.pop("patient_account", None)
            st.rerun()
st.markdown('<div class="hero"><div class="hero-copy"><span class="eyebrow">CONNECTED CARE RECORDS</span><h1>One patient. A clearer health story.</h1><p>Bring medical documents together and help patients and care teams see the details that matter.</p></div><div class="care-art"><div class="care-person patient"><span class="care-avatar">🙂</span><span>Patient</span></div><div class="care-link"></div><div class="care-person doctor"><span class="care-avatar">🩺</span><span>Care team</span></div><span class="care-badge">+</span></div></div>', unsafe_allow_html=True)
records = list_patient_documents(patient_id)
col1, col2, col3 = st.columns(3)
col1.metric("Records", len(records))
col2.metric("Timeline events", len(get_patient_timeline(patient_id)))
col3.metric("Workspace", patient_id)
st.caption("Answers quote information found in uploaded records. They are not a diagnosis or medical advice.")
upload_tab, search_tab, timeline_tab, access_tab, manage_tab = st.tabs([
    "Add records", "Ask across records", "Timeline", "Doctor access", "Manage records"
])

with upload_tab:
    st.subheader("Add a medical record")
    uploaded_files = st.file_uploader("Choose one or more text-based PDF files", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        selected = st.selectbox("Record to preview", options=range(len(uploaded_files)), format_func=lambda i: uploaded_files[i].name)
        current_file = uploaded_files[selected]
        try:
            with pymupdf.open(stream=current_file.getvalue(), filetype="pdf") as pdf:
                extracted_text = "\n".join(page.get_text("text") for page in pdf).strip()
            if extracted_text:
                st.success(f"Text extracted from {current_file.name}")
                st.text_area("Extracted text preview", extracted_text, height=220, disabled=True)
                if st.button("Save selected record", type="primary"):
                    count = store_document(extracted_text, patient_id, current_file.name)
                    if count:
                        st.success(f"Saved {current_file.name} as {count} searchable sections.")
                        st.rerun()
                    else:
                        st.error("This file did not contain text to save.")
            else:
                st.warning("No selectable text was found. This PDF may be scanned and need OCR before it can be searched.")
        except Exception as exc:
            st.error(f"Could not read this PDF: {exc}")
    else:
        st.info("PDFs are processed in memory. Re-uploading a filename replaces its saved version.")

with search_tab:
    st.subheader("Ask a question about this patient's records")
    st.caption("Voice recognition may be processed by your browser provider. The recognized text is searched locally.")
    allow_voice = st.checkbox("I agree to use browser speech recognition for this search", key="allow_voice_search")
    if allow_voice:
        mic_column, question_column = st.columns([0.55, 8], vertical_alignment="bottom")
        with mic_column:
            voice_html = (Path(__file__).resolve().parent / "voice_search_component" / "index.html").read_text(encoding="utf-8")
            components.html(voice_html, width=60, height=62, scrolling=False)
        with question_column:
            question = st.text_input(
                "Question",
                placeholder="What allergy is recorded? What happened in 2018?",
                key="patient_search_question",
            )
    else:
        question = st.text_input(
            "Question",
            placeholder="What allergy is recorded? What happened in 2018?",
            key="patient_search_question",
        )
    if st.button("Search records", type="primary", key="search_records"):
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            with st.spinner("Searching the patient's saved records…"):
                matches = search_records(question, patient_id)
                answer = generate_answer(question, patient_id)
            st.markdown("#### Record lookup")
            st.info(answer)
            if matches:
                st.markdown("#### Sources")
                for item in matches[:3]:
                    with st.expander(item["document_id"]):
                        st.write(item["text"])
    st.caption("Typed search uses local text matching and extractive retrieval; it does not send records to an AI service.")

with timeline_tab:
    st.subheader("Patient timeline")
    timeline = get_patient_timeline(patient_id)
    if not timeline:
        st.info("Timeline events will appear when dates or diagnoses are found in saved records.")
    else:
        for event_date, title, description, source in reversed(timeline):
            with st.container(border=True):
                heading = title if event_date == "Date not recorded" else f"{event_date} · {title}"
                st.markdown(f"**{heading}**")
                st.write(description)
                st.caption(f"Source: {source}")

with access_tab:
    st.subheader("Temporary doctor access")
    st.write("Create a private QR link for a doctor to open this patient's records for 10 minutes.")
    share_base_url = st.text_input("App address for the doctor device", value=default_app_address(), help="Uses this computer local network address by default. The doctor's phone must be on the same Wi-Fi. For off-site access, set APP_BASE_URL to your deployed app address.")
    consent = st.checkbox("I authorize temporary access to this patient's records", key=f"consent_{patient_id}")
    if st.button("Generate access code", type="primary"):
        if not consent:
            st.warning("Authorize sharing before generating a code.")
        else:
            code = create_access_code(patient_id)
            st.session_state[f"access_code_{patient_id}"] = code
            st.session_state[f"access_expiry_{patient_id}"] = time.time() + 600
            st.success("Code created. Share it directly with the intended doctor.")
    code_key, expiry_key = f"access_code_{patient_id}", f"access_expiry_{patient_id}"
    if st.session_state.get(code_key) and time.time() < st.session_state.get(expiry_key, 0):
        st.code(st.session_state[code_key])
        access_url = share_base_url.rstrip("/") + "/?" + urlencode({"patient_id": patient_id, "access_code": st.session_state[code_key]})
        qr_image = qrcode.make(access_url)
        qr_buffer = BytesIO()
        qr_image.save(qr_buffer, format="PNG")
        st.image(qr_buffer.getvalue(), width=210, caption="Scan to open the temporary doctor access page")
        st.caption("Anyone with this private link can access records until the code expires. Revoke access at any time.")
    elif st.session_state.get(code_key):
        st.info("The displayed access code has expired.")
    if st.button("Revoke current access"):
        revoke_access_code(patient_id)
        st.session_state.pop(code_key, None)
        st.session_state.pop(expiry_key, None)
        st.success("Doctor access revoked.")

with manage_tab:
    st.subheader("Saved records")
    records = list_patient_documents(patient_id)
    if not records:
        st.info("No records saved for this patient yet.")
    else:
        for index, name in enumerate(records):
            left, right = st.columns([5, 1])
            left.write(f"📄 {name}")
            if right.button("Remove", key=f"remove_{patient_id}_{index}_{name}"):
                delete_document(patient_id, name)
                st.success(f"Removed {name}")
                st.rerun()

st.divider()
st.markdown('<p class="small-note">One Patient, Many Records · Demonstration prototype. Use synthetic records only; this build is not a certified medical records system.</p>', unsafe_allow_html=True)
