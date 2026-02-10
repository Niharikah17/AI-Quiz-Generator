import streamlit as st
import google.generativeai as genai
import json
import re
import pandas as pd
import time
import datetime
import os
import numpy as np
from fpdf import FPDF
from PIL import Image
from io import BytesIO

# --- CONFIGURATION ---
API_KEY = "  # Replace with your Gemini API Key "
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-3-flash-preview')

USER_DB = "users.json"
HISTORY_DB = "quiz_history.csv"

st.set_page_config(page_title="COGNIFY AI", layout="wide")

def apply_styles():
    st.markdown("""
        <style>
        .stApp { background-color: #000000; color: #00FFFF; }
        h1, h2, h3, p, span, label, .stMetricValue { color: #00FFFF !important; font-weight: bold !important; }
        .welcome-text { font-size: 55px !important; text-align: center; margin-top: 30px; text-shadow: 0 0 15px #00FFFF; }
        .stButton>button {
            background-color: #000000; color: #00FFFF !important;
            border: 2px solid #00FFFF !important; border-radius: 10px;
            width: 100%; height: 50px; font-weight: bold; transition: 0.4s;
        }
        .stButton>button:hover { background-color: #00FFFF; color: #000000 !important; box-shadow: 0 0 25px #00FFFF; }
        [data-testid="stSidebar"] { background-color: #080808; border-right: 1px solid #00FFFF; }
        </style>
    """, unsafe_allow_html=True)

apply_styles()

# --- HELPERS ---
def load_users():
    if os.path.exists(USER_DB):
        with open(USER_DB, "r") as f: return json.load(f)
    return {}

def save_users(users):
    with open(USER_DB, "w") as f: json.dump(users, f)

# --- SESSION STATE ---
if 'page' not in st.session_state:
    st.session_state.update({
        'page': 'auth', 'user_name': '', 'profile_pic': None,
        'quiz_data': None, 'q_idx': 0, 'score': 0, 'submitted': False,
        'start_time': None, 'time_limit': 60, 'topic': '', 'test_type': '',
        'ocr_text': '', 'last_review': '', 'sidebar_mode': 'Dashboard & History'
    })

# --- GLOBAL SIDEBAR ---
if st.session_state.user_name and st.session_state.page != 'quiz':
    with st.sidebar:
        st.title("User Menu")
        st.write(f"Logged in: **{st.session_state.user_name}**")
        st.divider()
        st.session_state.sidebar_mode = st.radio("Portal Options", ["Dashboard & History", "Edit Profile", "Logout"])
        
        if st.session_state.sidebar_mode == "Dashboard & History":
            st.subheader("Your Test History")
            try:
                df = pd.read_csv(HISTORY_DB)
                user_df = df[df['User'] == st.session_state.user_name]
                if not user_df.empty:
                    st.dataframe(user_df[['Date', 'Topic', 'Score', 'Time(s)']], hide_index=True)
                else:
                    st.info("No tests taken yet.")
            except: st.info("No history database found.")
            
        elif st.session_state.sidebar_mode == "Edit Profile":
            st.subheader("Profile Settings")
            new_name = st.text_input("Change Display Name", value=st.session_state.user_name)
            if st.button("Update Profile"):
                st.session_state.user_name = new_name
                st.success("Profile Updated!")
                
        elif st.session_state.sidebar_mode == "Logout":
            st.session_state.clear()
            st.rerun()

# --- 1. AUTH ---
if st.session_state.page == 'auth':
    st.title("💠 COGNIFY AI LOGIN")
    t1, t2 = st.tabs(["LOGIN", "CREATE ACCOUNT"])
    with t1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("LOGIN"):
            users = load_users()
            if u in users and users[u].get('password') == p:
                st.session_state.user_name, st.session_state.page = u, 'menu'
                st.rerun()
    with t2:
        nu, np = st.text_input("New User"), st.text_input("New Pass", type="password")
        if st.button("REGISTER"):
            users = load_users()
            users[nu] = {"password": np}
            save_users(users); st.success("Registration successful!")

# --- 2. MENU ---
elif st.session_state.page == 'menu':
    st.markdown(f'<div class="welcome-text">Welcome {st.session_state.user_name} !!</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("🚀 START NEW SESSION"):
            st.session_state.page = 'type_selection'; st.rerun()

# --- 3. TYPE SELECTION ---
elif st.session_state.page == 'type_selection':
    if st.button("🔙 Back"): st.session_state.page = 'menu'; st.rerun()
    st.title("Choose Test Type")
    col1, col2 = st.columns(2)
    if col1.button("📝 MCQ Questions (Timed)"):
        st.session_state.test_type, st.session_state.page = "MCQ", 'setup'; st.rerun()
    if col2.button("✍️ Descriptive Questions"):
        st.session_state.test_type, st.session_state.page = "Descriptive", 'setup'; st.rerun()

# --- 4. SETUP ---
elif st.session_state.page == 'setup':
    if st.button("🔙 Back"): st.session_state.page = 'type_selection'; st.rerun()
    st.title(f"Setup {st.session_state.test_type} Test")
    st.session_state.topic = st.text_input("Enter Topic (e.g., Photosynthesis, Python Basics):")
    if st.session_state.test_type == "MCQ":
        st.session_state.time_limit = st.selectbox("Select Duration:", [1, 2, 5]) * 60
    
    if st.button("GENERATE TEST"):
        with st.spinner("AI is crafting your test..."):
            if st.session_state.test_type == "MCQ":
                p = f"Create 3 MCQ about {st.session_state.topic} in JSON: [{{'question':'', 'options':[], 'answer':'', 'explanation':''}}]"
            else:
                p = f"Create 1 complex descriptive question about {st.session_state.topic} in JSON: [{{'question':'', 'answer_key':''}}]"
            
            res = model.generate_content(p)
            st.session_state.quiz_data = json.loads(re.sub(r"```json|```", "", res.text).strip())
            st.session_state.start_time, st.session_state.q_idx, st.session_state.score, st.session_state.page = time.time(), 0, 0, 'quiz'
            st.rerun()

# --- 5. QUIZ PAGE ---
elif st.session_state.page == 'quiz':
    c_exit1, c_exit2 = st.columns([0.9, 0.1])
    if c_exit2.button("🔴 EXIT"):
        st.session_state.page = 'menu'; st.rerun()

    if st.session_state.test_type == "MCQ":
        elapsed = time.time() - st.session_state.start_time
        rem = max(0, int(st.session_state.time_limit - elapsed))
        st.metric("⏳ TIME", f"{rem//60:02d}:{rem%60:02d}")
        if rem <= 0: st.session_state.page = 'results'; st.rerun()

    q = st.session_state.quiz_data[st.session_state.q_idx]
    st.subheader(f"Q{st.session_state.q_idx + 1}: {q['question']}")

    # --- PATH A: MCQ ---
    if st.session_state.test_type == "MCQ":
        # Ensure no option is pre-selected by using None index
        ans = st.radio("Choose the correct option:", q['options'], index=None, key=f"q_{st.session_state.q_idx}")
        
        if not st.session_state.submitted:
            if st.button("SUBMIT ANSWER") and ans is not None:
                st.session_state.submitted = True
                if ans == q['answer']:
                    st.session_state.score += 1
                    st.success("✅ Correct!")
                else:
                    st.error(f"❌ Wrong! The correct answer was: {q['answer']}")
                st.info(f"**Explanation:** {q['explanation']}")
                st.rerun()
        else:
            # Re-display feedback if already submitted
            if ans == q['answer']: st.success("✅ Correct!")
            else: st.error(f"❌ Wrong! Answer: {q['answer']}")
            st.info(f"**Explanation:** {q['explanation']}")
            
            if st.button("NEXT QUESTION"):
                if st.session_state.q_idx < 2:
                    st.session_state.q_idx += 1
                    st.session_state.submitted = False
                else:
                    st.session_state.end_time = time.time()
                    st.session_state.page = 'results'
                st.rerun()
        
        if not st.session_state.submitted:
            time.sleep(1); st.rerun()

    # --- PATH B: DESCRIPTIVE ---
    else:
        h_file = st.file_uploader("Upload Image of Handwritten Answer", type=['jpg','png','jpeg'])
        if h_file:
            img = Image.open(h_file)
            st.image(img, width=450)
            if st.button("Scan & Evaluate"):
                with st.spinner("Vision AI analyzing..."):
                    vision_prompt = f"Question: {q['question']}. Read the handwriting. Transcribe it. Rate it 1-5. Return JSON: {{'transcription':'', 'rating':int, 'reason':'', 'tips':''}}"
                    response = model.generate_content([vision_prompt, img])
                    eval_data = json.loads(re.sub(r"```json|```", "", response.text).strip())
                    st.session_state.ocr_text = eval_data['transcription']
                    st.session_state.score = eval_data['rating']
                    st.session_state.last_review = f"**Reason:** {eval_data['reason']}\n\n**Improvement:** {eval_data['tips']}"
                    st.session_state.end_time = time.time(); st.session_state.page = 'results'; st.rerun()

# --- 6. RESULTS PAGE ---
elif st.session_state.page == 'results':
    st.title("📊 Performance Review")
    dur = int(st.session_state.end_time - st.session_state.start_time)
    
    if st.session_state.test_type == "MCQ":
        st.metric("Score", f"{st.session_state.score}/3")
        if not st.session_state.last_review:
            with st.spinner("AI Generating Strategy..."):
                p = f"The student scored {st.session_state.score}/3 in {st.session_state.topic}. Provide a strategic review and a 3-step study plan to improve."
                st.session_state.last_review = model.generate_content(p).text
    else:
        st.metric("Rating", f"{st.session_state.score}/5")
        st.write("**Transcribed Answer:**", st.session_state.ocr_text)

    st.subheader("🤖 AI Strategic Analysis")
    st.write(st.session_state.last_review)

    if st.button("💾 FINALIZE & SAVE TO DASHBOARD"):
        new_data = pd.DataFrame({"Date": [datetime.datetime.now().strftime("%Y-%m-%d")], "User": [st.session_state.user_name], "Topic": [st.session_state.topic], "Score": [st.session_state.score], "Time(s)": [dur]})
        if os.path.exists(HISTORY_DB): pd.concat([pd.read_csv(HISTORY_DB), new_data]).to_csv(HISTORY_DB, index=False)
        else: new_data.to_csv(HISTORY_DB, index=False)
        
        # Reset and Redirect
        st.session_state.sidebar_mode = "Dashboard & History"
        st.session_state.page = 'menu'
        st.session_state.update({'q_idx': 0, 'score': 0, 'submitted': False, 'last_review': ''})
        st.rerun()
