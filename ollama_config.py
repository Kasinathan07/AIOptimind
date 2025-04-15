from sentence_transformers import SentenceTransformer
import numpy as np

# Load the HuggingFace embedding model
model = SentenceTransformer("intfloat/e5-small-v2")

def get_embedding(text):
    """Get embedding using intfloat/e5-small-v2 model.

    Args:
        text: Can be:
            - str: Direct text to embed
            - list: List of texts to join
            - tuple: (file_path, content) pair

    Returns:
        numpy.ndarray: The embedding vector
    """
    # Handle different input types
    if isinstance(text, tuple):
        _, prompt = text
    elif isinstance(text, list):
        prompt = " ".join(str(item) for item in text)
    else:
        prompt = str(text)

    # Clean and prepare prompt
    prompt = prompt.replace('\ufeff', '').strip()

    # Add prefix for E5 model (important for correct embedding behavior)
    formatted_text = f"passage: {prompt}"

    # Get embedding and convert to numpy array
    embedding = model.encode(formatted_text)
    return np.array(embedding, dtype=np.float32)
