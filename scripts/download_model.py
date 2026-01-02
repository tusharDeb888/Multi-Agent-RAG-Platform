import os
import sys
from huggingface_hub import hf_hub_download

def download_model():
    repo_id = "unsloth/Llama-3.2-3B-Instruct-GGUF"
    filename = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    local_dir = "./models"
    local_path = os.path.join(local_dir, "llama-3.2-3b-instruct-quantized.gguf")
    
    print(f"Downloading {filename} from {repo_id}...")
    os.makedirs(local_dir, exist_ok=True)
    
    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=local_dir,
            local_dir_use_symlinks=False
        )
        
        # Rename to match config
        if os.path.exists(local_path):
            os.remove(local_path)
        os.rename(path, local_path)
        
        print(f"Model downloaded successfully to {local_path}")
        
    except Exception as e:
        print(f"Error downloading model: {e}")

if __name__ == "__main__":
    download_model()
