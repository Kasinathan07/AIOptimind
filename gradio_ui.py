import gradio as gr
import asyncio
import warnings
import atexit

from weaviate_config import (
    get_weaviate_client, store_framework_embedding, store_user_embedding,
    retrieve_framework_context, generate_code_suggestion
)
from weaviate_agent import parse_csproj_and_extract_code

# Fix async loop for Windows
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

warnings.filterwarnings("ignore", category=DeprecationWarning)

client = get_weaviate_client()
atexit.register(lambda: client.close())

# === Chat Interaction Logic ===
def chat_interaction(user_input, history, state):
    history = history or []
    chat_history = history.copy()

    if not state or not isinstance(state, dict):
        state = {"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False}}}

    if "inputs" not in state:
        state["inputs"] = {}
    if "flags" not in state["inputs"]:
        state["inputs"]["flags"] = {"test": False, "optimize": False, "bug": False}

    step = state["step"]
    task = state["task"]

    if step == 0:
        if user_input.lower() in ["framework embedding", "embedding"]:
            state["task"] = "embedding"
            state["step"] = 1
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": "🛠 Please enter the full path to your `.csproj` file."})
        elif user_input.lower() in ["optimize code", "optimize"]:
            state["task"] = "optimize"
            state["step"] = 1
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": "📝 Please paste your C# code."})
        else:
            chat_history.append({"role": "assistant", "content": "👋 What would you like to do?\n\n👉 Type **Framework Embedding** or **Optimize Code** to begin."})

    elif task == "embedding":
        if step == 1:
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
                        store_framework_embedding(client, fname, code)
                        chat_history.append({"role": "assistant", "content": f"✅ Stored: {fname}"})
                chat_history.append({"role": "assistant", "content": "🎉 Done! Type another command to continue."})
            except Exception as e:
                chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})
            state["step"] = 0

    elif task == "optimize":
        if step == 1:
            state["inputs"]["code"] = user_input
            state["step"] = 2
            chat_history.append({"role": "user", "content": f"```csharp\n{user_input}\n```"})
            chat_history.append({"role": "assistant", "content": "☑️ What do you want to do?\n\n- Write Test Cases\n- Optimize Code\n- Find Bug"})
            chat_history.append({"role": "assistant", "content": "__radio__"})

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

    return "", chat_history, state, gr.update(visible="__radio__" in [m["content"] for m in chat_history])

# === Radio interaction handler ===
def handle_radio_selection(selected_option, state, history):
    chat_history = history or []
    chat_history = [msg for msg in chat_history if msg["content"] != "__radio__"]
    chat_history.append({"role": "user", "content": selected_option})

    if not state or not isinstance(state, dict):
        state = {"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False}}}

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
            if state["inputs"]["flags"].get("bug") and "last_bug_result" in state["inputs"]:
                prompt = "Optimize the code based on the following bugs:\n" + state["inputs"]["last_bug_result"]
                result, _ = generate_code_suggestion(code, prompt, context, state)
                chat_history.append({"role": "assistant", "content": result})
            else:
                chat_history.append({"role": "assistant", "content": "🔍 What exactly do you want to optimize?"})
                state["step"] = 3

        elif flags["test"]:
            prompt = "Write test cases for the code based on the internal framework patterns and explain them.\n"
            result, _ = generate_code_suggestion(code, prompt, context, state)
            chat_history.append({"role": "assistant", "content": result})

    except Exception as e:
        chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})

    return chat_history, state

# === Gradio UI ===
with gr.Blocks(title="AIOptimind") as demo:
    gr.Markdown("## 🤖 AIOptimind - Chat with your Code Assistant")

    chatbot = gr.Chatbot(label="AI Chat", height=600, type="messages")
    state_box = gr.State({"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False}}})

    radio_options = gr.Radio(
        ["Write Test Cases", "Optimize Code", "Find Bug"],
        label=None,
        interactive=True,
        visible=False
    )

    with gr.Row():
        user_input = gr.Textbox(
            show_label=False,
            placeholder="Type your message here...",
            lines=1,
            autofocus=True
        )

    user_input.submit(
        fn=chat_interaction,
        inputs=[user_input, chatbot, state_box],
        outputs=[user_input, chatbot, state_box, radio_options]
    )

    radio_options.change(
        fn=handle_radio_selection,
        inputs=[radio_options, state_box, chatbot],
        outputs=[chatbot, state_box]
    )

if __name__ == "__main__":
    demo.launch()
