from pathlib import Path
from utils.config import AGENT_CONFIG
from utils.logger import warning

def read_file(path: str) -> str:
    """Read a file and return its contents as string."""
    try:
        p = Path(path).expanduser().resolve()
        return p.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return f"[ERROR] File not found: {path}"
    except Exception as e:
        return f"[ERROR] Could not read {path}: {e}"

def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent dirs as needed."""
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {p}"
    except Exception as e:
        return f"[ERROR] Could not write {path}: {e}"

def append_file(path: str, content: str) -> str:
    try:
        p = Path(path).expanduser().resolve()
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended {len(content)} chars to {p}"
    except Exception as e:
        return f"[ERROR] {e}"

def list_dir(path: str = ".") -> str:
    """List directory contents."""
    try:
        p = Path(path).expanduser().resolve()
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = []
        for e in entries:
            prefix = "📄" if e.is_file() else "📁"
            lines.append(f"{prefix} {e.name}")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"[ERROR] {e}"

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4

def budget_file_context(files: list[str]) -> str:
    """Build a file context block, respecting token budget."""
    budget = AGENT_CONFIG["token_budget"]
    blocks = []
    used = 0
    for path in files:
        content = read_file(path)
        tokens = estimate_tokens(content)
        if used + tokens > budget:
            warning(f"Token budget reached, skipping {path}")
            blocks.append(f"# FILE: {path}\n[TRUNCATED — too large for context]")
            continue
        blocks.append(f"# FILE: {path}\n```\n{content}\n```")
        used += tokens
    return "\n\n".join(blocks)
