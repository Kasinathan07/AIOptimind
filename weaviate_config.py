import os
import weaviate
import requests
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from weaviate.classes.query import MetadataQuery,Filter

env_path = os.path.join(os.path.dirname(__file__), "weaviate_creds.env")
load_dotenv(env_path)

def get_weaviate_client():
    """
    Initialize and return a Weaviate client using environment variables.
    """
    weaviate_url = os.getenv("WEAVIATE_URL")
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
    print("weaviate_url ;-", weaviate_url)
    print("weaviate_api_key ;-", weaviate_api_key)

    if not weaviate_url or not weaviate_api_key:
        raise ValueError("Weaviate URL or API Key is missing. Please check your .env file.")

    # Use the new WeaviateClient connection method
    client = weaviate.connect_to_weaviate_cloud(
    cluster_url=weaviate_url,
        auth_credentials=Auth.api_key(weaviate_api_key),
    )

    return client

#insert
def store_embedding(client, file_name, embedding,code):
    """Stores a single embedding in Weaviate under a structured schema."""
    if not client.is_ready():
        print("Weaviate client is not ready.")
        return

    try:
        # Get the collection
        collection = client.collections.get("AppCRUDVectorEmbeddings")
        if not isinstance(code, str):
            code = str(code)
        

        # Prepare the properties
        properties = {
            "file_name": file_name,
            "code":str(code),
            "embedding":embedding.tolist()  
        }
        
        # ✅ Ensure embedding is a plain list
        collection.data.insert(properties)
        print(f"Embedding for {file_name} stored successfully.")

    except Exception as e:
        print(f"Error storing embedding in Weaviate: {e}")
    finally:
        if hasattr(client, 'close'):
            client.close()
#get similar search with collection name
def retrieve_framework_context(client,user_code_embedding, top_k=3):
    try:
        jeopardy = client.collections.get("AppCRUDVectorEmbeddings")
        response = jeopardy.query.near_vector(
        near_vector=user_code_embedding,
        limit=top_k,
        return_metadata=MetadataQuery(distance=True)
        )
        return response.objects
    except Exception as e:
        print(f"Error retrieving framework context: {e}")
        return []
    finally:
        if hasattr(client, 'close'):
            client.close()

#retrive optimized code
def generate_code_suggestion(user_code: str, user_prompt: str, 
retrieved_context: list[str]) -> str:
    try:
    # Construct prompt
        framework_snippets = "\n\n".join([f"{i+1}.\n{item.properties['content']}" for i, item in enumerate(retrieved_context)])
    
        user_message = f"""The user has submitted the following C# code with the instruction: "{user_prompt}"

    User Code:
    {user_code}

    Relevant Code Snippets from Internal Framework:
    {framework_snippets}

    Now provide the improved or fixed version of the user code based on the framework patterns.
    Return only the modified code.
    """

        payload = {
            "model": "mistral",
            "messages": [
                {
                    "role": "system",
                    "content": "You are an AI assistant that specializes in optimizing and debugging C# code according to internal framework patterns."
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            "stream": False
        }

        response = requests.post("http://localhost:11434/api/chat", json=payload)

        if response.status_code == 200:
            return response.json()["message"]["content"]
        else:
            raise Exception(f"Failed to generate response: {response.text}")
    except Exception as e:
        print(f"Error Occured while optimize the code {e}")
    
def upsert_with_uuid(client, _id, collection_name,new_file_name,is_modified,is_deleted):
    try:
        collection = client.collections.get(collection_name)
        if(is_modified):
            collection.data.replace(
                uuid=_id,
                properties={"file_name": new_file_name}
            )
            print("Update successful")
        elif(is_deleted):
           collection.data.delete_many(
            where=Filter.by_property("file_name").equal(new_file_name)
        )
        print("Delete successful")
    except Exception as e:
        print(f"Update throws error: {e}")
    finally:
        client.close()    
        