import os
import uuid
from weaviate_config import (
    get_weaviate_client,
    store_framework_embedding,
    store_user_embedding,
    retrieve_framework_context,
    generate_code_suggestion
)
from weaviate.classes.query import Filter
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
    print("🤖 [AIOptimind] Welcome to AIOptimind Agent v2.0")

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

        if hasattr(client, 'close'):
            client.close()
        print("✅ Framework code embedded and stored.\n")

    if prompt_user("🚀 Do you want to optimize your own C# code? (yes/no):") == "yes":
        client = get_weaviate_client()

        user_code = read_multiline_input("📝 Paste your C# code (press Enter on empty line to finish):")
        user_prompt = input("📌 What do you want the AI to do with this code?: ").strip()

        code_id = store_user_embedding(client, user_code)
        user_collection = client.collections.get("UserCodeVectorEmbeddings")
        user_obj = user_collection.query.fetch_object_by_id(code_id)

        if not user_obj or not user_obj.vector:
            raise ValueError("❌ Failed to retrieve user code vector.")

        user_vector = user_obj.vector
        similar_context = retrieve_framework_context(client, user_vector)

        print("\n🔍 Retrieving similar framework context...")
        ai_output = generate_code_suggestion(user_code, user_prompt, similar_context)

        print("\n✅ Suggested Updated Code:\n")
        print(ai_output)

        if hasattr(client, 'close'):
            client.close()

if __name__ == "__main__":
    run_agent()
