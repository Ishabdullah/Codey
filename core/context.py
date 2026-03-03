"""
File context management — inject file contents into conversation.
Supports single files, globs, and whole directories.
"""
import re
import os
import glob
from pathlib import Path
from utils.logger import success, warning, info

_loaded_files: dict[str, str] = {}

def load_file(path: str) -> str:
    """Load a single file into context."""
    p = Path(path).expanduser()
    if not p.exists():
        p = Path(os.getcwd()) / path
    if not p.exists():
        warning(f"File not found: {path}")
        return f"[ERROR] File not found: {path}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        key = str(p.resolve())
        _loaded_files[key] = content
        success(f"Loaded: {p.name} ({len(content)} chars)")
        return content
    except Exception as e:
        return f"[ERROR] {e}"

def load_glob(pattern: str) -> list[str]:
    """
    Load all files matching a glob pattern.
    e.g. "*.py", "core/*.py", "**/*.py"
    Returns list of loaded paths.
    """
    matches = glob.glob(pattern, recursive=True)
    if not matches:
        warning(f"No files matched: {pattern}")
        return []
    loaded = []
    for m in matches:
        p = Path(m)
        if p.is_file():
            result = load_file(str(p))
            if not result.startswith("[ERROR]"):
                loaded.append(str(p))
    if loaded:
        info(f"Loaded {len(loaded)} files matching '{pattern}'")
    return loaded

def load_directory(path: str, extensions: list[str] = None, max_files: int = 10) -> list[str]:
    """
    Load all code files from a directory.
    Default extensions: .py .js .ts .sh .md .json .yaml .toml
    """
    default_exts = {".py", ".js", ".ts", ".sh", ".md", ".json",
                    ".yaml", ".yml", ".toml", ".txt", ".html", ".css",
                    ".c", ".cpp", ".h", ".rs", ".go"}
    exts = set(extensions) if extensions else default_exts
    p = Path(path).expanduser()
    if not p.is_dir():
        warning(f"Not a directory: {path}")
        return []

    files = sorted([
        f for f in p.rglob("*")
        if f.is_file()
        and f.suffix in exts
        and not any(part.startswith(".") for part in f.parts)
        and "__pycache__" not in str(f)
    ])[:max_files]

    loaded = []
    for f in files:
        result = load_file(str(f))
        if not result.startswith("[ERROR]"):
            loaded.append(str(f))

    if loaded:
        info(f"Loaded {len(loaded)} files from {path}")
    return loaded

def unload_file(path: str):
    p = Path(path).expanduser().resolve()
    if str(p) in _loaded_files:
        del _loaded_files[str(p)]
        info(f"Unloaded: {p.name}")
    else:
        warning(f"Not loaded: {path}")

def clear_context():
    _loaded_files.clear()
    info("File context cleared.")

def list_loaded() -> list[str]:
    return list(_loaded_files.keys())

def build_file_context_block() -> str:
    if not _loaded_files:
        return ""
    blocks = []
    total_chars = 0
    limit = 6000  # ~1500 tokens max for file context
    for path, content in _loaded_files.items():
        if total_chars >= limit:
            warning(f"Context limit reached, skipping remaining files")
            break
        name = Path(path).name
        if len(content) + total_chars > limit:
            # Truncate to fit
            allowed = limit - total_chars
            content = content[:allowed] + "\n... [truncated]"
        blocks.append(f'<file path="{name}">\n{content}\n</file>')
        total_chars += len(content)
    return "\n".join(blocks)

def detect_filenames(text: str) -> list[str]:
    """Auto-detect filenames in a prompt."""
    pattern = r'(?:\.{0,2}/)?[\w\-/]+\.(?:py|js|ts|sh|json|yaml|yml|toml|txt|md|html|css|cpp|c|h|rs|go|rb|java)'
    matches = re.findall(pattern, text)
    existing = []
    for m in matches:
        p = Path(m).expanduser()
        if p.exists():
            existing.append(m)
        else:
            # Try relative to cwd
            p2 = Path(os.getcwd()) / m
            if p2.exists():
                existing.append(str(p2))
    return existing

def auto_load_from_prompt(prompt: str) -> list[str]:
    """Detect and load files mentioned in prompt."""
    found = detect_filenames(prompt)
    loaded = []
    for f in found:
        result = load_file(f)
        if not result.startswith("[ERROR]"):
            loaded.append(f)
    return loaded
