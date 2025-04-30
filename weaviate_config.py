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
from openai import OpenAI
from ollama_config import get_embedding  # import here to avoid circular imports
# from weaviate.classes.query import Filter  
# from weaviate.collections.classes.filters import Filter, WhereFilter
# from weaviate.collections.classes.filters import Filter as CollectionFilter, WhereFilter # Collection hybrid filters


env_path = os.path.join(os.path.dirname(__file__), "weaviate_creds.env")
load_dotenv(env_path)

USE_MANUAL_EMBEDDING = True  # Set to False to use Weaviate's default


def get_weaviate_client():
    url = os.getenv("WEAVIATE_URL")
    key = os.getenv("WEAVIATE_API_KEY")

    if not url or not key:
        raise ValueError("Weaviate URL or API Key missing.")

    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=Auth.api_key(key),
    )

    for name in ["FXCodeEmbedding", "UserCodeEmbeddings", "SnippetCodeEmbeddings","FunctionDocsEmbedding"]:
        if not client.collections.exists(name):

            if name == "FXCodeEmbedding":
                properties=[
                    Property(name="code", data_type=DataType.TEXT, vectorizePropertyName=True),
                    Property(name="file_name", data_type=DataType.TEXT, vectorizePropertyName=False),
                    Property(name="code_hash", data_type=DataType.TEXT, vectorizePropertyName=False)
                ]
            elif name == "SnippetCodeEmbeddings":
                properties=[
                    Property(name="code", data_type=DataType.TEXT, vectorizePropertyName=True),
                    Property(name="file_name", data_type=DataType.TEXT, vectorizePropertyName=False)
                ]
            elif name == "UserCodeEmbeddings":
                properties=[
                    Property(name="code", data_type=DataType.TEXT, vectorizePropertyName=True),
                    Property(name="code_id", data_type=DataType.TEXT, vectorizePropertyName=False)
                ]
            elif name == "FunctionDocsEmbedding":
                properties=[
                    Property(name="text", data_type=DataType.TEXT, vectorizePropertyName=True),
                    Property(name="file_name", data_type=DataType.TEXT, vectorizePropertyName=False),
                    Property(name="code_hash", data_type=DataType.TEXT, vectorizePropertyName=False),
                    Property(name="code_id", data_type=DataType.TEXT, vectorizePropertyName=False),
                    Property(name="user_name", data_type=DataType.TEXT, vectorizePropertyName=False),

                ]

            client.collections.create(
                name=name,
                vectorizer_config=Configure.Vectorizer.text2vec_weaviate(),
                properties=properties
            )

    return client

def store_framework_embedding(client, file_name, code_str, tablename,user_name=None):
    if tablename == "FunctionDocsEmbedding":
        return_state,code_id = store_document_embedding(client, file_name, code_str, tablename,user_name)
        return return_state,code_id
    else:
        return_state = _store_embedding(client, file_name, code_str,tablename)
    return return_state,None

# def store_user_embedding(client, code_str):
#     collection = client.collections.get("UserCodeEmbeddings")
#     code_id = str(uuid.uuid4())
#     properties = {
#         "code": code_str,
#         "code_id": code_id
#     }

#     collection.data.insert(uuid=code_id, properties=properties)
#     time.sleep(2)  # Allow time for vectorization

#     # Verify vector exists using fetch_object_by_id
#     result = collection.query.fetch_object_by_id(code_id, include_vector=True)
#     if not result or not result.vector:
#         raise ValueError("❌ Vector not generated for user code")

#     print(f"✅ Stored user code with ID: {code_id}")
#     return code_id

def store_user_embedding(client, code_str):    
    collection = client.collections.get("UserCodeEmbeddings")
    code_id = str(uuid.uuid4())

    properties = {
        "code": code_str,
        "code_id": code_id,
        "embedding_source": "Hugging Face" if USE_MANUAL_EMBEDDING else "weaviate"
    }

    if USE_MANUAL_EMBEDDING:
        vector = get_embedding(code_str).tolist()
        collection.data.insert(uuid=code_id, properties=properties, vector=vector)
        print(f"✅inside manual embedding")
    else:
        collection.data.insert(uuid=code_id, properties=properties)
        print(f"✅inside weaviate embedding")
    time.sleep(2)  # Optional: give Weaviate time to vectorize if using automatic
    
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

# def _store_embedding(client, file_name, code_str, collection_name):
#     collection = client.collections.get(collection_name)
#     code_hash = compute_hash(code_str)

#     result = collection.query.fetch_objects(
#         filters=Filter.by_property("file_name").equal(file_name)
#     )

#     if result.objects:
#         obj = result.objects[0]
#         if obj.properties.get("code_hash") == code_hash:
#             print(f"🟡 {file_name} unchanged. Skipping.")
#             return
#         else:
#             print(f"🟠 {file_name} changed. Updating.")
#             collection.data.delete_many(where=Filter.by_property("file_name").equal(file_name))

#     properties = {
#         "file_name": file_name,
#         "code": code_str,
#         "code_hash": code_hash
#     }
#     collection.data.insert(properties=properties)
#     print(f"✅ {file_name} stored in {collection_name}.")

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
            return "unchanged"
        else:
            print(f"🟠 {file_name} changed. Updating.")
            collection.data.delete_many(where=Filter.by_property("file_name").equal(file_name))
            result_state = "changed"
    else:
        result_state = "new"

    properties = {
        "file_name": file_name,
        "code": code_str,
        "code_hash": code_hash,
        "embedding_source": "Hugging Face" if USE_MANUAL_EMBEDDING else "weaviate"
    }

    if USE_MANUAL_EMBEDDING:
        vector = get_embedding(code_str).tolist()
        collection.data.insert(properties=properties, vector=vector)
        print(f"✅ inside manual embedding")
    else:
        collection.data.insert(properties=properties)
        print(f"✅ inside weaviate embedding")

    print(f"✅ {file_name} stored in {collection_name}.")
    return result_state

def store_document_embedding(client, file_name, doc_text,tablename,user_name):
    """
    Stores a document embedding (e.g., PDF or DOCX converted to plain text) to the 'FunctionDocsEmbedding' collection in Weaviate.

    Parameters:
    - client: weaviate client connection.
    - file_name: Name of the original document file (e.g., "HRPolicy.pdf").
    - doc_text: The extracted text content of the document.
    """
    collection = client.collections.get(tablename)
    code_hash = compute_hash(doc_text)


    match_filter = Filter.by_property("file_name").equal(file_name) & Filter.by_property("user_name").equal(user_name)

    result = collection.query.fetch_objects(filters=match_filter)


    if result.objects:
        obj = result.objects[0]
        if obj.properties.get("code_hash") == code_hash:
            print(f"🟡 {file_name} unchanged. Skipping.")
            code_id = obj.properties.get("code_id")
            return "unchanged",code_id
        else:
            print(f"🟠 {file_name} changed. Updating.")
            collection.data.delete_many(where=match_filter)
            result_state = "changed"
    else:
        result_state = "new"

    code_id = str(uuid.uuid4())     

    properties = {
        "file_name": file_name,
        "text": doc_text,
        "code_hash": code_hash,
        "code_id": code_id,
        "user_name": user_name,
        "embedding_source": "Hugging Face" if USE_MANUAL_EMBEDDING else "weaviate"
    }

    if USE_MANUAL_EMBEDDING:    
        vector = get_embedding(doc_text).tolist()
        collection.data.insert(uuid=code_id,properties=properties, vector=vector)
        print(f"✅ Document embedding inserted manually.")
    else:
        collection.data.insert(properties=properties)
        print(f"✅ Document embedding inserted via Weaviate vectorizer.")
    
    print(f"✅ {file_name} stored in {doc_text}.")
    return result_state,code_id

# def retrieve_framework_context(client, user_vector,user_query_text, top_k=5):
#     if not user_vector:
#         raise ValueError("❌ Cannot retrieve context - user vector is empty")
#     if not user_query_text:
#         raise ValueError("❌ Cannot retrieve context - user query text is empty")

#     fx_collection = client.collections.get("FXCodeEmbedding")
    
#     # fx_results = fx_collection.query.hybrid(
#     #     query=user_query_text,        # 🔥 Text-based part
#     #     vector=user_vector,           # 🔥 Vector-based part
#     #     alpha=0.5,                    # 🔥 0.5 = balance text and vector equally (you can tune this)
#     #     limit=top_k,
#     #     return_metadata=MetadataQuery(distance=True, score=True)  # Also get hybrid score if you want
#     # )
# # plain dict instead of WhereFilter
#     # where_clause = {
#     #     "path":       ["file_name"],
#     #     "operator":   "Equal",
#     #     "valueText":"APPCrud"     # ← your user_filename
#     # }
#     where_clause = WhereFilter(
#     path=["file_name"],  # Name of the property
#     operator="Equal",    # Comparison operator
#     value_text="APPCrud" # Value for comparison (string in this case)
# )

#     fx_results = fx_collection.query.hybrid(
#         query=user_query_text,
#         vector=user_vector,
#         alpha=0.5,
#         limit=top_k,
#         # where=where_clause,
#         # filters=Filter(where=where_clause),
#         filters=CollectionFilter(where=where_clause),          
#         # filters=Filter(where=where_clause),                  # ← simple dict!
#         return_metadata=MetadataQuery(distance=True, score=True)
#     )
#     combined_results = fx_results.objects 
#     return combined_results
#     fx_results = fx_collection.query.hybrid(
#     query=user_query_text,
#     vector=user_vector,
#     alpha=0.5,
#     limit=top_k,
#     return_metadata=MetadataQuery(distance=True, score=True)
# )

#     # Manual filtering based on 'file_name'
#     combined_results = [
#         obj for obj in fx_results.objects
#         if obj.properties.get('file_name') == 'APPCrud'
#     ]

#     return combined_results

# def generate_code_suggestion(user_code, user_prompt, retrieved_context):
    # Extract keywords from the user prompt
    

    # Filter the retrieved context based on keywords
    filtered_snippets = [
        f"{i+1}.\n{obj.properties['code']}"
        for i, obj in enumerate(retrieved_context)
        
    ]

    # Join the filtered snippets
    snippets = "\n\n".join(filtered_snippets)

    # Construct the prompt
    prompt = f"""
The user has submitted this C# code:

{user_code}

Instruction: Please improve the code based on the following requirement: "{user_prompt}"

Here are some relevant framework keywords:

{snippets}

Please optimize the user's code using the above context. Focus on enhancing internal method usage and code efficiency. 
Only return the updated C# code—no explanation or extra text.
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

def retrieve_framework_context(client, user_vector,user_prompt, top_k=5):
    if not user_vector:
        raise ValueError("❌ Cannot retrieve context - user vector is empty")

    fx_collection = client.collections.get("FXCodeEmbedding")
    snippet_collection = client.collections.get("SnippetCodeEmbeddings")
    fun_collection = client.collections.get("FunctionDocsEmbedding")

    # file_filter = Filter.by_property("file_name").equal("AppCRUD")
    fx_results = fx_collection.query.near_vector(
        near_vector=user_vector,
        limit=top_k,
        # filters=file_filter,
        return_metadata=MetadataQuery(distance=True)
    )
    
    # fx_results = fx_collection.query.hybrid(
    #     query=user_prompt,               # 👈 use user text (e.g., "optimize exception handling")
    #     vector=user_vector,              # 👈 use vector similarity
    #     alpha=0.4,                       # 0.5 = balance between vector & keyword
    #     limit=top_k,
    #     filters=file_filter,
    #     return_metadata=MetadataQuery(distance=True)
    # )

    # snippet_results = snippet_collection.query.near_vector(
    #     near_vector=user_vector,
    #     limit=top_k,
    #     return_metadata=MetadataQuery(distance=True)
    # )

    # fun_results = fun_collection.query.near_vector(
    #     near_vector=user_vector,
    #     limit=top_k,
    #     return_metadata=MetadataQuery(distance=True)
    # )
    # Combine results from both collections
    combined_results = fx_results.objects 
    return combined_results

def retrieve_Fun_framework_context(client, user_vector, top_k=5):
    if not user_vector:
        raise ValueError("❌ Cannot retrieve context - user vector is empty")

    
    fx_collection = client.collections.get("FXCodeEmbedding")
    snippet_collection = client.collections.get("SnippetCodeEmbeddings")
    fun_collection = client.collections.get("FunctionDocsEmbedding")
     # 🔥 HARD-CODED list of allowed files
    allowed_files = ["JobHeader_Save_environment.docx","JobHeader_Save_environment1.docx"]

    

    # Build a dynamic filter based on file names
    # where_clause = WhereFilter(
    #     path=["file_name"],
    #     operator="Or",
    #     operands=[
    #         WhereFilter(
    #             path=["file_name"],
    #             operator="Equal",
    #             value_text=fname
    #         ) for fname in allowed_files
    #     ]
    # )
    # filters = Filter(where=where_clause)

    # where_clause = {
    #     "operator": "Or",
    #     "operands": [
    #         {
    #             "path": ["file_name"],
    #             "operator": "Equal",
    #             "valueText": fname
    #         }
    #         for fname in allowed_files
    #     ]
    # }
    # filters = {"where": where_clause}
     
    # filters = Filter.by_property("file_name").equal_any(allowed_files)

    # fx_results = fx_collection.query.near_vector(
    #     near_vector=user_vector,
    #     limit=top_k,
    #     return_metadata=MetadataQuery(distance=True)
    # )
    # filters = {
    #     "operator": "Or",
    #     "operands": [
    #         {
    #             "path": ["file_name"],
    #             "operator": "Equal",
    #             "valueText": fname
    #         }
    #         for fname in allowed_files
    #     ]
    # }
        # 🔥 Create Filter correctly
    # filters = Filter(
    #     operator="Or",
    #     operands=[
    #         Filter.by_property("file_name").equal(fname) for fname in allowed_files
    #     ]
    # )
    # Start with the first condition
    file_filter = Filter.by_property("file_name").equal(allowed_files[0])

    # For each additional file name, create an OR condition
    for file in allowed_files[1:]:
        file_filter = file_filter | Filter.by_property("file_name").equal(file)
    
    fx_results = fx_collection.query.near_vector(
        near_vector=user_vector,
        limit=top_k,
        return_metadata=MetadataQuery(distance=True)
    )

    

    fun_results = fun_collection.query.near_vector(
        near_vector=user_vector,
        limit=top_k,
        #filters=Filter.by_property("file_name").equal_any(allowed_files),
        filters=file_filter,
        return_metadata=MetadataQuery(distance=True)
    )
    # Combine results from both collections
    combined_results = fx_results.objects +fun_results.objects
    return combined_results


# def generate_code_suggestion(user_code, user_prompt, retrieved_context):
    # Extract keywords from the user prompt
    

    # Filter the retrieved context based on keywords
    filtered_snippets = [
        f"{i+1}.\n{obj.properties['code']}"
        for i, obj in enumerate(retrieved_context)
        
    ]

    # Join the filtered snippets
    snippets = "\n\n".join(filtered_snippets)

    # Construct the prompt
    prompt = f"""
The user has submitted this C# code:

{user_code}

Instruction: Please improve the code based on the following requirement: "{user_prompt}"

Here are some relevant framework keywords:

{snippets}

Please optimize the user's code using the above context. Focus on enhancing internal method usage and code efficiency. 
Only return the updated C# code—no explanation or extra text.
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


    
IS_OLLAMA = False  # Set to True to use Ollama (Mistral), False to use OpenAI

def generate_code_suggestion(user_code_, userprompt_, retrievedcontext_,state):
    Notes = "NOTE:- While Handling the exceptions Use the internal framework Logging Service to log exceptions instead of using 'throw new'." 
    # + "\n" + "2. If the user Prompt Prefers any kind of Transaction type. Please go on with the Internal Framework Logic since we have already predefined methods in APPCRUD.If that method is not applicable to the user case go with your suggestions";
    
    snippets = [
        f"{i+1}.\nCode:\n{obj.properties['code']}"
        for i, obj in enumerate(retrievedcontext_)
        if 'code' in obj.properties
]

    user_message = f"""The user has submitted the following C# code with the instruction: "{userprompt_}"

User Code:
{user_code_}

Here are some framework patterns:

{snippets}


"""
    
    # Ensure the flags are initialized before usage
    if "flags" not in state["inputs"]:
       state["inputs"]["flags"] = {"test": False, "optimize": False, "bug": False}

    # Determine AI role based on selected flag
    if state["inputs"]["flags"]["test"] or state["inputs"]["FnRadio"]["test"]:
        role = "You are an AI agent that specializes in writing test cases for C# code according to internal framework patterns. Only return the testcases with explanation." + "\n" + Notes
    elif state["inputs"]["flags"]["optimize"]or state["inputs"]["FnRadio"]["generate"]:
         role = "You are an AI agent that specializes in generating the c# code, optimizing and debugging C# code by using only our internal framework patterns.Only return the updated C# code with explanation." + "\n" + Notes 
    elif state["inputs"]["flags"]["bug"]:
        role = "You are an AI agent that specializes in identifying and fixing bugs in C# code according to internal framework patterns. Only return the bugs and explanation." + "\n" + Notes
    elif state["inputs"]["FnRadio"]["curd"]:
         role = "You are an AI agent that specializes in Writing a CRUD Operation from the Functional Documents provided by user who writes according to internal framework patterns.Only return the updated C# code with explanation." + "\n" + Notes
    if IS_OLLAMA:
        # Use Ollama (Mistral) locally
        response = requests.post("http://localhost:11434/api/chat", json={
            "model": "mistral",
            "messages": [
                {"role": "system", "content": role},
                {"role": "user", "content": user_message}
            ],
            "stream": False
        })

        if response.status_code == 200:
            content = response.json()["message"]["content"]
            print("Message content:\n", content)
            return content, None
        else:
            raise Exception(f"Failed to generate suggestion via Ollama: {response.text}")
    else:
        # Use OpenAI API (GPT-4o mini)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": role
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        message_content = response.choices[0].message.content
        token_usage = response.usage
        print("Message content:\n", message_content)
        print("\nToken usage:", token_usage)
        return message_content, token_usage

def generate_FN_code_Testcase_suggestion(user_code_, userprompt_, retrievedcontext_,state):

    # Notes = "NOTE:- While Handling the exceptions Use the internal framework Logging Service to log exceptions instead of using 'throw new'."
    Notes = "NOTE:- Focus on internal framework practices. Be clear and detailed in your suggestions."


    snippets = [
    f"{i+1}.\nCode:\n{obj.properties.get('code', '[No code available]')}\nText:\n{obj.properties.get('text', '[No text available]')}"
    for i, obj in enumerate(retrievedcontext_)
    if 'code' in obj.properties or 'text' in obj.properties
]

    user_message = f"""The user has provided the following functional document with the instruction: "{userprompt_}"

Document Text:
{user_code_}

Relevant Framework Context:

{snippets}
"""
    
    # Ensure the flags are initialized before usage
    if "FnRadio" not in state["inputs"]:
       state["inputs"]["FnRadio"] = {"test": False, "generate": False, "curd": False}

    # Determine AI role based on selected flag
    if state["inputs"]["FnRadio"]["test"]:
        role = "You are an AI agent that specializes in writing test cases for  uploaded function document based on internal functional patterns. Only return the testcases with explanation." + "\n" + Notes
    elif state["inputs"]["FnRadio"]["generate"]:
         role = "You are an AI agent that specializes in generation the C# code for the functional document provided by user and based on the internal framework patterns.Only return the updated C# code with explanation." + "\n" + Notes
    elif state["inputs"]["FnRadio"]["curd"]:
        role = "You are an AI agent that specializes in writing a CRUD operation in C# according to internal framework patterns. Only return the updated C# code with explanation." + "\n" + Notes
    if IS_OLLAMA:
        # Use Ollama (Mistral) locally
        response = requests.post("http://localhost:11434/api/chat", json={
            "model": "mistral",
            "messages": [
                {"role": "system", "content": role},
                {"role": "user", "content": user_message}
            ],
            "stream": False
        })

        if response.status_code == 200:
            content = response.json()["message"]["content"]
            print("Message content:\n", content)
            return content, None
        else:
            raise Exception(f"Failed to generate suggestion via Ollama: {response.text}")
    else:
        # Use OpenAI API (GPT-4o mini)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": role
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        message_content = response.choices[0].message.content
        token_usage = response.usage
        print("Message content:\n", message_content)
        print("\nToken usage:", token_usage)
        return message_content, token_usage

def SuggestFxCode_Based_on_user_input(User_Promt, retrievedcontext_):
    # Notes = "NOTE:- While Handling the exceptions Use the internal framework Logging Service to log exceptions instead of using 'throw new'."
    #Notes = "NOTE:- Focus on internal framework practices. Be clear and detailed in your suggestions.and return the correct framework pattern that user asked for."

    snippets = [
    f"{i+1}.\nCode:\n{obj.properties['code']}"
    for i, obj in enumerate(retrievedcontext_)
    if 'code' in obj.properties
]
    user_message = f"""The user has Requested to Get the instruction: "{User_Promt}"
    Here are some framework patterns:

{snippets}


"""
    role = "You are an AI agent specialized in my internal framework. Your knowledge is based entirely on the internal framework you were trained with. you should focus only on the user question and return the exact code avaiable in the framework or Just List out the method name avaiable in the framework code which user asked for.Don't search on the entire framework code. Just target on the specific file user asked for."
    # Use OpenAI API (GPT-4o mini)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": role
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

    message_content = response.choices[0].message.content
    token_usage = response.usage
    print("Message content:\n", message_content)
    print("\nToken usage:", token_usage)
    return message_content, token_usage    
