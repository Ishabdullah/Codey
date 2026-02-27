import os
from pathlib import Path

CODEY_DIR = Path(os.environ.get("CODEY_DIR", Path.home() / "codey"))
MODEL_PATH = Path(os.environ.get(
    "CODEY_MODEL",
    Path.home() / "models" / "qwen2.5-coder-7b" / "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"
))

MODEL_CONFIG = {
    "n_ctx": 1024,       # low to prevent crashes
    "n_threads": 4,
    "n_gpu_layers": 0,
    "verbose": False,
    "temperature": 0.2,
    "max_tokens": 300,
    "repeat_penalty": 1.1,
    "top_p": 0.95,
    "top_k": 40,
    "stop": ["<|im_end|>", "<|im_start|>"],
}

AGENT_CONFIG = {
    "max_steps": 6,
    "token_budget": 1000,
    "confirm_shell": True,
    "confirm_write": True,
    "history_turns": 2,
}

CODEY_VERSION = "0.1.0"
CODEY_NAME = "Codey"
