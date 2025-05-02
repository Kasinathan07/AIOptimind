import os
import gradio as gr
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import requests
import re

from weaviate_config import get_weaviate_client  # ✅ Import client initializer

# Load environment variables
load_dotenv(dotenv_path=Path("weaviate_creds.env"))

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ Initialize Weaviate client
weaviate_client = get_weaviate_client()

# ✅ Preload all FXCodeEmbedding entries with vectors
def preload_fxcode_with_vectors():
    collection = weaviate_client.collections.get("FXCodeEmbedding")
    results = collection.query.fetch_objects(include_vector=True)
    print(f"✅ Loaded {len(results.objects)} FX framework entries with vectors.")
    return results.objects

# ✅ Cache the FX framework context at startup
fx_context_cache = preload_fxcode_with_vectors()

def is_code_snippet(text):
    # Check for common code elements like braces, semicolons, or keywords
    return bool(re.search(r'[{};]|class |void |public |private |int |string ', text))

def process_message(message):
    # Split the message into code and text, if both are present
    code_snippets = []
    text_parts = []
    
    # Split the input message by lines or other delimiters
    lines = message.split("\n")
    
    for line in lines:
        if is_code_snippet(line):
            code_snippets.append(line)
        else:
            text_parts.append(line)

    return "\n".join(text_parts), "\n".join(code_snippets)

# ✅ Chat function using cached context
def chat_with_gpt(message, chat_history):
    if chat_history is None:
        chat_history = []

    messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]

    snippets = "\n\n".join([
        f"{i+1}. {obj.properties['file_name']}:\n{obj.properties['code']}"
        for i, obj in enumerate(fx_context_cache[:10])
    ])
    system_prompt = (
        "You are a C# code assistant with access to the following internal framework patterns.\n\n"
        "Use these patterns to guide your suggestions, optimizations, or bug fixes.\n\n"
        f"{snippets}"
    )

    messages.insert(0, {"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"❌ Error: {e}"

    # Split the user message into text and code parts
    text_part, code_part = process_message(message)
    
    # Add the text and code separately to chat history
    chat_history.append({"role": "user", "content": text_part})
    if code_part:
        user_display_code = f"```\n{code_part}\n```"  # Markdown for code block
        chat_history.append({"role": "user", "content": user_display_code})
    #     def is_code_snippet(text):
#         # Simple check: presence of semicolons, braces, or keywords
#         return bool(re.search(r'[{};]|class |void |public |private |int |string ', text))

#     # ...

#     user_display = f"
# \n{message}\n
# " if is_code_snippet(message) else message
#     chat_history.append({"role": "user", "content": user_display})

    # chat_history.append({"role":"user","content":messages})
    chat_history.append({"role": "assistant", "content": reply})

    return chat_history, ""  # Return updated chat history and clear message box

def login_user(username, password):
    try:
        payload = f"grant_type=password&username={username}&password={password}&ExternalURL=dev.myhub.plus&TimeZone=-330"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post("https://sitauth.myhub.plus/token", data=payload, headers=headers)
        if response.status_code == 200:
            user_info = response.json()
            return True, "✅ Login Successful", user_info
        else:
            return False, f"❌ Login Failed: {response.text}", None
    except Exception as e:
        return False, f"❌ Error: {str(e)}", None

def handle_login(username, password):
    success, message, user_info = login_user(username, password)
    if success:
        gr.Info(message, duration=5)              # ✅ show success popup
        return (
            gr.update(visible=False),     # Hide login screen
            gr.update(visible=True),      # Show chat screen
            gr.update(value=message, visible=False),  # Hide message box
        )
    else:
        gr.Info("❌ Incorrect username or password.", duration=5)  # ✅ Show error popup
        return (
            gr.update(visible=True),      # Keep login screen
            gr.update(visible=False),     # Hide chat screen
            gr.update(value="", visible=False),       # Hide message box
        )

# ✅ Gradio UI
with gr.Blocks() as demo:
    gr.HTML("""
    <style>
    #send-btn {
        background-color: #2979FF;
        color: white;
        font-size: 24px;
    }

    #clear-btn {
        background-color: #2979FF;
        color: white;
        font-weight: bold;
    }
    #login_screen{
        width:50%;
        margin: auto;
        position: absolute;
        top: 50%;
        left: 25%;
        right: 25%  
    }
    </style>
    """)

    # Login Screen
    with gr.Column(visible=True, elem_id="login_screen") as login_screen:
        gr.Markdown("## 🔐 Login to Continue")
        username = gr.Textbox(label="Username", elem_id="username-box")
        password = gr.Textbox(label="Password", type="password", elem_id="password-box")
        login_btn = gr.Button("Login", elem_id="send-btn")
        login_msg = gr.Markdown("", visible=False)

    # Chat Screen
    with gr.Column(visible=False, elem_id="chat_screen") as chat_screen:
        gr.Markdown("## 🤖 AIOptimind - Chat with your MYHUB Code Assistant")
        chatbot = gr.Chatbot(type="messages", height=700, show_label=False)
        with gr.Row():
            msg = gr.Textbox(show_label=False, placeholder="Type your message...", scale=10)
            send_btn = gr.Button("➤", scale=1, elem_id="send-btn")
        clear_btn = gr.Button("Clear Chat", elem_id="clear-btn")
    
    def clear():
        return []
    
    # Bind login logic
    login_btn.click(handle_login, [username, password], [login_screen, chat_screen, login_msg])
    msg.submit(chat_with_gpt, [msg, chatbot], [chatbot, msg])
    send_btn.click(chat_with_gpt, [msg, chatbot], [chatbot, msg])

    clear_btn.click(clear, outputs=chatbot)

demo.launch()
