#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import console, info, success, error, separator
from utils.config import CODEY_VERSION, CODEY_NAME
from core.loader import load_model
from core.agent import run_agent
from core import context as ctx

BANNER = f"""[bold green]
  ██████╗ ██████╗ ██████╗ ███████╗██╗   ██╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝
 ██║     ██║   ██║██║  ██║█████╗   ╚████╔╝
 ██║     ██║   ██║██║  ██║██╔══╝    ╚██╔╝
 ╚██████╗╚██████╔╝██████╔╝███████╗   ██║
  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝
[/bold green][dim]  v{CODEY_VERSION} · Local AI Coding Assistant · Termux[/dim]
"""

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Codey - Local AI coding assistant")
    parser.add_argument("prompt",      nargs="?", help="One-shot prompt")
    parser.add_argument("--yolo",      action="store_true", help="Skip confirmations")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming")
    parser.add_argument("--threads",   type=int,  help="CPU thread count")
    parser.add_argument("--ctx",       type=int,  help="Context window size")
    parser.add_argument("--version",   action="store_true")
    parser.add_argument("--chat",      action="store_true", help="Interactive mode even with prompt")
    parser.add_argument("--read",      nargs="+", metavar="FILE", help="Pre-load files into context")
    return parser.parse_args()

def apply_overrides(args):
    from utils import config
    if args.yolo:
        config.AGENT_CONFIG["confirm_shell"] = False
        config.AGENT_CONFIG["confirm_write"] = False
        info("YOLO mode: confirmations disabled.")
    if args.threads:
        config.MODEL_CONFIG["n_threads"] = args.threads
    if args.ctx:
        config.MODEL_CONFIG["n_ctx"] = args.ctx

def shutdown():
    try:
        from core.inference import stop_server
        stop_server()
    except Exception:
        pass

def handle_command(user_input: str, history: list) -> tuple[bool, list]:
    cmd = user_input.strip()
    low = cmd.lower()

    if low in ("/exit", "/quit", "exit", "quit"):
        console.print("[dim]Goodbye![/dim]")
        shutdown()
        sys.exit(0)

    if low == "/clear":
        history.clear()
        ctx.clear_context()
        success("History and file context cleared.")
        return True, history

    if low == "/context":
        loaded = ctx.list_loaded()
        if loaded:
            console.print("[bold]Loaded files:[/bold]")
            for f in loaded:
                console.print(f"  📄 {f}")
        else:
            info("No files loaded. Use /read <file> to load one.")
        return True, history

    if low == "/project":
        from core.project import detect_project
        proj = detect_project()
        console.print(f"[bold]Project:[/bold] {proj['type']}")
        console.print(f"[bold]Directory:[/bold] {proj['cwd']}")
        if proj["key_files"]:
            console.print(f"[bold]Key files:[/bold] {', '.join(proj['key_files'])}")
        return True, history

    if low.startswith("/read"):
        parts = cmd.split()[1:]
        if not parts:
            info("Usage: /read <file1> [file2] ...")
        else:
            for f in parts:
                ctx.load_file(f)
        return True, history

    if low.startswith("/unread"):
        parts = cmd.split()[1:]
        if not parts:
            info("Usage: /unread <file>")
        else:
            for f in parts:
                ctx.unload_file(f)
        return True, history

    if low.startswith("/cwd"):
        parts = cmd.split(maxsplit=1)
        if len(parts) > 1:
            try:
                os.chdir(parts[1])
                from core.project import invalidate_cache
                invalidate_cache()
                success(f"Working directory: {os.getcwd()}")
            except Exception as e:
                error(str(e))
        else:
            info(f"Current directory: {os.getcwd()}")
        return True, history

    if low == "/help":
        console.print("""
[bold]Commands:[/bold]
  /read <file>    Load file into context
  /unread <file>  Remove file from context
  /context        Show loaded files
  /project        Show detected project info
  /clear          Clear history and context
  /cwd [path]     Show or change working directory
  /exit           Quit
  /help           This help

[bold]CLI flags:[/bold]
  codey "task"              One-shot
  codey --chat "task"       Chat with prefilled prompt
  codey --yolo "task"       Skip confirmations
  codey --read file.py      Pre-load file
  codey                     Interactive chat

[bold]Auto-features:[/bold]
  • Files mentioned by name are auto-loaded into context
  • Shell errors trigger automatic fix attempts
  • Project type and files detected from current directory
        """)
        return True, history

    return False, history

def repl(initial_prompt=None, yolo=False, one_shot=False, preload=None):
    console.print(BANNER)
    separator()
    load_model()

    # Show project context on startup
    from core.project import detect_project
    proj = detect_project()
    if proj["type"] != "unknown":
        info(f"Project: [bold]{proj['type']}[/bold] · {os.getcwd()}")

    if preload:
        for f in preload:
            ctx.load_file(f)

    history = []

    if initial_prompt and one_shot:
        try:
            run_agent(initial_prompt, history, yolo=yolo)
        except KeyboardInterrupt:
            pass
        finally:
            shutdown()
        return

    info("Type your task. /help for commands.")
    separator()

    if initial_prompt:
        try:
            _, history = run_agent(initial_prompt, history, yolo=yolo)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")

    while True:
        loaded = ctx.list_loaded()
        prompt_suffix = f" [bold dim]({len(loaded)} file{'s' if len(loaded)!=1 else ''})[/bold dim]" if loaded else ""
        try:
            user_input = console.input(f"[bold blue]You{prompt_suffix}>[/bold blue] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            shutdown()
            break

        if not user_input:
            continue

        was_cmd, history = handle_command(user_input, history)
        if was_cmd:
            continue

        try:
            _, history = run_agent(user_input, history, yolo=yolo)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
        except Exception as e:
            error(f"Agent error: {e}")
            import traceback
            traceback.print_exc()

def main():
    args = parse_args()
    if args.version:
        print(f"Codey v{CODEY_VERSION}")
        sys.exit(0)
    apply_overrides(args)
    one_shot = bool(args.prompt and not args.chat)
    repl(
        initial_prompt=args.prompt,
        yolo=args.yolo,
        one_shot=one_shot,
        preload=args.read,
    )

if __name__ == "__main__":
    main()
