import gradio as gr
import json
import os
import atexit
import warnings
import asyncio


from weaviate_config import (
    get_weaviate_client, store_framework_embedding, store_user_embedding,
    retrieve_framework_context, generate_code_suggestion
)
from weaviate_agent import parse_csproj_and_extract_code

# ========== Environment Setup ==========
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

warnings.filterwarnings("ignore", category=DeprecationWarning)

client = get_weaviate_client()
atexit.register(lambda: client.close())

# ========== History Utils ==========
HISTORY_FILE = "chat_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)        
    return [{"role": "assistant", "content": "👋 Welcome! What would you like to do?"}]

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f)

def clear_chat():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
    return [{"role": "assistant", "content": "👋 Welcome! What would you like to do?"}], {"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False}}, "last_bug_result" : None, "last_test_result": None}, gr.update(value=None,visible=True), gr.update(value=None,visible=False)

# ========== Chat Logic ==========
def chat_interaction(user_input, history, state):
    history = history or []
    chat_history = history.copy()

    if not state or not isinstance(state, dict):
        state = {"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False} , "last_bug_result" : None, "last_test_result": None}}

    step = state["step"]
    task = state["task"]       
    
    if step == 0:
        # Do nothing, radio is expected to handle it
        if user_input == None or (user_input.lower() != "Framework Embedding" and user_input.lower() !="Optimize Code") : 
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": "Hi! Please select any of the options below."})
        return "", chat_history, state, gr.update(visible=False), gr.update(visible=True)

    if task == "embedding":
        if step == 1:
            if "csproj" not in user_input:
                chat_history.append({"role": "user", "content": user_input})
                chat_history.append({"role": "assistant", "content": "⚠️ Invalid path. Please enter the full path to your `.csproj` file."})
                return "", chat_history, state, gr.update(visible=False), gr.update(visible=False)
            state["inputs"]["csproj"] = user_input
            state["step"] = 2
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": "📄 Please enter the file names to embed (comma-separated)."})
        elif step == 2:
            state["inputs"]["files"] = user_input
            chat_history.append({"role": "user", "content": user_input})
            try:
                csproj_path = state["inputs"]["csproj"]
                file_names = [f.strip() for f in user_input.split(",")]
                snippets = parse_csproj_and_extract_code(csproj_path, file_names)                
                if not snippets:
                    chat_history.append({"role": "assistant", "content": "⚠️ No valid C# files found."})
                else:
                    for fname, code in snippets.items():
                        result_state = store_framework_embedding(client, fname, code)
                        if result_state == "changed":
                            chat_history.append({"role": "assistant", "content": f"✅ Stored: {fname}"})
                        elif result_state == "unchanged":
                            chat_history.append({"role": "assistant", "content": f"The File {fname} is already stored."})                        
                chat_history.append({"role": "assistant", "content": "🎉 Done! What would you like to do next?"})
                chat_history.append({"role": "assistant", "content": "__task_radio__"})
            except Exception as e:
                chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})
            state["step"] = 0

        elif step == 3:
            state["inputs"]["custom_prompt"] = user_input
            chat_history.append({"role": "user", "content": user_input})
            try:
                code = state["inputs"]["code"]
                code_id = store_user_embedding(client, code)
                user_obj = client.collections.get("UserCodeEmbeddings").query.fetch_object_by_id(code_id, include_vector=True)
                user_vector = user_obj.vector['default']
                context = retrieve_framework_context(client, user_vector)
                prompt = f"Optimize the following code with the given user intent: {user_input}"
                result, usage = generate_code_suggestion(code, prompt, context, state)
                chat_history.append({"role": "assistant", "content": result})
            except Exception as e:
                chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})

            state["step"] = 0

    elif task == "optimize":
        if step == 1:
            state["inputs"]["code"] = user_input
            state["step"] = 2
            chat_history.append({"role": "user", "content": f"```csharp\n{user_input}\n```"})
            chat_history.append({"role": "assistant", "content": "☑️ What do you want to do next?"})
            chat_history.append({"role": "assistant", "content": "__option_radio__"})
    if step == 3 and task == "embedding":
        show_task_radio = False
    show_task_radio = any(m["content"] == "__task_radio__" for m in chat_history)
    show_option_radio = any(m["content"] == "__option_radio__" for m in chat_history)
    save_history(chat_history)
    #return "", chat_history, state, gr.update(visible=False), gr.update(visible=show_task_radio)
    return "", chat_history, state, gr.update(visible="__option_radio__" in [m["content"] for m in chat_history]), gr.update(visible=show_task_radio)

def handle_task_selection(task_choice, state, history):
    chat_history = history or []
    chat_history = [msg for msg in chat_history if msg["content"] != "__task_radio__"]

    if not task_choice:
        return "", chat_history, state, gr.update(visible=True), gr.update(visible=False)

    chat_history.append({"role": "user", "content": task_choice})

    if not state or not isinstance(state, dict):
        state = {"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False}, "last_bug_result" : None, "last_test_result": None}}

    if "optimize" in task_choice.lower():
        state["task"] = "optimize"
        state["step"] = 1
        chat_history.append({"role": "assistant", "content": "📝 Please paste your C# code."})
    elif "framework" in task_choice.lower():
        state["task"] = "embedding"
        state["step"] = 1
        chat_history.append({"role": "assistant", "content": "🛠 Please enter the full path to your `.csproj` file."})

    save_history(chat_history)
    return "", chat_history, state, gr.update(visible=False), gr.update(visible=False)

def handle_radio_selection(selected_option, state, history):
    chat_history = [msg for msg in (history or []) if msg["content"] != "__option_radio__"]
    chat_history.append({"role": "user", "content": selected_option})

    if not state or not isinstance(state, dict):
        state = {"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False}, "last_bug_result" : None, "last_test_result": None}}
    if not selected_option:
        return chat_history, state, gr.update(visible=True), gr.update(visible=False)
    flags = {
        "test": "test" in selected_option.lower(),
        "optimize": "optimize" in selected_option.lower(),
        "bug": "bug" in selected_option.lower()
    }
    state["inputs"]["flags"] = flags

    try:
        code = state["inputs"]["code"]
        code_id = store_user_embedding(client, code)
        user_obj = client.collections.get("UserCodeEmbeddings").query.fetch_object_by_id(code_id, include_vector=True)

        if not hasattr(user_obj, 'vector') or user_obj.vector is None:
            raise ValueError("❌ Vector not generated for user code")

        user_vector = user_obj.vector['default']
        context = retrieve_framework_context(client, user_vector)

    
        
        if flags["bug"]:
            bug_prompt = "Find bugs for the code based on the internal framework patterns and explain them.\n"
            result, _ = generate_code_suggestion(code, bug_prompt, context, state)
            state["inputs"]["last_bug_result"] = result
            chat_history.append({"role": "assistant", "content": result})
            chat_history.append({"role": "assistant", "content": "Want to fix it? Or optimize it?"})
            state["step"] = 2
        elif flags["optimize"]:
            if "last_bug_result" in state["inputs"] and state["inputs"]["last_bug_result"]:
                prompt = "Optimize the code based on the following bugs and return fixes for each bug:\n" + state["inputs"]["last_bug_result"]
                result, _ = generate_code_suggestion(code, prompt, context, state)
                chat_history.append({"role": "assistant", "content": result})
            elif "last_test_result" in state["inputs"] and state["inputs"]["last_test_result"]:
                prompt = "Optimize the code based on the following test cases and return fixes for each test case:\n" + state["inputs"]["last_test_result"]
                result, _ = generate_code_suggestion(code, prompt, context, state)
                chat_history.append({"role": "assistant", "content": result})
            else:
                chat_history.append({"role": "assistant", "content": "🔍 What exactly do you want to optimize?"})
                state["step"] = 3
        elif flags["test"]:
            prompt = "Write test cases for the code based on the internal framework patterns and explain them.\n"
            result, _ = generate_code_suggestion(code, prompt, context, state)
            state["inputs"]["last_test_result"] = result
            chat_history.append({"role": "assistant", "content": result})

        # result, usage = generate_code_suggestion(code, prompt, context, state)
        # chat_history.append({"role": "assistant", "content": result})
        chat_history.append({"role": "assistant", "content": "🎯 Anything else?"})
        #chat_history.append({"role": "assistant", "content": "__task_radio__"})
        if flags["bug"] :
            show_task_radio = False
            show_option_radio = True
        elif flags["optimize"]:
            show_task_radio = False
            show_option_radio = True
        elif flags["test"]:
            show_task_radio = False
            show_option_radio = True
    except Exception as e:
        chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})

    state["step"] = 0
    save_history(chat_history)
    return chat_history, state, gr.update(show_task_radio),gr.update(show_option_radio)

# ========== UI Layout ==========
with gr.Blocks(title="AIOptimind", css="""
#send-btn {
    background-color: blue;
    color: white;    
    font-size: 24px;
}
#clear-btn {
    background-color: blue;
    color: white;
    font-weight: bold;
}
""")as demo:
    gr.Markdown("## 🤖 AIOptimind - Chat with your Code Assistant")

    chatbot = gr.Chatbot(label="AI Chat", height=600, type="messages", avatar_images=("user.jpg", "chatbot.jpg"), value=load_history())
    state_box = gr.State({"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False},"last_bug_result":None ,"last_test_result":None}})

    #task_radio = gr.Radio(["Framework Embedding", "Optimize Code"], visible=True, label="Choose task",value=None)
    with gr.Column(visible=True, elem_id="task-radio-container") as task_container:
        task_radio = gr.Radio(["Framework Embedding", "Optimize Code"], visible=True, label="Choose task", value=None)

    option_radio = gr.Radio(["Write Test Cases", "Optimize Code", "Find Bug"], visible=False, label="Choose option",value=None)

    with gr.Row():
            user_input = gr.Textbox(
                show_label=False,
                placeholder="Type your message...",
                scale=10
            )
            send_btn = gr.Button("➤", scale=1,elem_id="send-btn")

    user_input.submit(chat_interaction, [user_input, chatbot, state_box], [user_input, chatbot, state_box, option_radio,task_radio])
    send_btn.click(chat_interaction, [user_input, chatbot, state_box], [user_input, chatbot, state_box, option_radio,task_radio])
    task_radio.change(handle_task_selection, [task_radio, state_box, chatbot], [user_input, chatbot, state_box, task_radio,option_radio])
    option_radio.change(handle_radio_selection, [option_radio, state_box, chatbot], [chatbot, state_box, task_radio,option_radio])

    gr.Button("Clear Chat", elem_id="clear-btn").click(fn=clear_chat, outputs=[chatbot, state_box, task_radio, option_radio])

if __name__ == "__main__":
    demo.launch()
