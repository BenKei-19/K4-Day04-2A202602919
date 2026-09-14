import json
from pathlib import Path
from datetime import datetime

import streamlit as st

# Must be the first Streamlit command
st.set_page_config(page_title="IT Helpdesk Agent Pro Max", page_icon="✨", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');

html, body, [class*="css"]  {
    font-family: 'Outfit', sans-serif;
}

/* Main background */
.stApp {
    background: radial-gradient(circle at top left, #1e1b4b 0%, #020617 100%);
    color: #e2e8f0;
}

/* Glassmorphism sidebar */
[data-testid="stSidebar"] {
    background: rgba(15, 23, 42, 0.6) !important;
    backdrop-filter: blur(12px) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.05);
}

/* Gradient text for main title */
h1 {
    background: -webkit-linear-gradient(45deg, #00f2fe, #4facfe, #00f2fe);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 600;
}

/* Custom Chat bubbles */
[data-testid="chatAvatarIcon-user"] {
    background-color: #6366f1 !important;
}
[data-testid="chatAvatarIcon-assistant"] {
    background-color: #14b8a6 !important;
}

.stChatMessage {
    background: rgba(30, 41, 59, 0.4);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 16px;
    padding: 10px 15px;
    margin-bottom: 15px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.stChatMessage:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.1);
}

/* Primary Button style */
button[kind="primary"] {
    background: linear-gradient(90deg, #6366f1, #14b8a6) !important;
    border: none !important;
    color: white !important;
    border-radius: 20px !important;
    font-weight: 600 !important;
    transition: all 0.3s ease !important;
}
button[kind="primary"]:hover {
    transform: scale(1.02);
    box-shadow: 0 0 15px rgba(20, 184, 166, 0.4);
}

/* Tool Expander */
.st-emotion-cache-p5msec {
    background: rgba(0,0,0,0.2) !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

from chat import (
    load_lab_env, make_provider, to_openai_tools, load_tool_declarations,
    run_model_tool_loop, trim_history, safe_slug, now_iso, write_transcript,
    build_artifact_version, artifact_version_dict
)

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"

# Load env variables
load_lab_env(ROOT)

# UI Sidebar configuration
with st.sidebar:
    st.title("⚙️ Cấu hình Agent")
    provider_name = st.selectbox("Provider", ["openai", "openrouter", "anthropic", "gemini"], index=0)
    model_name = st.text_input("Model", value="gpt-5.5")
    version = st.text_input("Agent Version", value="v3")
    max_tool_rounds = st.number_input("Max Tool Rounds", min_value=1, max_value=10, value=4)
    history_window = st.number_input("History Window (turns)", min_value=0, max_value=20, value=5)
    
    if st.button("🗑️ Xóa Lịch Sử Chat"):
        st.session_state.history = []
        st.session_state.transcript = None
        st.session_state.turn_index = 0
        st.rerun()

# State initialization
if "history" not in st.session_state:
    st.session_state.history = []
if "transcript" not in st.session_state:
    st.session_state.transcript = None
if "turn_index" not in st.session_state:
    st.session_state.turn_index = 0

def init_transcript(provider: str, model: str, version: str, sys_prompt_path: Path, tools_path: Path):
    if st.session_state.transcript is None:
        artifact_version = build_artifact_version(version, sys_prompt_path, tools_path)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        transcript_id = f"{safe_slug(version)}_{safe_slug(provider)}_{timestamp}"
        
        st.session_state.transcript = {
            "transcript_id": transcript_id,
            **artifact_version_dict(artifact_version),
            "provider": provider,
            "model": model,
            "system_prompt": sys_prompt_path.read_text(encoding="utf-8"),
            "tools": str(tools_path),
            "history_window": history_window,
            "max_tool_rounds": max_tool_rounds,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "turns": []
        }

st.title("💬 Trợ lý IT Helpdesk")
st.markdown("Xin chào! Tôi có thể giúp gì cho bạn hôm nay?")

# Display existing chat messages
for msg in st.session_state.history:
    avatar_icon = "🧑‍💻" if msg["role"] == "user" else "✨"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])
        if "tool_events" in msg and msg["tool_events"]:
            with st.expander("🛠️ Xem chi tiết Tool Calls"):
                st.json(msg["tool_events"])

# Chat input
if prompt := st.chat_input("Nhập câu hỏi của bạn..."):
    # Display user message immediately
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)
    
    # Save user message to history
    st.session_state.history.append({"role": "user", "content": prompt})
    st.session_state.turn_index += 1
    
    # Initialize components
    sys_prompt_path = ARTIFACTS_DIR / "system_prompt.md"
    tools_path = ARTIFACTS_DIR / "tools.yaml"
    
    system_prompt = sys_prompt_path.read_text(encoding="utf-8")
    openai_tools = to_openai_tools(load_tool_declarations(tools_path))
    provider = make_provider(provider_name)
    
    init_transcript(provider_name, model_name, version, sys_prompt_path, tools_path)
    
    # Prepare messages for model
    history_for_trim = [{"role": msg["role"], "content": msg["content"]} for msg in st.session_state.history[:-1]]
    messages = [
        {"role": "system", "content": system_prompt},
        *trim_history(history_for_trim, history_window),
        {"role": "user", "content": prompt}
    ]
    
    turn_record = {
        "turn_index": st.session_state.turn_index,
        "started_at": now_iso(),
        "user": prompt,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": []
    }
    
    with st.chat_message("assistant", avatar="✨"):
        with st.spinner("Đang suy nghĩ..."):
            try:
                result = run_model_tool_loop(
                    provider=provider,
                    messages=messages,
                    tools=openai_tools,
                    model=model_name,
                    max_tool_rounds=max_tool_rounds,
                )
                
                assistant_text = result.get("assistant_text", "")
                tool_events = result.get("tool_events", [])
                
                # Render results
                st.markdown(assistant_text)
                if tool_events:
                    with st.expander("🛠️ Xem chi tiết Tool Calls"):
                        st.json(tool_events)
                
                # Append assistant response to history
                st.session_state.history.append({
                    "role": "assistant", 
                    "content": assistant_text,
                    "tool_events": tool_events
                })
                
                turn_record.update(result)
                
            except Exception as e:
                error_msg = f"**Lỗi Provider:** {type(e).__name__} - {str(e)}"
                st.error(error_msg)
                st.session_state.history.append({"role": "assistant", "content": error_msg})
                turn_record.update({"status": "provider_error", "error": str(e)})

    # Save transcript
    turn_record["ended_at"] = now_iso()
    st.session_state.transcript["turns"].append(turn_record)
    st.session_state.transcript["updated_at"] = now_iso()
    
    transcript_path = ROOT / "transcripts" / f"{st.session_state.transcript['transcript_id']}.transcript.json"
    write_transcript(transcript_path, st.session_state.transcript)
