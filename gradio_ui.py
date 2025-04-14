import gradio as gr
from weaviate_config import (
    get_weaviate_client, store_framework_embedding, store_user_embedding,
    retrieve_framework_context, generate_code_suggestion
)
from weaviate_agent import parse_csproj_and_extract_code

client = get_weaviate_client()

def process_inputs(csproj_path, cs_files_str, user_code, user_prompt, add_framework, optimize_code):
    result_log = []
    ai_result = ""

    try:
        if add_framework:
            target_files = [f.strip() for f in cs_files_str.split(",") if f.strip()]
            code_snippets = parse_csproj_and_extract_code(csproj_path, target_files)

            if not code_snippets:
                result_log.append("⚠️ No valid C# files found in the .csproj.")
            else:
                for file_name, code_str in code_snippets.items():
                    store_framework_embedding(client, file_name, code_str)
                    result_log.append(f"✅ Stored framework file: {file_name}")

        if optimize_code:
            code_id = store_user_embedding(client, user_code)
            user_collection = client.collections.get("UserCodeEmbeddings")
            user_object = user_collection.query.fetch_object_by_id(code_id, include_vector=True)

            if not hasattr(user_object, 'vector') or user_object.vector is None:
                raise ValueError("❌ Failed to generate vector for user code")

            user_vector = user_object.vector['default']
            context_results = retrieve_framework_context(client, user_vector)
            ai_result = generate_code_suggestion(user_code, user_prompt, context_results)

            result_log.append("✅ Optimization complete.")

        if not result_log:
            result_log.append("ℹ️ Nothing was processed. Enable one or both options.")

    except Exception as e:
        result_log.append(f"❌ Error: {str(e)}")

    return "\n".join(result_log), ai_result


with gr.Blocks(title="AIOptimind Gradio Interface") as demo:
    gr.Markdown("## 🤖 AIOptimind - Optimize your C# code with AI")

    # Checkboxes to enable sections
    add_framework = gr.Checkbox(label="Add framework code")
    optimize_code = gr.Checkbox(label="Optimize user C# code")

    # Framework section (conditionally visible)
    with gr.Group(visible=False) as framework_section:
        csproj_path = gr.Textbox(label="📂 .csproj File Path", placeholder="e.g. /path/to/project.csproj")
        cs_files = gr.Textbox(label="📄 Target C# Files (comma-separated)", placeholder="e.g. Program.cs, Startup.cs")

    # User code section (conditionally visible)
    with gr.Group(visible=False) as user_section:
        user_code = gr.Textbox(label="📝 Your C# Code", lines=10, placeholder="Paste your C# code here...")
        user_prompt = gr.Textbox(label="📌 What should the AI do?", placeholder="e.g. Optimize performance")

    # Action button
    run_button = gr.Button("🚀 Run AIOptimind")

    # Output display
    status_output = gr.Textbox(label="🧾 Status", lines=8, interactive=False)
    ai_output = gr.Textbox(label="💡 Optimized Code Output", lines=15, interactive=False)

    # Toggle section visibility
    add_framework.change(lambda val: gr.update(visible=val), inputs=add_framework, outputs=framework_section)
    optimize_code.change(lambda val: gr.update(visible=val), inputs=optimize_code, outputs=user_section)

    # Connect run button to logic
    run_button.click(
        fn=process_inputs,
        inputs=[csproj_path, cs_files, user_code, user_prompt, add_framework, optimize_code],
        outputs=[status_output, ai_output]
    )

if __name__ == "__main__":
    demo.launch()
