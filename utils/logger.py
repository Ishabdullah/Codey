import sys
from rich.console import Console
from rich.theme import Theme

_theme = Theme({
    "info":    "bold cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error":   "bold red",
    "tool":    "bold magenta",
    "think":   "dim italic white",
    "user":    "bold blue",
})

console = Console(theme=_theme, highlight=False)

def info(msg):    console.print(f"[info]ℹ  {msg}[/info]")
def success(msg): console.print(f"[success]✓  {msg}[/success]")
def warning(msg): console.print(f"[warning]⚠  {msg}[/warning]")
def error(msg):   console.print(f"[error]✗  {msg}[/error]")
def think(msg):   console.print(f"[think]💭 {msg}[/think]")

def tool_call(name, args):
    console.print(f"[tool]🔧 TOOL [{name}][/tool]")

def tool_result(result):
    preview = str(result)[:200]
    console.print(f"[success]   ↳ {preview}[/success]")

def separator():
    console.rule(style="dim")

def confirm(question) -> bool:
    """Keep asking until we get a real y or n — never auto-cancel."""
    sys.stdout.flush()
    sys.stderr.flush()
    while True:
        try:
            ans = input(f"\n⚠  {question} [y/N]: ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", ""):
                # Only accept empty as No if it was a deliberate Enter
                # Re-prompt if stdin might have leftover newlines
                return False
        except EOFError:
            # stdin closed (e.g. piped input) — default to False
            return False
        except KeyboardInterrupt:
            print()
            return False
