import os
from lxml import etree
from utils import clean_filename

def get_cs_files_from_csproj(csproj_path, target_filenames):
    if not os.path.exists(csproj_path):
        print(f"❌ Project file not found at: {csproj_path}")
        return []

    tree = etree.parse(csproj_path)
    root = tree.getroot()
    ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}

    target_filenames = {f.lower() for f in target_filenames}
    cs_files = []

    for item_group in root.findall(".//ns:ItemGroup", ns):
        for compile_item in item_group.findall("ns:Compile", ns):
            if 'Include' in compile_item.attrib:
                file_path = compile_item.attrib['Include']
                if file_path.lower().split('\\')[-1] in target_filenames:
                    cs_files.append(file_path)
    return cs_files

def read_cs_files(csproj_dir, cs_files):
    code_snippets = {}
    for cs_file in cs_files:
        file_path = os.path.join(csproj_dir, cs_file)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                clean_name = clean_filename(cs_file)
                code_snippets[clean_name] = {
                    "original_path": cs_file,
                    "content": content
                }
        else:
            print(f"⚠️ Skipped missing file: {cs_file}")
    return code_snippets

# ✅ Wrapper to be used in agent_runner.py
def parse_csproj_and_extract_code(csproj_path, target_filenames):
    csproj_dir = os.path.dirname(csproj_path)
    cs_files = get_cs_files_from_csproj(csproj_path, target_filenames)
    return {fname: data["content"] for fname, data in read_cs_files(csproj_dir, cs_files).items()}
