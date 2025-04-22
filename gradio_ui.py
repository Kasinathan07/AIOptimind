import gradio as gr
import json
import os
import atexit
import warnings
import asyncio
import re


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
    text_Space = False
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
        return gr.update(interactive = text_Space,value = ""),gr.update(interactive = text_Space), chat_history, state, gr.update(visible=False), gr.update(visible=True)

    if task == "embedding":
        if step == 1:
            # Regex to extract the path ending in .csproj
            match = re.search(r'[a-zA-Z]:\\(?:[^\\\s"]+\\)*[^\\\s"]+\.csproj', user_input)
            if not match:                
                chat_history.append({"role": "user", "content": user_input})
                chat_history.append({"role": "assistant", "content": "⚠️ Invalid path. Please enter the full path to your `.csproj` file."})                
                return gr.update(interactive = True,value = ""),gr.update(interactive = True), chat_history, state, gr.update(visible=False), gr.update(visible=False)            
            csproj_path = match.group()
            state["inputs"]["csproj"] = csproj_path
            state["step"] = 2
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": "📄 Please enter the file names to embed (comma-separated)."})
            text_Space = True
            show_task_radio = False
            show_option_radio = False
        elif step == 2:
            state["inputs"]["files"] = user_input
            chat_history.append({"role": "user", "content": user_input})
            try:
                csproj_path = state["inputs"]["csproj"]
                file_names = [f.strip() for f in user_input.split(",")]
                snippets = parse_csproj_and_extract_code(csproj_path, file_names)                
                if not snippets:
                    chat_history.append({"role": "assistant", "content": "⚠️ No valid C# files found. Enter the Correct File Name."})                     
                    return gr.update(interactive = text_Space,value = ""),gr.update(interactive = text_Space), chat_history, state, gr.update(visible=False), gr.update(visible=False)
                else:
                    for fname, code in snippets.items():
                        result_state = store_framework_embedding(client, fname, code)
                        if result_state == "changed":
                            chat_history.append({"role": "assistant", "content": f"✅ Stored: {fname}"})
                        elif result_state == "unchanged":
                            chat_history.append({"role": "assistant", "content": f"The File {fname} is already stored."})                        
                chat_history.append({"role": "assistant", "content": "🎉 Done! What would you like to do next?"})
                #chat_history.append({"role": "assistant", "content": "__task_radio__"})
                show_task_radio = True
                show_option_radio = False                
            except Exception as e:
                chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})
            state["step"] = 0

        # elif step == 3:
        #     state["inputs"]["custom_prompt"] = user_input
        #     chat_history.append({"role": "user", "content": user_input})
        #     try:
        #         code = state["inputs"]["code"]
        #         code_id = store_user_embedding(client, code)
        #         user_obj = client.collections.get("UserCodeEmbeddings").query.fetch_object_by_id(code_id, include_vector=True)
        #         user_vector = user_obj.vector['default']
        #         context = retrieve_framework_context(client, user_vector)
        #         prompt = f"Optimize the following code with the given user intent: {user_input}"
        #         result, usage = generate_code_suggestion(code, prompt, context, state)
        #         chat_history.append({"role": "assistant", "content": result})
        #     except Exception as e:
        #         chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})

            state["step"] = 0

    elif task == "optimize":
        if step == 1:
            state["inputs"]["code"] = user_input
            state["step"] = 2
            chat_history.append({"role": "user", "content": f"```csharp\n{user_input}\n```"})
            chat_history.append({"role": "assistant", "content": "☑️ What do you want to do next?"})
            #chat_history.append({"role": "assistant", "content": "__option_radio__"})
            show_task_radio = False
            show_option_radio = True
        elif step == 2:
            chat_history.append({"role": "user", "content": user_input})
            try:
                code = state["inputs"]["code"]
                Usercode_id = state["inputs"]["code_id"]
                userCode_obj = client.collections.get("UserCodeEmbeddings").query.fetch_object_by_id(Usercode_id, include_vector=True)
                if not hasattr(userCode_obj, 'vector') or userCode_obj.vector is None:
                    raise ValueError("❌ Vector not generated for user code")
                user_vector = userCode_obj.vector['default']
                FXcontext = retrieve_framework_context(client, user_vector)
                prompt = f"Optimize the following code with the given user input: {user_input}"
                result, usage = generate_code_suggestion(code, prompt, FXcontext, state)
                chat_history.append({"role": "assistant", "content": result})
                show_task_radio = True
                show_option_radio = False                
            except Exception as e:
                chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})
            state["step"] = 0
    if step == 3 and task == "embedding":
        show_task_radio = False
    #show_task_radio = any(m["content"] == "__task_radio__" for m in chat_history)
    #show_option_radio = any(m["content"] == "__option_radio__" for m in chat_history)
    save_history(chat_history)
    #return "", chat_history, state, gr.update(visible=False), gr.update(visible=show_task_radio)
    return gr.update(interactive = text_Space,value = ""),gr.update(interactive = text_Space), chat_history, state, gr.update(visible=show_option_radio), gr.update(visible=show_task_radio)
def handle_task_selection(task_choice, state, history):
    text_Space = False
    chat_history = history or []
    if not task_choice:
        return gr.update(interactive = text_Space,value = ""),gr.update(interactive = text_Space), chat_history, state, gr.update(visible=True), gr.update(visible=False)
    
    chat_history = [msg for msg in chat_history if msg["content"] != "__task_radio__"]
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
    return gr.update(interactive = True,value = ""),gr.update(interactive = True), chat_history, state, gr.update(visible=False), gr.update(visible=False)

def handle_radio_selection(selected_option, state, history):
    text_Space = False
    chat_history = [msg for msg in (history or []) if msg["content"] != "__option_radio__"]
    if not selected_option:
        return gr.update(interactive = text_Space,value = ""),gr.update(interactive = text_Space),chat_history, state, gr.update(visible=True), gr.update(visible=False)    
    chat_history.append({"role": "user", "content": selected_option})
    Optimize_From = ""    
    if not state or not isinstance(state, dict):
        state = {"task": None, "step": 0, "inputs": {"flags": {"test": False, "optimize": False, "bug": False}, "last_bug_result" : None, "last_test_result": None}}    
    flags = {
        "test": "test" in selected_option.lower(),
        "optimize": "optimize" in selected_option.lower(),
        "bug": "bug" in selected_option.lower()
    }
    state["inputs"]["flags"] = flags

    try:
        code = state["inputs"]["code"]
        code_id = store_user_embedding(client, code)
        state["inputs"]["code_id"] = code_id
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
                Optimize_From = "last_bug_result"
            elif "last_test_result" in state["inputs"] and state["inputs"]["last_test_result"]:
                prompt = "Optimize the code based on the following test cases and return fixes for each test case and expalin them how its passed those test cases:\n" + state["inputs"]["last_test_result"] 
                result, _ = generate_code_suggestion(code, prompt, context, state)
                chat_history.append({"role": "assistant", "content": result})
                Optimize_From = "last_test_result"
            else:
                chat_history.append({"role": "assistant", "content": "🔍 What exactly do you want to optimize?"})
                state["step"] = 3
                Optimize_From = "User_Prompt"
        elif flags["test"]:
            prompt = "Write the Unit test cases for the code and explain the scenarios for those cases.\n"
            result, _ = generate_code_suggestion(code, prompt, context, state)
            state["inputs"]["last_test_result"] = result
            chat_history.append({"role": "assistant", "content": result})
        if flags["bug"] :
            show_task_radio = False
            show_option_radio = True            
        elif flags["optimize"] and Optimize_From == "User_Prompt":
            show_task_radio = False
            show_option_radio = False
            text_Space = True   
        elif flags["optimize"] and (Optimize_From == "last_bug_result" or Optimize_From == "last_test_result"):
            show_task_radio = True
            show_option_radio = False
        elif flags["test"]:
            show_task_radio = False
            show_option_radio = True
    except Exception as e:
        chat_history.append({"role": "assistant", "content": f"❌ Error: {str(e)}"})

    if state["step"] == 3:
        state["step"] = 2
    else:
        state["step"] = 0   
    save_history(chat_history)
    return gr.update(interactive = text_Space,value = ""),gr.update(interactive = text_Space),chat_history, state, gr.update(visible = show_task_radio),gr.update(visible = show_option_radio)


# ========== UI Layout ==========
with gr.Blocks(title="AIOptimind", css="""
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
""")as demo:
    gr.Markdown("## 🤖 AIOptimind - Chat with your MYHUB Code Assistant")

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
                scale=10,
                interactive=False
            )
            send_btn = gr.Button("➤", scale=1,elem_id="send-btn",interactive=False)            

    user_input.submit(chat_interaction, [user_input, chatbot, state_box], [user_input,send_btn, chatbot, state_box, option_radio,task_radio])
    send_btn.click(chat_interaction, [user_input, chatbot, state_box], [user_input,send_btn, chatbot, state_box, option_radio,task_radio])
    task_radio.select(handle_task_selection, [task_radio, state_box, chatbot], [user_input,send_btn, chatbot, state_box, task_radio,option_radio])    
    option_radio.select(handle_radio_selection, [option_radio, state_box, chatbot], [user_input,send_btn,chatbot, state_box, task_radio,option_radio])

    gr.Button("Clear Chat", elem_id="clear-btn").click(fn=clear_chat, outputs=[chatbot, state_box, task_radio, option_radio])

if __name__ == "__main__":
    demo.launch()
