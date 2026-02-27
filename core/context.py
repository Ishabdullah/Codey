"""
File context management — inject file contents into conversation.
"""
import re
from pathlib import Path
from utils.logger import success, warning, info

# Files currently loaded into context
_loaded_files: dict[str, str] = {}

def load_file(path: str) -> str:
    """Load a file into context. Returns content or error string."""
    p = Path(path).expanduser()
    if not p.exists():
        # Try relative to cwd
        import os
        p = Path(os.getcwd()) / path
    if not p.exists():
        warning(f"File not found: {path}")
        return f"[ERROR] File not found: {path}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        _loaded_files[str(p)] = content
        success(f"Loaded: {p} ({len(content)} chars)")
        return content
    except Exception as e:
        warning(f"Could not read {path}: {e}")
        return f"[ERROR] {e}"

def unload_file(path: str):
    """Remove a file from context."""
    p = Path(path).expanduser().resolve()
    if str(p) in _loaded_files:
        del _loaded_files[str(p)]
        info(f"Unloaded: {p}")

def clear_context():
    """Remove all loaded files."""
    _loaded_files.clear()
    info("File context cleared.")

def list_loaded() -> list[str]:
    return list(_loaded_files.keys())

def build_file_context_block() -> str:
    """Build the context string injected into the system prompt."""
    if not _loaded_files:
        return ""
    blocks = []
    for path, content in _loaded_files.items():
        # Truncate large files
        if len(content) > 3000:
            content = content[:3000] + "\n... [truncated]"
        blocks.append(f'<file path="{path}">\n{content}\n</file>')
    return "\n".join(blocks)

def detect_filenames(text: str) -> list[str]:
    """
    Auto-detect filenames mentioned in a prompt.
    Matches patterns like: file.py, ./path/to/file.js, ../config.json
    """
    pattern = r'(?:\.{0,2}/)?[\w\-/]+\.(?:py|js|ts|sh|json|yaml|yml|toml|txt|md|html|css|cpp|c|h|rs|go|rb|java)'
    matches = re.findall(pattern, text)
    # Filter out things that don't actually exist
    existing = []
    for m in matches:
        p = Path(m).expanduser()
        if p.exists():
            existing.append(m)
    return existing

def auto_load_from_prompt(prompt: str) -> list[str]:
    """Detect and load any files mentioned in the prompt. Returns list of loaded paths."""
    found = detect_filenames(prompt)
    loaded = []
    for f in found:
        result = load_file(f)
        if not result.startswith("[ERROR]"):
            loaded.append(f)
    return loaded
