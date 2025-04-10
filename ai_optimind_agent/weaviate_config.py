import os
import uuid
import requests
import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.classes.config import Property, Configure, DataType
from utils import compute_hash

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

    for name in ["AppCRUDVectorEmbeddings", "UserCodeVectorEmbeddings"]:
        if not client.collections.exists(name):
            properties = [
                Property(name="file_name", data_type=DataType.TEXT, vectorizePropertyName=False),
                Property(name="code", data_type=DataType.TEXT, vectorizePropertyName=True)
            ]

            if name == "AppCRUDVectorEmbeddings":
                properties.append(
                    Property(name="code_hash", data_type=DataType.TEXT, vectorizePropertyName=False)
                )
            elif name == "UserCodeVectorEmbeddings":
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
    _store_embedding(client, file_name, code_str, "AppCRUDVectorEmbeddings")

def store_user_embedding(client, code_str):
    collection = client.collections.get("UserCodeVectorEmbeddings")
    code_id = str(uuid.uuid4())
    properties = {
        "file_name": "user_code",
        "code": code_str,
        "code_id": code_id
    }
    collection.data.insert(uuid=code_id, properties=properties)
    print(f"✅ User code stored with ID: {code_id}")
    return code_id

def get_user_vector_by_code_id(client, code_id):
    collection = client.collections.get("UserCodeVectorEmbeddings")
    results = collection.query.fetch_objects(
        filters=Filter.by_property("code_id").equal(code_id),
        limit=1,
        return_metadata=MetadataQuery(vector=True)
    )

    if not results.objects or results.objects[0].vector is None:
        raise ValueError("❌ Failed to retrieve user code vector.")

    return results.objects[0].vector

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
    collection = client.collections.get("AppCRUDVectorEmbeddings")
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
