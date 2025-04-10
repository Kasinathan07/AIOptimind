import os
from ollama_config import get_embedding
from weaviate_config import store_embedding,get_weaviate_client,retrieve_framework_context,generate_code_suggestion,upsert_with_uuid
from lxml import etree

def get_cs_files_from_csproj(csproj_path,target_filenames):
    tree = etree.parse(csproj_path)
    root = tree.getroot()
    
     # Get XML namespace (if present)
    namespace = root.tag.split('}')[0].strip('{') if '}' in root.tag else ''
    ns = {'ns': namespace} if namespace else {}  # Create namespace dictionary

        
    target_filenames = {filename.lower() for filename in target_filenames}
    # Extract all included .cs files
    cs_files = []
    for item_group in root.findall(".//ns:ItemGroup", ns):  # Use namespace
        for compile_item in item_group.findall("ns:Compile", ns):  # Use namespace
            if 'Include' in compile_item.attrib:
                # cs_files.append(compile_item.attrib['Include'])
                file_path = compile_item.attrib['Include']
                if file_path.lower().split('\\')[-1] in target_filenames:  # Extract filename from path
                    cs_files.append(file_path)
    
    return cs_files

def clean_filename(filename):
    """Clean filename to make it Weaviate-compatible."""
    # Remove file extension
    name = os.path.splitext(filename)[0]
    # Replace invalid characters with underscores
    clean_name = ''.join(c if c.isalnum() else '_' for c in name)
    # Ensure it starts with a letter or underscore
    if clean_name[0].isdigit():
        clean_name = f"file_{clean_name}"
    return clean_name

def read_cs_files(csproj_dir, cs_files):
    """Read C# files and return cleaned code snippets."""
    code_snippets = {}
    
    for cs_file in cs_files:
        file_path = os.path.join(csproj_dir, cs_file)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    # Read the content
                    content = f.read()
                    # Clean the filename for Weaviate
                    clean_name = clean_filename(cs_file)
                    # Store with clean name and original path
                    code_snippets[clean_name] = {
                        "original_path": cs_file,
                        "content": content.strip()  # Remove leading/trailing whitespace
                    }
            except Exception as e:
                print(f"Error reading file {cs_file}: {e}")
    
    return code_snippets

def retrieve_and_optimize_code():
    #get user code
    # user_filePath = input("Enter the path of the file :- ")
    # user_code = input("Enter the class name :- ")
    # csproj_dirs = os.path.dirname(user_filePath)
    # user_code_content = read_cs_files(csproj_dirs,user_code)
    #get client
    client = get_weaviate_client()
    user_code_content = input("Enter the C# code you want to optimize or fix:\n")
    user_instruction = input("What do you want the AI to do with the code? (e.g., Optimize it, Fix bugs, etc.):\n")
    #print(user_code_content)
    #user Code embedding
    user_code_embedding = get_embedding(user_code_content)
    #Retrive Code with weviate RAG   
    retrieved_code =retrieve_framework_context(client,user_code_embedding)
    print(retrieved_code)
    result = generate_code_suggestion(user_code_content, user_instruction, retrieved_code)
    print("\n🛠️ Optimized/Fix Code:\n")
    print(result)

def Update_value():
    client = get_weaviate_client()
    obj_id = "6b83accc-008b-4274-843b-d035c0b2506c"
    class_name = "AppCRUDVectorEmbeddings"
    newValue = "AppCrud"
    upsert_with_uuid(client, obj_id, class_name, newValue,False,True)

def main():
    CsProj_Path = "D:\ofc\DEV\cube.fx\Cube.Fx\Cube.Fx.Repo\Cube.Fx.Repo.csproj"
    print(CsProj_Path)
    target_files = ["APPCrud.cs"] 
    csproj_dir = os.path.dirname(CsProj_Path)
    resutl = get_cs_files_from_csproj(CsProj_Path,target_files)
    print(resutl)
    codeResult = read_cs_files(csproj_dir,resutl)
    print(codeResult)
    # Generate embedding using Mistral via Ollama
    embedding = get_embedding(codeResult)
    print(embedding)
    print(type(embedding), embedding.shape)
    #get client
    client = get_weaviate_client()
    #if embedding is not None:
    store_embedding(client,"APPCrud",embedding,codeResult)
    #store_raw_code(client,codeResult)
    print("stored embedding successfully")    


if __name__ == "__main__":
    retrieve_and_optimize_code()
    #Update_value()
    #main()
    # retrieve_and_optimize_code()  # Comment this out if you just want to test retrieval
   # retrieve_code_example()
