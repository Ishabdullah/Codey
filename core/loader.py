from utils.logger import success, error
from utils.config import MODEL_PATH
from pathlib import Path
import os

LLAMA_SERVER = str(Path.home() / "llama.cpp/build/bin/llama-server")

def load_model():
    binary = Path(LLAMA_SERVER)
    if not binary.exists():
        error(f"llama-server not found: {LLAMA_SERVER}")
        return None
    if not MODEL_PATH.exists():
        error(f"Model not found: {MODEL_PATH}")
        return None
    success(f"Binary : {LLAMA_SERVER}")
    success(f"Model  : {MODEL_PATH}")
    return True

def unload_model():
    from core.inference import stop_server
    stop_server()
