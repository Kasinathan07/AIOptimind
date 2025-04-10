import requests
import numpy as np

def get_embedding(text):
    """Get embedding from Ollama API.
    
    Args:
        text: Can be:
            - str: Direct text to embed
            - list: List of texts to join
            - tuple: (file_path, content) pair
    
    Returns:
        numpy.ndarray: The embedding vector
    """
    # Ollama API endpoint for embeddings
    url = "http://localhost:11434/api/embeddings"
    
    # Handle different input types
    if isinstance(text, tuple):
        # If it's a tuple (file_path, content), use the content part
        _, prompt = text
    elif isinstance(text, list):
        # If text is a list, join it into a single string
        prompt = " ".join(str(item) for item in text)
    else:
        # Convert to string if it's not already
        prompt = str(text)
    
    # Clean the prompt - remove BOM and normalize newlines
    prompt = prompt.replace('\ufeff', '')  # Remove BOM if present
    prompt = prompt.strip()  # Remove leading/trailing whitespace
    
    # Request payload
    payload = {
        "model": "mistral",  # Using mistral for better efficiency
        "prompt": prompt
    }
    
    # Make the API request
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        # Convert to numpy array and ensure it's float32
        embedding = np.array(response.json()["embedding"], dtype=np.float32)
        return embedding
    else:
        raise Exception(f"Failed to get embedding: {response.text}")