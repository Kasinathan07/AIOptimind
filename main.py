import os
import uuid
from weaviate_config import (
    get_weaviate_client,
    store_framework_embedding,
    store_user_embedding,
    retrieve_framework_context,
    generate_code_suggestion
)
from weaviate_agent import parse_csproj_and_extract_code

def prompt_user(prompt_text):
    return input(f"{prompt_text.strip()} ").strip().lower()

def read_multiline_input(prompt_text):
    print(prompt_text)
    lines = []
    while True:
        line = input(" ➤ ")
        if line.strip() == "":
            break
        lines.append(line.strip())
    return "\n".join(lines)

def run_agent():
    client = None
    try:
        print("🤖 [AIOptimind] Welcome to AIOptimind Agent v1.0")

        if prompt_user("🔧 Do you want to add framework code? (yes/no):") == "yes":
            csproj_path = input("📂 Enter path to .csproj file: ").strip()
            target_files = []
            print("📄 Enter target C# filenames (e.g., Program.cs). Press Enter on empty line to finish:")
            while True:
                file = input(" ➤ File name: ").strip()
                if file == "":
                    break
                target_files.append(file)

            code_snippets = parse_csproj_and_extract_code(csproj_path, target_files)
            client = get_weaviate_client()

            for file_name, code_str in code_snippets.items():
                store_framework_embedding(client, file_name, code_str)

            print("✅ Framework code embedded and stored.\n")

        if prompt_user("🚀 Do you want to optimize your own C# code? (yes/no):") == "yes":
            if client is None:
                client = get_weaviate_client()

            user_code = read_multiline_input("📝 Paste your C# code (press Enter on empty line to finish):")
            user_prompt = input("📌 What do you want the AI to do with this code?: ").strip()

            code_id = store_user_embedding(client, user_code)
            print(f"✅ User code stored with ID: {code_id}")

            user_collection = client.collections.get("UserCodeEmbeddings")
            user_object = user_collection.query.fetch_object_by_id(code_id, include_vector=True)
            
            if not hasattr(user_object, 'vector') or user_object.vector is None:
                raise ValueError("Failed to generate vector for user code")
                
            user_vector = user_object.vector['default']
            context_results = retrieve_framework_context(client, user_vector)

            ai_result = generate_code_suggestion(user_code, user_prompt, context_results)
            print("\n💡 Optimized Output:\n")
            print(ai_result)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        if client is not None:
            client.close()

if __name__ == "__main__":
    run_agent()