import os
import uuid
import requests
import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.classes.config import Property, Configure, DataType
from utils import compute_hash
import time
import json

env_path = os.path.join(os.path.dirname(__file__), "weaviate_creds.env")
load_dotenv(env_path)

def get_weaviate_client():
    url = os.getenv("WEAVIATE_URL")
    key = os.getenv("WEAVIATE_API_KEY")

    if not url or not key:
        raise ValueError("Weaviate URL or API Key missing.")

    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=Auth.api_key(key),
    )

    for name in ["FXCodeEmbeddings", "UserCodeEmbeddings"]:
        if not client.collections.exists(name):
            properties = [
                Property(name="code", data_type=DataType.TEXT, vectorizePropertyName=True)
            ]

            if name == "FXCodeEmbeddings":
                properties.extend([
                    Property(name="file_name", data_type=DataType.TEXT, vectorizePropertyName=False),
                    Property(name="code_hash", data_type=DataType.TEXT, vectorizePropertyName=False)
                ])
            elif name == "UserCodeEmbeddings":
                properties.append(
                    Property(name="code_id", data_type=DataType.TEXT, vectorizePropertyName=False)
                )

            client.collections.create(
                name=name,
                vectorizer_config=Configure.Vectorizer.text2vec_weaviate(),
                properties=properties
            )

    return client

def store_framework_embedding(client, file_name, code_str):
    _store_embedding(client, file_name, code_str, "FXCodeEmbeddings")

def store_user_embedding(client, code_str):
    collection = client.collections.get("UserCodeEmbeddings")
    code_id = str(uuid.uuid4())
    properties = {
        "code": code_str,
        "code_id": code_id
    }

    collection.data.insert(uuid=code_id, properties=properties)
    time.sleep(2)  # Allow time for vectorization

    # Verify vector exists using fetch_object_by_id
    result = collection.query.fetch_object_by_id(code_id, include_vector=True)
    if not result or not result.vector:
        raise ValueError("❌ Vector not generated for user code")

    print(f"✅ Stored user code with ID: {code_id}")
    return code_id

def get_user_vector(client, code_id):
    collection = client.collections.get("UserCodeEmbeddings")

    result = collection.query.fetch_object_by_id(code_id, include_vector=True)
    
    if result and result.vector:
        print(f"✅ Retrieved vector for user code ID {code_id}")
        return result.vector
    else:
        print(f"⚠️ Vector not found for ID {code_id}. Trying again in 4 seconds...")
        time.sleep(4)
        result = collection.query.fetch_object_by_id(code_id, include_vector=True)
        if result and result.vector:
            print(f"✅ Vector found on retry for ID {code_id}")
            return result.vector

    raise ValueError(f"❌ User vector still empty after retry for code ID: {code_id}")

def _store_embedding(client, file_name, code_str, collection_name):
    collection = client.collections.get(collection_name)
    code_hash = compute_hash(code_str)

    result = collection.query.fetch_objects(
        filters=Filter.by_property("file_name").equal(file_name)
    )

    if result.objects:
        obj = result.objects[0]
        if obj.properties.get("code_hash") == code_hash:
            print(f"🟡 {file_name} unchanged. Skipping.")
            return
        else:
            print(f"🟠 {file_name} changed. Updating.")
            collection.data.delete_many(where=Filter.by_property("file_name").equal(file_name))

    properties = {
        "file_name": file_name,
        "code": code_str,
        "code_hash": code_hash
    }
    collection.data.insert(properties=properties)
    print(f"✅ {file_name} stored in {collection_name}.")

def retrieve_framework_context(client, user_vector, top_k=3):
    if not user_vector:
        raise ValueError("❌ Cannot retrieve context - user vector is empty")

    collection = client.collections.get("FXCodeEmbeddings")
    results = collection.query.near_vector(
        near_vector=user_vector,
        limit=top_k,
        return_metadata=MetadataQuery(distance=True)
    )
    return results.objects

def generate_code_suggestion(user_code, user_prompt, retrieved_context):
    snippets = "\n\n".join([
        f"{i+1}.\n{obj.properties['code']}" for i, obj in enumerate(retrieved_context)
    ])
    prompt = f"""
The user has submitted this C# code:

{user_code}

Instruction: "{user_prompt}"

Here are some framework references:

{snippets}

Now return the improved version of the code based on internal methods. ONLY return the updated code.
"""
    response = requests.post("http://localhost:11434/api/chat", json={
        "model": "mistral",
        "messages": [
            {"role": "system", "content": "You are a C# code optimizer AI."},
            {"role": "user", "content": prompt}
        ],
        "stream": False
    })

    if response.status_code == 200:
        return response.json()["message"]["content"]
    else:
        raise Exception(f"Failed to generate suggestion: {response.text}")
