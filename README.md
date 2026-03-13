# Codey

**Important: Codey has evolved!**  

The original simple CLI coding assistant has been rearchitected into **Codey-v2**: a full persistent, learning agent daemon.  
This repo's README has been updated to reflect v1 features, but for the dedicated v2 developement (ongoing commits, issues, PRs):  
→ https://github.com/Ishabdullah/Codey-v2

If you're looking for the classic session-based version you found it. 🦾🦾🦾

A local AI coding assistant for Termux, powered by Qwen2.5-Coder-7B running entirely on-device via llama.cpp. No cloud, no API keys, no data leaving your phone.

```
  ██████╗ ██████╗ ██████╗ ███████╗██╗   ██╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝
 ██║     ██║   ██║██║  ██║█████╗   ╚████╔╝
 ██║     ██║   ██║██║  ██║██╔══╝    ╚██╔╝
 ╚██████╗╚██████╔╝██████╔╝███████╗   ██║
  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝
  v1.0.0 · Local AI Coding Assistant · Termux
```

---

## Features

- **ReAct agent loop** — thinks, calls tools, observes results, repeats
- **Task orchestrator** — breaks complex tasks into subtask queues with a live checklist UI
- **Repo map** — automatically scans project symbols on startup for better context
- **Tiered memory** — LRU file eviction, relevance scoring, rolling summaries (4096 token budget)
- **.codeyignore** — pattern-based file exclusion for context and auto-loading
- **CODEY.md** — persistent project memory loaded on every session
- **TDD loop** — write → test → fix → verify cycle with pytest
- **File tools** — `write_file`, `patch_file` (with context matching), `read_file`, `append_file`, `list_dir`
- **Shell execution** — runs commands with auto-retry and security hardening
- **Workspace restriction** — file operations outside the project root require confirmation
- **Session persistence** — opt-in resume via `--session` flag
- **Source file protection** — agents cannot modify Codey's own source files
- **Auto-commit** — offers to stage and commit changes after successful task completion
- **Claude Code-style UI** — syntax-highlighted panels, colored diffs, task checklists
- **Context bar** — live token usage + tokens/sec display
- **Auto-summarization** — compresses long conversation history to save context
- **File undo/diff** — `/undo` and `/diff` commands for any Codey-edited file
- **Project detection** — auto-detects Python, Node, Rust, Go projects
- **Search** — grep across project files with `/search`
- **Git integration** — commit and push from chat with `/git`

---

## Requirements

- **Termux** on Android
- **RAM:** 5GB+ available (model uses ~4.4GB)
- **Storage:** ~5GB for model + ~500MB for llama.cpp
- **Python:** 3.12+
- **Packages:** `rich` (`pip install rich`)

---

## Installation

### 1. Install llama.cpp

```bash
pkg install cmake ninja clang
git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DLLAMA_CURL=OFF
cmake --build build --config Release -j4
```

### 2. Download the model

```bash
mkdir -p ~/models/qwen2.5-coder-7b
cd ~/models/qwen2.5-coder-7b
# Download Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf from HuggingFace
# ~4.7GB download
```

### 3. Install Codey

```bash
git clone https://github.com/Ishabdullah/Codey.git ~/codey
pip install rich
```

### 4. Add to PATH

```bash
echo 'export PATH="$HOME/codey:$PATH"' >> ~/.bashrc
source ~/.bashrc
chmod +x ~/codey/codey
```

### 5. Verify

```bash
codey --version
# Codey v0.9.0
```

---

## Usage

### One-shot mode
```bash
codey "create a Flask hello world app and run it"
```

### YOLO mode (skip confirmations)
```bash
codey --yolo "create todo.py with add_task remove_task list_tasks"
```

### Interactive chat
```bash
codey
You> fix the bug in main.py
```

### Pre-load files
```bash
codey --read main.py utils.py "refactor the helper functions"
```

### Resume a session
```bash
codey --session abc123
```

### Generate project memory
```bash
codey --init
```

### TDD mode
```bash
codey --tdd "create a calculator with add subtract multiply divide"
```

### Plan mode (confirm before executing)
```bash
codey --plan "refactor the entire auth module"
```

---

## Chat Commands

### File Commands
| Command | Description |
|---|---|
| `/read <file>` | Load file into context |
| `/load <file\|*.py\|dir/>` | Load file, glob pattern, or directory |
| `/unread <file>` | Remove file from context |
| `/ignore <pattern>` | Add pattern to `.codeyignore` file |
| `/context` | Show loaded files with token counts and age |
| `/diff [file]` | Show colored diff of Codey's changes |
| `/undo [file]` | Restore file to previous version |

### Project Commands
| Command | Description |
|---|---|
| `/init` | Generate CODEY.md project memory file |
| `/memory` | Show current CODEY.md contents |
| `/memory-status` | Show memory manager stats (files, summary, turn) |
| `/project` | Show detected project type and key files |
| `/search <pattern> [path]` | Search across project files |
| `/git [commit\|push\|status]` | Git operations from chat |
| `/cwd [path]` | Show or change working directory |

### Session Commands
| Command | Description |
|---|---|
| `/clear` | Clear history, file context, and undo history |
| `/exit` | Quit Codey |
| `/help` | Show all commands |

---

## CLI Flags

| Flag | Description |
|---|---|
| `--yolo` | Skip all confirmations |
| `--plan` | Show and confirm plan before executing |
| `--no-plan` | Disable orchestrator even for complex tasks |
| `--tdd` | Enable TDD loop (write→test→fix→verify) |
| `--session <id>` | Resume a saved session |
| `--read <file>` | Pre-load files into context |
| `--init` | Generate CODEY.md and exit |
| `--chat` | Interactive mode even with an initial prompt |
| `--threads <n>` | Override CPU thread count |
| `--ctx <n>` | Override context window size |
| `--version` | Show version |

---

## How It Works

### Agent Loop (ReAct)
```
User prompt
    ↓
Build system prompt (SYSTEM_PROMPT + CODEY.md + relevant files)
    ↓
Infer → parse tool call → execute tool → observe result
    ↓ (loop until done or max steps)
Final answer
```

### Tool Call Format
The model outputs tool calls in this format:
```
<tool>
{"name": "write_file", "args": {"path": "hello.py", "content": "print('hello')"}}
</tool>
```

### Available Tools
| Tool | Description |
|---|---|
| `write_file` | Create or overwrite a file |
| `patch_file` | Surgical find/replace within a file |
| `read_file` | Read file contents |
| `append_file` | Append to a file |
| `list_dir` | List directory contents |
| `shell` | Execute a shell command |
| `search_files` | Grep pattern across files |

### Task Orchestrator
For complex multi-step tasks (>100 chars with 3+ action signals), Codey plans subtasks first:
```
╭─────────────────── Task Plan  0/3 ───────────────────╮
│   ☐  1. Create todo.py with add_task remove_task...  │
│   ☐  2. Create test_todo.py with 3 pytest tests      │
│   ☐  3. Run tests and fix any failures               │
╰──────────────────────────────────────────────────────╯
  Execute this plan? [Y/n]:
```

Each subtask runs in an isolated context. The checklist updates live with ✓ as tasks complete.

### Memory Architecture
```
┌──────────────────────────────────────────┐
│           4096 TOKEN WINDOW              │
├──────────────┬───────────────────────────┤
│ FIXED (~700) │ System prompt + CODEY.md  │
├──────────────┼───────────────────────────┤
│ ANCHOR (~300)│ Rolling work summary      │ ← compressed history
├──────────────┼───────────────────────────┤
│ DYNAMIC(~800)│ Relevant files only       │ ← LRU + relevance scored
├──────────────┼───────────────────────────┤
│ HOT (~500)   │ Last 3 conversation turns │ ← always kept
├──────────────┼───────────────────────────┤
│ CURRENT(~300)│ This message              │
├──────────────┼───────────────────────────┤
│ RESPONSE(~1296)│ Model output budget     │
└──────────────┴───────────────────────────┘
```

---

## CODEY.md — Project Memory

Run `/init` in any project directory to generate a `CODEY.md` file. Codey auto-loads this on every session, giving it accurate context about your project without wasting tokens on repeated directory scans.

Example:
```markdown
# Project
A FastAPI REST API for task management.

# Stack
- Python 3.12, FastAPI, SQLite, pytest

# Structure
- main.py — app entry point and routes
- models.py — SQLAlchemy models
- tests/ — pytest test suite

# Commands
- Run: uvicorn main:app --reload
- Test: pytest tests/
```

---

## Performance

| Metric | Value |
|---|---|
| Model | Qwen2.5-Coder-7B-Instruct Q4_K_M |
| RAM usage | ~4.4GB |
| Context window | 4096 tokens |
| Threads | 4 (configurable) |
| Speed | ~7-8 t/s on modern Android |
| Cold start | ~15s first inference |
| Warm inference | ~2-3s |

---

## Configuration

Edit `~/codey/utils/config.py`:

```python
MODEL_CONFIG = {
    "n_ctx":          4096,   # context window
    "n_threads":      4,      # CPU threads (lower = less heat)
    "n_batch":        256,    # batch size
    "max_tokens":     1024,   # max response length
    "temperature":    0.2,    # lower = more deterministic
    "top_p":          0.95,
    "top_p":          40,
    "repeat_penalty": 1.1,
    "kv_cache_type":  "q8_0", # quantized KV cache saves RAM
}

AGENT_CONFIG = {
    "max_steps":      6,      # tool call limit per task
    "history_turns":  6,      # conversation turns to keep
    "confirm_shell":  True,   # ask before running shell commands
    "confirm_write":  True,   # ask before writing files
}
```

---

## Project Structure

```
~/codey/
├── main.py                 # CLI entrypoint, REPL, command handling
├── codey                   # shell launcher script
├── CODEY.md                # project memory for Codey itself
├── core/
│   ├── agent.py            # ReAct tool loop, hallucination guard
│   ├── inference.py        # llama-server HTTP client, TPS tracking
│   ├── loader.py           # binary/model path validation
│   ├── orchestrator.py     # task planning and queue execution
│   ├── taskqueue.py        # persistent task queue (JSON)
│   ├── display.py          # Rich UI panels, checklists, diffs
│   ├── memory.py           # MemoryManager: LRU + relevance scoring
│   ├── context.py          # file context wrapper over MemoryManager
│   ├── sessions.py         # session save/load/list
│   ├── tdd.py              # TDD loop: write→test→fix→verify
│   ├── planner.py          # plan mode: generate and confirm plan
│   ├── summarizer.py       # conversation compression
│   ├── codeymd.py          # CODEY.md read/write/generate
│   ├── tokens.py           # token counting, context bar, TPS
│   └── project.py          # project type detection
├── tools/
│   ├── file_tools.py       # write/read/append/list + PROTECTED_FILES
│   ├── patch_tools.py      # surgical find/replace with undo snapshot
│   └── shell_tools.py      # shell execution with safety checks
├── prompts/
│   └── system_prompt.py    # system prompt and tool format
└── utils/
    ├── config.py           # all settings
    ├── logger.py           # rich terminal output helpers
    └── file_utils.py       # low-level file operations
| `/undo [file]` | Restore file to previous version |

---

## Features In-Depth

### .codeyignore
Create a `.codeyignore` file in your project root to prevent Codey from reading certain files. It supports glob-style patterns (e.g., `*.log`, `node_modules/`, `secrets/`). 
Default ignores include: `.git`, `__pycache__`, `.env`, and private keys.

### Repo Map
Codey automatically generates a lightweight "map" of your project structure (classes, functions, and imports) on startup. This provides the model with architectural context without loading full file contents into the token window.

### Workspace Restriction
To prevent unintended modifications, Codey restricts its file tools to the current project directory. Any attempt to read or write a file outside the workspace root will trigger a confirmation prompt.

### Auto-Commit
After completing a task or running successful tests, Codey will check your git status. If changes are detected, it will offer to stage and commit them automatically with a descriptive message based on the task.

---

## Version History

| Version | Highlights |
|---|---|
| v1.0.0 | Production release — full stability, security hardening, repo map, task orchestrator |
| v0.9.5 | Strip "Final Answer:" from checklists, refined planner prompts |
| v0.9.4 | Added `--no-plan` flag and `/ignore` command |
| v0.9.3 | Repo map, auto-commit after tasks, context-aware `patch_file` instructions |
| v0.9.2 | Portable paths (auto-detect llama-server), shell hardening, session redaction, workspace root restriction |
| v0.9.1 | P1 stability fixes: robust JSON parser, patch collision checks, `.codeyignore` support |
| v0.9.0 | Task orchestrator, subtask queues, source file protection, TPS display |


---

## Known Limitations

- **7B model quality** — complex multi-file refactors may require guidance
- **4096 token window** — large projects need selective file loading
- **Serial execution** — no parallel tool calls or async inference
- **No repo indexing** — no vector DB or Tree-sitter; relies on explicit file loading
- **Termux only** — shell commands assume Linux/Android environment

---

## License

MIT

