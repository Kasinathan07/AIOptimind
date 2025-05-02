import os
import gradio as gr
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import requests
import re
import json
from weaviate_config import get_weaviate_client

# Load environment variables
load_dotenv(dotenv_path=Path("weaviate_creds.env"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
weaviate_client = get_weaviate_client()

# Directory to store per-user session data
SESSION_DIR = Path("sessions")
SESSION_DIR.mkdir(exist_ok=True)

def preload_fxcode_with_vectors():
    collection = weaviate_client.collections.get("FXCodeEmbedding")
    results = collection.query.fetch_objects(include_vector=True)
    print(f"✅ Loaded {len(results.objects)} FX framework entries with vectors.")
    return results.objects

fx_context_cache = preload_fxcode_with_vectors()

def is_code_snippet(text):
    return bool(re.search(r'\b(class|void|public|private|int|string)\b|[{};]', text, re.IGNORECASE))

def process_message(message):
    code_snippets = []
    text_parts = []
    lines = message.split("\n")
    for line in lines:
        if is_code_snippet(line):
            code_snippets.append(line)
        else:
            text_parts.append(line)
    text_content = "\n".join([line.strip() for line in text_parts if line.strip()])
    code_content = "\n".join([line.strip() for line in code_snippets if line.strip()])
    return text_content, code_content

def get_session_path(username):
    safe_name = username.split('@')[0]
    return SESSION_DIR / f"session_{safe_name}.json"

def load_session(username=None):
    if username:
        session_path = get_session_path(username)
        if session_path.exists():
            with open(session_path, 'r') as f:
                return json.load(f)
    return {"username": username, "chat_history": []}

def save_session(session_data):
    username = session_data.get("username")
    if username:
        session_path = get_session_path(username)
        with open(session_path, 'w') as f:
            json.dump(session_data, f, indent=4)

def login_user(username, password):
    try:
        payload = f"grant_type=password&username={username}&password={password}&ExternalURL=dev.myhub.plus&TimeZone=-330"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post("https://sitauth.myhub.plus/token", data=payload, headers=headers)
        if response.status_code == 200:
            return True, "✅ Login Successful", response.json()
        else:
            return False, f"❌ Login Failed: {response.text}", None
    except Exception as e:
        return False, f"❌ Error: {str(e)}", None

def handle_login(username, password):
    success, message, user_info = login_user(username, password)
    if success:
        gr.Info(message, duration=5)
        session_data = load_session(username)
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(value=message, visible=False),
            session_data,
            session_data.get("chat_history", [])
        )
    else:
        gr.Info("❌ Incorrect username or password.", duration=5)
        return (
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(),
            []
        )

def chat_with_gpt(message, user_data):
    chat_history = user_data.get("chat_history", [])
    messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]

    snippets = "\n\n".join([f"{i+1}. {obj.properties['file_name']}:\n{obj.properties['code']}" for i, obj in enumerate(fx_context_cache[:10])])
    system_prompt = (
        "You are a C# code assistant with access to the following internal framework patterns.\n\n"
        "Use these patterns to guide your suggestions, optimizations, or bug fixes.\n\n"
        f"{snippets}"
    )
    messages.insert(0, {"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"❌ Error: {e}"

    text_part, code_part = process_message(message)

    if text_part and not code_part:
        chat_history.append({"role": "user", "content": text_part})
    elif code_part and not text_part:
        chat_history.append({"role": "user", "content": f"```\n{code_part}\n```"})
    elif text_part and code_part:
        chat_history.append({"role": "user", "content": text_part})
        chat_history.append({"role": "user", "content": f"```\n{code_part}\n```"})

    chat_history.append({"role": "assistant", "content": reply})
    user_data["chat_history"] = chat_history

    save_session(user_data)
    return chat_history, "", user_data

def clear_chat(user_data):
    user_data["chat_history"] = []
    save_session(user_data)
    return [], user_data

# --- Gradio UI ---
with gr.Blocks() as demo:
    gr.HTML("""
    <style>
    #send-btn { background-color: #2979FF; color: white; font-size: 24px; }
    #clear-btn { background-color: #2979FF; color: white; font-weight: bold; }
    #login_screen {
        width:50%; margin: auto;
        position: absolute; top: 50%;
        left: 25%; right: 25%
    }
    </style>
    """)

    user_state = gr.State({"username": None, "chat_history": []})

    with gr.Column(visible=True, elem_id="login_screen") as login_screen:
        gr.Markdown("## 🔐 Login to Continue")
        username = gr.Textbox(label="Username", elem_id="username-box")
        password = gr.Textbox(label="Password", type="password", elem_id="password-box")
        login_btn = gr.Button("Login", elem_id="send-btn")
        login_msg = gr.Markdown("", visible=False)

    with gr.Column(visible=False, elem_id="chat_screen") as chat_screen:
        gr.Markdown("## 🤖 AIOptimind - Chat with your MYHUB Code Assistant")
        chatbot = gr.Chatbot(type="messages", height=700, show_label=False)
        with gr.Row():
            msg = gr.Textbox(show_label=False, placeholder="Type your message...", scale=10)
            send_btn = gr.Button("➤", scale=1, elem_id="send-btn")
        clear_btn = gr.Button("Clear Chat", elem_id="clear-btn")

    login_btn.click(handle_login, [username, password], [login_screen, chat_screen, login_msg, user_state, chatbot])
    msg.submit(chat_with_gpt, [msg, user_state], [chatbot, msg, user_state])
    send_btn.click(chat_with_gpt, [msg, user_state], [chatbot, msg, user_state])
    clear_btn.click(clear_chat, [user_state], [chatbot, user_state])

demo.launch()

