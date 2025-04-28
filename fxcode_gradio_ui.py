# fxcode_gradio_ui.py

import gradio as gr
from weaviate_config import get_weaviate_client, store_framework_embedding
from weaviate_agent import parse_csproj_and_extract_code
from utils import compute_hash
from weaviate.classes.query import Filter

# === CRUD Operations ===

def create_embeddings(csproj_path, file_names):
    client = get_weaviate_client()
    file_list = [f.strip() for f in file_names.split(",") if f.strip()]
    snippets = parse_csproj_and_extract_code(csproj_path, file_list)

    if not snippets:
        return "❌ No valid code snippets found."

    results = {}
    for fname, code in snippets.items():
        try:
            result = store_framework_embedding(client, fname, code)
            results[fname] = f"✅ Embedded (hash: {compute_hash(code)[:8]})"
        except Exception as e:
            results[fname] = f"❌ Error: {str(e)}"
    client.close()

    return "\n".join(f"{fname}: {status}" for fname, status in results.items())

def read_embeddings(file_names, selected_props_csv):
    client = get_weaviate_client()
    file_list = [f.strip() for f in file_names.split(",") if f.strip()]
    selected_props = [p.strip() for p in selected_props_csv.split(",") if p.strip()]
    results = []

    collection = client.collections.get("FXCodeEmbedding")
    for fname in file_list:
        try:
            result = collection.query.fetch_objects(
                filters=Filter.by_property("file_name").equal(fname)
            )
            if result.objects:
                props = result.objects[0].properties
                filtered_props = {k: v for k, v in props.items() if k in selected_props}
                formatted = "\n".join(f"{k}: {v}" for k, v in filtered_props.items())
                results.append(f"📄 {fname}:\n{formatted}")
            else:
                results.append(f"❌ No embedding found for: {fname}")
        except Exception as e:
            results.append(f"❌ Error reading {fname}: {str(e)}")
    client.close()
    return "\n\n".join(results)

def delete_embeddings(file_names):
    client = get_weaviate_client()
    file_list = [f.strip() for f in file_names.split(",") if f.strip()]
    results = []

    collection = client.collections.get("FXCodeEmbedding")
    for fname in file_list:
        try:
            deleted = collection.data.delete_many(where=Filter.by_property("file_name").equal(fname))
            if deleted.matches == 0:
                results.append(f"⚠️ No match found for: {fname}")
            else:
                results.append(f"🗑️ Deleted: {fname}")
        except Exception as e:
            results.append(f"❌ Error deleting {fname}: {str(e)}")
    client.close()
    return "\n".join(results)

# === Gradio Interface ===

with gr.Blocks(title="FXCodeEmbedding CRUD") as demo:
    gr.Markdown("## FXCodeEmbedding CRUD Interface")

    with gr.Tab("Create Embeddings"):
        csproj_input = gr.Textbox(label="Path to .csproj file")
        file_input_create = gr.Textbox(label="Comma-separated .cs file names (e.g., A.cs,B.cs)")
        create_btn = gr.Button("Create")
        create_output = gr.Textbox(label="Output", lines=10)
        create_btn.click(create_embeddings, [csproj_input, file_input_create], create_output)

    with gr.Tab("Read Embeddings"):
        file_input_read = gr.Textbox(label="Comma-separated .cs file names")
        props_input = gr.Textbox(label="Comma-separated properties to fetch (e.g., file_name,code,code_hash)")
        read_btn = gr.Button("Read")
        read_output = gr.Textbox(label="Output", lines=10)
        read_btn.click(read_embeddings, [file_input_read, props_input], read_output)

    with gr.Tab("Delete Embeddings"):
        file_input_delete = gr.Textbox(label="Comma-separated .cs file names")
        delete_btn = gr.Button("Delete")
        delete_output = gr.Textbox(label="Output", lines=10)
        delete_btn.click(delete_embeddings, file_input_delete, delete_output)

if __name__ == "__main__":
    demo.launch()
