import streamlit as st
import requests
import time
import csv
import io
import datetime

# --- Configuration ---
st.set_page_config(page_title="Bulk Certificate Generator", page_icon="🎓", layout="centered")
API_BASE_URL = "http://127.0.0.1:8000"

# --- Injecting Custom CSS to match the design ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    
    @keyframes gradientBG {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Global Background: Animated Red-Blue gradient */
    .stApp {
        background: linear-gradient(-45deg, #ff4b4b, #2d3485, #ff4b4b, #2d3485);
        background-size: 400% 400%;
        animation: gradientBG 15s ease infinite;
        font-family: 'Poppins', sans-serif !important;
    }
    
    /* Hide the Streamlit top menu and footer for a cleaner app look */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* The main container acts as the phone screen */
    .block-container {
        background-color: #ffffff;
        padding: 2.5rem 1.5rem;
        border-radius: 35px; /* Phone-like rounded corners */
        box-shadow: 0px 20px 40px rgba(0, 0, 0, 0.4);
        max-width: 600px; /* Increased width */
        min-height: 800px;
        margin-top: 3rem;
        margin-bottom: 3rem;
    }

    /* Tabs styling */
    div[data-baseweb="tab-list"] {
        background-color: transparent; /* Removed the outer box */
        border-radius: 0;
        padding: 0;
        gap: 15px;
        margin-bottom: 25px;
        display: flex;
        justify-content: space-between;
    }
    div[data-baseweb="tab"] {
        border-radius: 15px;
        padding: 10px 20px;
        font-weight: 700;
        color: #ffffff !important;
        flex-grow: 1;
        justify-content: center;
        text-align: center;
        transition: all 0.2s;
    }
    /* Orange Button for Upload */
    div[data-baseweb="tab"]:nth-child(1) {
        background-color: #f39c12 !important;
    }
    /* Green Button for Activity */
    div[data-baseweb="tab"]:nth-child(2) {
        background-color: #27ae60 !important;
    }
    
    div[aria-selected="true"] {
        box-shadow: 0px 4px 10px rgba(0,0,0,0.2) !important;
        transform: translateY(-2px);
    }

    /* Teal indicator dot */
    .indicator-dot {
        height: 10px;
        width: 10px;
        background-color: #eab334; /* Gold accent */
        border-radius: 50%;
        display: inline-block;
        margin-bottom: 10px;
    }

    /* Typography */
    h1, h2, h3, p, label {
        color: #175e6b !important; /* Dark teal text */
        font-weight: 600;
    }
    .greeting {
        font-size: 18px;
        color: #175e6b;
        margin-bottom: 25px;
        font-weight: 700;
        text-align: center;
    }

    /* Progress bar styling */
    .stProgress > div > div > div > div {
        background-color: #175e6b;
        border-radius: 10px;
    }
    .stProgress {
        margin-bottom: 5px;
    }
    
    /* Upload / Submit Button */
    .stButton {
        display: flex;
        justify-content: center;
    }
    .stButton>button, .stButton>button p {
        background-color: #2e8b57; /* Green button */
        color: #ffffff !important; /* White text */
        font-weight: 700;
        border: none;
        padding: 0.75rem 3rem; /* Make it bigger */
        border-radius: 25px;
        width: auto;
        transition: all 0.3s;
        margin-top: 10px;
        margin-bottom: 0; 
        line-height: 1; /* Reset line height for perfect flex centering */
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.1rem; /* Slightly larger text */
    }
    .stButton>button:hover {
        background-color: #27774a;
        box-shadow: 0 4px 12px rgba(46, 139, 87, 0.4);
    }
    
    /* Inputs */
    .stTextInput>div>div>input {
        background-color: #f0f4f5;
        border-radius: 10px;
        border: none;
        color: #333;
    }
    .stDateInput>div>div>input {
        background-color: #f0f4f5;
        border-radius: 10px;
        border: none;
        color: #333;
    }

    /* Certificate Cards */
    .cert-card {
        background-color: #f0f4f5;
        border: none;
        border-radius: 12px;
        padding: 15px;
        margin-top: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="indicator-dot" style="display: block; margin: 0 auto 10px auto;"></div>', unsafe_allow_html=True)
st.markdown('<div class="greeting"><strong>Welcome Back</strong>!</div>', unsafe_allow_html=True)

# --- Tabs ---
tab1, tab2 = st.tabs(["Upload", "Activity"])

with tab1:
    st.write("Configure your certificate batch and upload the CSV data.")
    
    cert_title = st.text_input("Certificate Title", value="Certificate of Completion")
    course_name = st.text_input("Course Name", value="Python Backend Development")
    organization = st.text_input("Organization", value="ABC Technologies")
    issue_date = st.date_input("Issue Date", value=datetime.date.today())

    uploaded_file = st.file_uploader("Upload CSV (must contain 'name' and 'email')", type=["csv"])

    if st.button("Generate Certificates"):
        if not uploaded_file:
            st.error("Please upload a CSV file.")
        else:
            try:
                content = uploaded_file.getvalue().decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                
                fieldnames = [f.lower().strip() for f in (reader.fieldnames or [])]
                if "name" not in fieldnames or "email" not in fieldnames:
                    st.error("CSV must contain 'name' and 'email' columns.")
                    st.stop()
                    
                recipients = []
                for row in reader:
                    name_key = next((k for k in row.keys() if k.lower().strip() == "name"), None)
                    email_key = next((k for k in row.keys() if k.lower().strip() == "email"), None)
                    
                    name_val = row[name_key].strip() if row.get(name_key) else ""
                    email_val = row[email_key].strip() if row.get(email_key) else ""
                    
                    if name_val and email_val:
                        recipients.append({"name": name_val, "email": email_val})
                        
                if not recipients:
                    st.error("No valid recipients found in the CSV.")
                    st.stop()
                    
            except Exception as e:
                st.error(f"Error parsing CSV: {str(e)}")
                st.stop()

            payload = {
                "certificate_title": cert_title.strip(),
                "course_name": course_name.strip(),
                "organization": organization.strip(),
                "issue_date": issue_date.isoformat(),
                "recipients": recipients
            }

            with st.spinner("Submitting job..."):
                try:
                    response = requests.post(f"{API_BASE_URL}/api/jobs/", json=payload)
                    response.raise_for_status()
                    job_data = response.json()
                    st.session_state['current_job_id'] = job_data["id"]
                except Exception as e:
                    error_msg = getattr(e, "response", None)
                    st.error(f"Failed to create job: {str(e)}")
                    st.stop()

            st.success("Job submitted! Switch to Activity tab to view progress.")

with tab2:
    if 'current_job_id' not in st.session_state:
        st.info("No active jobs. Go to Upload to generate certificates.")
    else:
        job_id = st.session_state['current_job_id']
        st.write(f"**Job ID:** `{job_id}`")
        
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        # Check status once per tab render or loop if pending
        try:
            status_res = requests.get(f"{API_BASE_URL}/api/jobs/{job_id}")
            if status_res.status_code == 200:
                status_info = status_res.json()
                
                job_status = status_info.get("status")
                completed = status_info.get("completed_count", 0)
                failed = status_info.get("failed_count", 0)
                total = status_info.get("total_count", 0)
                
                prog = 0.0
                if total > 0:
                    prog = (completed + failed) / total
                progress_bar.progress(prog)
                status_text.caption(f"Storage {completed+failed}/{total} | Status: **{job_status}**")
                
                if job_status in ["COMPLETED", "FAILED"]:
                    st.success("Generation Complete!")
                    
                    with st.spinner("Fetching certificates..."):
                        certs_res = requests.get(f"{API_BASE_URL}/api/jobs/{job_id}/certificates")
                        if certs_res.status_code == 200:
                            certs_data = certs_res.json()
                            for cert in certs_data.get("certificates", []):
                                d_url = cert.get("download_url")
                                dl_link = f"{API_BASE_URL}{d_url}" if d_url else "#"
                                status_ico = "✅" if cert.get("status") == "COMPLETED" else "❌"
                                
                                st.markdown(
                                    f'''
                                    <div class="cert-card">
                                        <div>
                                            <strong>{cert.get("recipient_name")}</strong><br>
                                            <span style="color:#888; font-size: 12px;">{cert.get("recipient_email")}</span>
                                        </div>
                                        <div>
                                            {status_ico}
                                            <a href="{dl_link}" target="_blank" style="background:#eee; padding:5px 10px; border-radius:4px; text-decoration:none; color:#333; font-size:12px; margin-left:10px;">Download</a>
                                        </div>
                                    </div>
                                    ''', unsafe_allow_html=True
                                )
        except Exception as e:
            st.error(f"Error checking status: {str(e)}")
