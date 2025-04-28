# fxcode_crud.py

import argparse
from weaviate_config import get_weaviate_client, store_framework_embedding
from weaviate_agent import parse_csproj_and_extract_code
from utils import compute_hash
from ollama_config import get_embedding
from weaviate.classes.query import Filter

USE_MANUAL_EMBEDDING = True  # Keep this aligned with weaviate_config

def create_or_update_framework_embeddings(client, snippets):
    """
    Given a dict of {filename: code}, embed and store them into FXCodeEmbedding.
    """
    result_summary = {}
    for fname, code in snippets.items():
        try:
            result = store_framework_embedding(client, fname, code)
            result_summary[fname] = result
        except Exception as e:
            print(f"❌ Error embedding {fname}: {str(e)}")
            result_summary[fname] = "error"
    return result_summary

def read_framework_embeddings(client, file_names):
    """
    Read and print metadata for one or more embedded files.
    """
    collection = client.collections.get("FXCodeEmbedding")
    for fname in file_names:
        try:
            result = collection.query.fetch_objects(
                filters=Filter.by_property("file_name").equal(fname)
            )
            if result.objects:
                print(f"\n📄 {fname}:")
                print(result.objects[0].properties)
            else:
                print(f"\n❌ No embedding found for: {fname}")
        except Exception as e:
            print(f"❌ Error reading {fname}: {str(e)}")

def delete_framework_embeddings(client, file_names):
    """
    Delete one or more embeddings based on file names.
    """
    collection = client.collections.get("FXCodeEmbedding")
    for fname in file_names:
        try:
            deleted = collection.data.delete_many(where=Filter.by_property("file_name").equal(fname))
            if deleted.matches == 0:
                print(f"⚠️ No match found for: {fname}")
            else:
                print(f"🗑️ Deleted: {fname}")

        except Exception as e:
            print(f"❌ Error deleting {fname}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="CRUD for FXCodeEmbedding collection in Weaviate")
    parser.add_argument("operation", choices=["create", "read", "delete"], help="CRUD operation to perform")
    parser.add_argument("--csproj", help="Path to the .csproj file (required for create)")
    parser.add_argument("--files", required=True, help="Comma-separated list of .cs file names (e.g., A.cs,B.cs)")

    args = parser.parse_args()
    file_list = [f.strip() for f in args.files.split(",")]

    try:
        client = get_weaviate_client()
    except Exception as e:
        print(f"❌ Failed to connect to Weaviate: {str(e)}")
        return
    
    try:
        if args.operation == "create":
            if not args.csproj:
                print("❌ Please provide --csproj path for 'create' operation.")
                return

            print(f"📁 Parsing project: {args.csproj}")
            snippets = parse_csproj_and_extract_code(args.csproj, file_list)

            if not snippets:
                print("❌ No valid code snippets found.")
                return

            print(f"📦 Embedding {len(snippets)} file(s)...")
            results = create_or_update_framework_embeddings(client, snippets)

            print("\n📊 Embedding Summary:")
            for fname, status in results.items():
                print(f"• {fname}: {status}")

        elif args.operation == "read":
            read_framework_embeddings(client, file_list)

        elif args.operation == "delete":
            delete_framework_embeddings(client, file_list)
    finally:
        client.close()        

if __name__ == "__main__":
    main()
