"""
Thin wrappers around file_utils that add confirmation for writes.
"""
from utils.file_utils import read_file, write_file, append_file, list_dir
from utils.logger import confirm as ask_confirm, warning
from utils.config import AGENT_CONFIG

def tool_read_file(path: str) -> str:
    return read_file(path)

def tool_write_file(path: str, content: str) -> str:
    if AGENT_CONFIG["confirm_write"]:
        preview = content[:200] + ("..." if len(content) > 200 else "")
        warning(f"About to write to: {path}")
        print(f"Preview:\n{preview}")
        if not ask_confirm("Confirm write?"):
            return "[CANCELLED] Write cancelled by user."
    return write_file(path, content)

def tool_append_file(path: str, content: str) -> str:
    if AGENT_CONFIG["confirm_write"]:
        if not ask_confirm(f"Append to {path}?"):
            return "[CANCELLED] Append cancelled by user."
    return append_file(path, content)

def tool_list_dir(path: str = ".") -> str:
    return list_dir(path)
