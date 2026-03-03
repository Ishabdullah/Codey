#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import console, info, success, error, warning, separator
from utils.config import CODEY_VERSION
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
    parser.add_argument("prompt",    nargs="?")
    parser.add_argument("--yolo",    action="store_true")
    parser.add_argument("--threads", type=int)
    parser.add_argument("--ctx",     type=int)
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--chat",    action="store_true")
    parser.add_argument("--read",    nargs="+", metavar="FILE")
    parser.add_argument("--init",    action="store_true")
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

def run_init():
    from core.project import detect_project
    from core.codeymd import get_init_prompt, write_codeymd, find_codeymd
    from core.inference import infer
    existing = find_codeymd()
    if existing:
        warning(f"CODEY.md already exists at {existing}")
        ans = input("Overwrite? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            info("Aborted.")
            return
    proj = detect_project()
    info(f"Analyzing {proj['type']} project in {proj['cwd']}...")
    messages = [
        {"role": "system", "content": "You are a technical writer. Output only clean markdown, no preamble."},
        {"role": "user",   "content": get_init_prompt(proj)}
    ]
    info("Generating CODEY.md...")
    content = infer(messages, stream=False)
    if content.startswith("[ERROR]"):
        error(f"Generation failed: {content}")
        return
    path = write_codeymd(content)
    if path.startswith("[ERROR]"):
        error(path)
    else:
        success(f"CODEY.md written to {path}")

def print_diff(diff_output: str):
    """Print diff with color."""
    for line in diff_output.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        else:
            console.print(line)

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
        from core.filehistory import clear_history
        clear_history()
        success("History, file context, and undo history cleared.")
        return True, history

    # /undo [file] — restore last version
    if low.startswith("/undo"):
        from core.filehistory import undo, list_history
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            # Show what can be undone
            hist = list_history()
            if not hist:
                info("Nothing to undo this session.")
            else:
                console.print("[bold]Files with undo history:[/bold]")
                for path, timestamps in hist.items():
                    name = Path(path).name
                    console.print(f"  📄 {name} — versions at: {', '.join(timestamps)}")
                info("Usage: /undo <filename>")
        else:
            result = undo(parts[1])
            if result.startswith("[ERROR]"):
                error(result)
        return True, history

    # /diff [file] — show changes
    if low.startswith("/diff"):
        from core.filehistory import diff, list_history
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            hist = list_history()
            if not hist:
                info("No file changes this session.")
            else:
                console.print("[bold]Changed files:[/bold]")
                for path in hist:
                    console.print(f"  📄 {Path(path).name}")
                info("Usage: /diff <filename>")
        else:
            result = diff(parts[1])
            if result.startswith("[ERROR]") or result.startswith("No"):
                info(result)
            else:
                print_diff(result)
        return True, history

    # /load — load files, globs, or directories
    if low.startswith("/load"):
        parts = cmd.split()[1:]
        if not parts:
            info("Usage: /load <file|glob|dir> ...")
            info("  /load *.py              — load all Python files")
            info("  /load core/             — load all files in core/")
            info("  /load main.py utils/    — mix of files and dirs")
        else:
            for target in parts:
                p = Path(target)
                if p.is_dir():
                    ctx.load_directory(str(p))
                elif "*" in target or "?" in target:
                    ctx.load_glob(target)
                else:
                    ctx.load_file(target)
        return True, history

    # /read (alias for /load single file)
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

    if low == "/context":
        loaded = ctx.list_loaded()
        if loaded:
            console.print("[bold]Loaded files:[/bold]")
            for f in loaded:
                console.print(f"  📄 {Path(f).name} ({len(ctx._loaded_files[f])} chars)")
        else:
            info("No files loaded.")
        return True, history

    if low == "/project":
        from core.project import detect_project
        proj = detect_project()
        console.print(f"[bold]Project:[/bold] {proj['type']} · {proj['cwd']}")
        if proj["key_files"]:
            console.print(f"[bold]Key files:[/bold] {', '.join(proj['key_files'])}")
        return True, history

    if low == "/init":
        run_init()
        return True, history

    if low == "/memory":
        from core.codeymd import find_codeymd, read_codeymd
        path = find_codeymd()
        if path:
            console.print(f"[bold]CODEY.md[/bold] ({path}):\n")
            console.print(read_codeymd())
        else:
            info("No CODEY.md found. Run /init to generate one.")
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
[bold]File commands:[/bold]
  /read <file>          Load file into context
  /load <file|*.py|dir> Load file, glob, or directory
  /unread <file>        Remove file from context
  /context              Show loaded files
  /diff [file]          Show what Codey changed
  /undo [file]          Restore file to previous version

[bold]Project commands:[/bold]
  /init                 Generate CODEY.md project memory
  /memory               Show CODEY.md contents
  /project              Show project info
  /cwd [path]           Show or change directory

[bold]Session commands:[/bold]
  /clear                Clear history, context, undo history
  /exit                 Quit
  /help                 This help

[bold]CLI flags:[/bold]
  codey "task"          One-shot
  codey --chat "task"   Chat with prefilled prompt
  codey --yolo "task"   Skip confirmations
  codey --read file.py  Pre-load file
  codey --init          Generate CODEY.md and exit
        """)
        return True, history

    return False, history

def repl(initial_prompt=None, yolo=False, one_shot=False, preload=None):
    console.print(BANNER)
    separator()
    load_model()

    from core.project import detect_project
    from core.codeymd import find_codeymd
    proj = detect_project()
    if proj["type"] != "unknown":
        info(f"Project: [bold]{proj['type']}[/bold] · {os.getcwd()}")
    codeymd_path = find_codeymd()
    if codeymd_path:
        info(f"Memory: [bold]CODEY.md[/bold] found")
    else:
        info("No CODEY.md — run [bold]/init[/bold] to create project memory")

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
        suffix = f" [bold dim]({len(loaded)} file{'s' if len(loaded)!=1 else ''})[/bold dim]" if loaded else ""
        try:
            user_input = console.input(f"[bold blue]You{suffix}>[/bold blue] ").strip()
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
    if args.init:
        load_model()
        run_init()
        shutdown()
        return
    one_shot = bool(args.prompt and not args.chat)
    repl(initial_prompt=args.prompt, yolo=args.yolo,
         one_shot=one_shot, preload=args.read)

if __name__ == "__main__":
    main()
