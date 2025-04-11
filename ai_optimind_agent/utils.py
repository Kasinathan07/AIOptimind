import hashlib
import os

def compute_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def clean_filename(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    clean = ''.join(c if c.isalnum() else '_' for c in name)
    return f"file_{clean}" if clean[0].isdigit() else clean
