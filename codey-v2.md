# Codey v2 — Implementation Plan

## Overview

Codey v2 transforms Codey from a session-based CLI tool into a **persistent, daemon-like AI agent** that lives on your device. Instead of being "run" for each task, Codey v2 exists continuously—maintaining state, managing background processes, and adapting to work without constant supervision.

The key difference from current Codey: **persistence over invocation**. Current Codey is a tool you run. Codey v2 is an agent that exists. It has a native "body" (daemon process), direct filesystem access (no tool-call parsing), internal planning (not model-asked orchestration), hierarchical memory (working/project/long-term/episodic), self-modification capability (with checkpointing), and observability into its own state. All while running locally on an S24 Ultra with dual-model hot-swap (7B primary, 1.5B secondary) for thermal and memory efficiency.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLI Client (codey)                         │
│  ── User commands, flags, REPL interface                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Daemon Core (codeyd)                       │
│  ── Main event loop, signal handlers, PID file, Unix socket     │
│  ── Receives commands from CLI or scheduled tasks               │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   Planner        │ │   Memory         │ │   Tools          │
│   (internal)     │ │   (hierarchical) │ │   (direct)       │
│ ── Task queue    │ │ ── Working       │ │ ── Filesystem    │
│ ── Adaptation    │ │ ── Project       │ │ ── Shell         │
│ ── Background    │ │ ── Long-term     │ │ ── Git           │
│    tasks         │ │ ── Episodic      │ │ ── Search        │
└──────────────────┘ └──────────────────┘ └──────────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LLM Layer (inference)                      │
│  ── Model router (7B ↔ 1.5B hot-swap)                          │
│  ── Direct llama.cpp binding (no HTTP)                         │
│  ── Context management, token tracking                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      State Store (SQLite)                       │
│  ── Persistent memory, task queue, episodic log                │
│  ── Survives restarts, daemon reloads                          │
└─────────────────────────────────────────────────────────────────┘
```

### Components

| Component | File(s) | Responsibility |
|-----------|---------|----------------|
| **CLI Client** | `codey` (bash), `main.py` | User interface, command parsing, REPL |
| **Daemon Core** | `core/daemon.py` (NEW) | Main process, signal handlers, socket listener |
| **Planner** | `core/planner_v2.py` (NEW) | Internal task planning, adaptation, background scheduling |
| **Memory** | `core/memory_v2.py` (NEW) | Hierarchical memory (working/project/long-term/episodic) |
| **Tools** | `tools/` (refactored) | Direct filesystem/shell/git access (no JSON parsing) |
| **LLM Layer** | `core/inference_v2.py` (NEW), `core/loader_v2.py` (NEW) | Model loading, hot-swap routing, direct llama.cpp |
| **State Store** | `core/state.py` (NEW) | SQLite schema, persistence, rollback |
| **Observability** | `core/observability.py` (NEW) | Self-state queries, health checks, metrics |

---

## Major Features

### 1. Persistent Daemon

**Description:** Codey runs as a background daemon process with a Unix socket for CLI communication, PID file for single-instance enforcement, and signal handlers for graceful shutdown/reload.

**Motivation:** Current Codey spawns fresh for each command, losing all state. Daemon mode enables continuous existence, background tasks, and instant CLI response.

**Key Decisions/Tradeoffs:**
- Unix socket over TCP: Faster, no port conflicts, local-only security
- PID file in `~/.codey/codey.pid`: Standard daemon pattern, easy cleanup
- SIGUSR1 for hot reload (config changes without restart)
- SIGTERM for graceful shutdown (complete current task, save state)
- Tradeoff: Daemon consumes ~200MB RAM idle vs. 0MB when not in use

**Implementation:**
- `core/daemon.py`: Main daemon loop, socket server, signal registration
- `codeyd` (NEW bash script): Daemon launcher (`codeyd start|stop|status|reload`)
- CLI (`codey`) connects to socket if daemon running, spawns direct if not

---

### 2. Direct Filesystem Access

**Description:** Remove tool-call JSON parsing. Agent calls `self.files.read(path)` directly as native Python methods.

**Motivation:** Current flow: model outputs JSON → `parse_tool_call()` → `execute_tool()` → `tool_read_file()`. This adds latency, parsing errors, and hallucination surface.

**Key Decisions/Tradeoffs:**
- Tools become direct method calls on `self.files`, `self.shell`, `self.git`
- Model still outputs tool tags for transparency, but parsing is simplified
- Tradeoff: Less validation, so safeguards move to method-level (e.g., path validation in `files.read()`)

**Implementation:**
- Refactor `tools/file_tools.py` → `core/filesystem.py` (class-based, direct access)
- Update `core/agent_v2.py` to use `self.files.read()` instead of tool dispatch
- Keep tool tags in model output for logging/observability

---

### 3. Internal Planning (Native Orchestrator)

**Description:** Planning moves from "ask model to list steps" to internal agent reasoning. The agent generates, tracks, and adapts tasks as part of its thought process.

**Motivation:** Current `orchestrator.py` wastes tokens asking model to output numbered lists. Planning should be intrinsic, not prompted.

**Key Decisions/Tradeoffs:**
- Planner is a Python class with task queue, dependency tracking, adaptation logic
- Model receives one task at a time with context from prior tasks
- Tradeoff: Less "visible" planning to user, but more efficient and adaptable

**Implementation:**
- `core/planner_v2.py`: `Planner` class with `add_task()`, `complete_task()`, `adapt()`
- Task queue stored in SQLite (survives restarts)
- Remove `core/orchestrator.py` and `core/taskqueue.py` (replaced by planner)

---

### 4. Hierarchical Memory

**Description:** Four-tier memory system:
- **Working:** Currently edited files (evicted after task completes)
- **Project:** CODEY.md, key files (never evicted)
- **Long-term:** Embeddings + vector search for semantic recall
- **Episodic:** SQLite log of actions taken (for "what did I do last week?")

**Motivation:** Current `memory.py` is flat turn-based eviction. No semantic search, no persistent project knowledge, no action history.

**Key Decisions/Tradeoffs:**
- Working memory: In-memory dict, fast access
- Project memory: Loaded at daemon start, cached
- Long-term: SQLite + sentence-transformers (small model, ~100MB)
- Episodic: SQLite append-only log
- Tradeoff: Embeddings add ~100MB RAM, but enable "find that function I wrote" queries

**Implementation:**
- `core/memory_v2.py`: `Memory` class with four sub-managers
- `core/embeddings.py` (NEW): Sentence-transformers integration
- SQLite tables: `episodic_log`, `longterm_embeddings`, `project_files`

---

### 5. Self-Modification with Checkpointing

**Description:** Remove `PROTECTED_FILES` block. Agent can modify any file, including its own source. Before modifying core files, agent creates a checkpoint snapshot for rollback.

**Motivation:** Current Codey blocks self-modification. To evolve, Codey must be able to rewrite itself safely.

**Key Decisions/Tradeoffs:**
- Checkpoint before any write to `core/`, `tools/`, `utils/`
- Checkpoint = git commit + full file backup in `~/.codey/checkpoints/`
- Rollback via `codey rollback <checkpoint_id>`
- Tradeoff: Checkpoints add ~50-100MB per self-modification event

**Implementation:**
- Remove `PROTECTED_FILES` from `tools/file_tools.py`
- Add `core/checkpoint.py` (NEW): `create_checkpoint()`, `rollback()`
- Git integration: Auto-commit on checkpoint with message "Codey self-mod: <reason>"

---

### 6. Observability (Self-State Queries)

**Description:** Agent can query its own state: token usage, memory contents, task queue, filesystem watches, model loaded, thermal status.

**Motivation:** Current Codey has no introspection. Debugging requires reading logs. Agent should know its own state.

**Key Decisions/Tradeoffs:**
- `self.state` object with properties: `tokens_used`, `memory_loaded`, `tasks_pending`, `model_active`, `temperature`
- Exposed via `/status` CLI command and agent-internal queries
- Tradeoff: State tracking adds minor overhead (~5% latency)

**Implementation:**
- `core/observability.py`: `State` class with property accessors
- Update all core modules to report metrics to `State`
- CLI: `/status` command displays current state

---

### 7. Background Execution

**Description:** Agent can spawn background tasks (file watches, long-running servers, periodic checks) via asyncio event loop.

**Motivation:** Current Codey blocks on every command. Background execution enables parallel work (e.g., run tests while writing next file).

**Key Decisions/Tradeoffs:**
- Asyncio event loop in daemon core
- Background tasks tracked in SQLite, survive daemon restarts
- File watches via `watchdog` library (lightweight, ~10MB RAM)
- Tradeoff: Async complexity, but enables true multitasking

**Implementation:**
- `core/daemon.py`: Async event loop (`asyncio.run()`)
- `core/background.py` (NEW): `BackgroundTask` class, file watch registration
- Add `watchdog` to `requirements.txt`

---

### 8. Dual-Model Hot-Swap

**Description:** Two models loaded on-demand:
- **Primary:** Qwen2.5-Coder-7B-Instruct Q4_K_M (code tasks)
- **Secondary:** Qwen2.5-1.5B-Instruct Q8_0 (simple queries)
- Router decides per-task, hot-swaps with 2-3 second delay

**Motivation:** Thermal and memory efficiency. Simple tasks don't need 7B. Running both at once is impossible on 12GB RAM.

**Key Decisions/Tradeoffs:**
- Router heuristic: <50 chars + simple keywords → 1.5B, else 7B
- Hot-swap: Unload current, load target (2-3 sec delay)
- Cooldown: 30 seconds before swapping back (avoid thrashing)
- Tradeoff: 2-3 sec delay on swap, but 3x faster on simple tasks

**Implementation:**
- `core/loader_v2.py`: `ModelLoader` class with `load_primary()`, `load_secondary()`, `unload()`
- `core/router.py` (NEW): `route_task()` heuristic
- Update `core/inference_v2.py` to accept `model='primary'|'secondary'`

---

### 9. Error Recovery (Strategy Switching)

**Description:** Instead of fixed retry count, agent adapts strategy on failure: `write_file` fails → try `patch_file`. Tests fail → debug with targeted fixes. Command errors → search for solution.

**Motivation:** Current Codey retries same action 2x, then gives up. Real debugging requires strategy changes.

**Key Decisions/Tradeoffs:**
- Strategy tree per tool type (file write, shell, test run)
- Agent receives error context and suggested alternative
- Tradeoff: More complex agent logic, but higher success rate

**Implementation:**
- `core/recovery.py` (NEW): `StrategySwitcher` class with fallback trees
- Update `core/agent_v2.py` to call `switcher.get_fallback()` on error
- Add error classification (syntax error, import error, runtime error)

---

### 10. Direct llama.cpp Binding

**Description:** Replace HTTP server (`llama-server`) with direct `llama-cpp-python` binding. No subprocess, no HTTP overhead.

**Motivation:** Current flow: spawn `llama-server` → HTTP request → parse response. Adds ~500ms latency, subprocess management complexity.

**Key Decisions/Tradeoffs:**
- Use `llama-cpp-python` package (pip installable)
- Direct `Llama.create_chat_completion()` calls
- Tradeoff: `llama-cpp-python` requires compilation (may need prebuilt wheel for Termux)

**Implementation:**
- Add `llama-cpp-python` to `requirements.txt`
- `core/inference_v2.py`: Replace HTTP calls with `llama_cpp.Llama()`
- Remove `llama-server` binary dependency, `_start_server()` logic

---

## Implementation Plan (Phased Roadmap)

### Phase 1: Foundation (Daemon + State Store)

**Goals:**
- Daemon process with socket listener
- SQLite state store
- CLI connects to daemon

**Code Changes:**
- Add: `core/daemon.py`, `core/state.py`, `codeyd` (bash script)
- Modify: `codey` (bash script), `main.py` (CLI mode detection)

**Data Model:**
```sql
-- SQLite schema (core/state.py)
CREATE TABLE state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, running, done, failed
    result TEXT,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    completed_at INTEGER
);

CREATE TABLE episodic_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    action TEXT NOT NULL,
    details TEXT
);
```

**Testing:**
- Daemon starts, creates PID file, listens on socket
- CLI connects, sends command, receives response
- Daemon handles SIGTERM (graceful shutdown), SIGUSR1 (reload)
- State persists across daemon restarts

**Migration:**
- Existing `sessions/*.json` files remain readable
- New state stored in SQLite (`~/.codey/state.db`)
- No breaking changes to user workflows

---

### Phase 2: Direct Filesystem + Tools

**Goals:**
- Remove tool-call JSON parsing
- Direct `self.files.read()/write()` methods
- Simplified agent loop

**Code Changes:**
- Add: `core/filesystem.py`
- Modify: `tools/file_tools.py` → class-based, direct access
- Modify: `core/agent_v2.py` (simplified tool handling)
- Remove: `parse_tool_call()`, `extract_json()` complexity

**Data Model:**
- No changes (filesystem is stateless)

**Testing:**
- Agent reads/writes files without JSON parsing errors
- Hallucination rate decreases (no false tool calls)
- Performance: 20-30% faster file operations

**Migration:**
- Tool tags in model output remain for logging
- Backward compatible with existing prompts

---

### Phase 3: Dual-Model Hot-Swap

**Goals:**
- Load/unload models on demand
- Router heuristic for task routing
- 7B ↔ 1.5B hot-swap with cooldown

**Code Changes:**
- Add: `core/loader_v2.py`, `core/router.py`
- Modify: `core/inference_v2.py` (model parameter)
- Modify: `utils/config.py` (dual-model config)

**Data Model:**
```sql
-- Add to state.db
CREATE TABLE model_state (
    active_model TEXT NOT NULL,  -- 'primary' or 'secondary'
    loaded_at INTEGER NOT NULL,
    last_swap_at INTEGER
);
```

**Testing:**
- Both models download and load successfully
- Router correctly classifies simple vs complex tasks
- Hot-swap completes in 2-3 seconds
- Cooldown prevents thrashing

**Migration:**
- Existing `MODEL_CONFIG` extended (backward compatible)
- Users must download secondary model manually

---

### Phase 4: Hierarchical Memory

**Goals:**
- Four-tier memory system
- Embeddings for long-term semantic search
- Episodic log for action history

**Code Changes:**
- Add: `core/memory_v2.py`, `core/embeddings.py`
- Modify: `core/context.py` (use new memory system)
- Remove: `core/memory.py` (replaced)

**Data Model:**
```sql
CREATE TABLE project_files (
    path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    loaded_at INTEGER NOT NULL,
    is_protected INTEGER NOT NULL  -- never evicted
);

CREATE TABLE longterm_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    chunk_start INTEGER NOT NULL,
    chunk_end INTEGER NOT NULL,
    embedding BLOB NOT NULL,  -- sentence-transformers vector
    created_at INTEGER NOT NULL
);

CREATE TABLE working_memory (
    file_path TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    loaded_at INTEGER NOT NULL,
    last_used_at INTEGER NOT NULL
);
```

**Testing:**
- Project files persist across sessions
- Semantic search finds relevant files ("that function I wrote")
- Working memory evicts after task completion
- Episodic log captures all actions

**Migration:**
- Existing session history imported into episodic log
- CODEY.md auto-loaded as protected project file

---

### Phase 5: Internal Planning + Background Execution

**Goals:**
- Native planner (no model-asked orchestration)
- Async background tasks
- File watches

**Code Changes:**
- Add: `core/planner_v2.py`, `core/background.py`
- Modify: `core/daemon.py` (async event loop)
- Remove: `core/orchestrator.py`, `core/taskqueue.py`

**Data Model:**
```sql
-- Task queue already exists (Phase 1), extend:
ALTER TABLE task_queue ADD COLUMN dependencies TEXT;  -- JSON list of task IDs
ALTER TABLE task_queue ADD COLUMN retry_count INTEGER DEFAULT 0;
```

**Testing:**
- Complex tasks broken into subtasks without model prompting
- Background tasks run in parallel (tests + file writes)
- File watches trigger agent reactions
- Task queue survives daemon restarts

**Migration:**
- Existing `--plan` flag behavior unchanged
- Orchestrator tasks imported into new planner queue

---

### Phase 6: Self-Modification + Observability

**Goals:**
- Remove `PROTECTED_FILES` block
- Checkpointing before self-modification
- Observability queries (`self.state.*`)

**Code Changes:**
- Add: `core/checkpoint.py`, `core/observability.py`
- Modify: `tools/file_tools.py` (remove protection)
- Modify: All core modules (report to observability)

**Data Model:**
```sql
CREATE TABLE checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    reason TEXT NOT NULL,
    files_modified TEXT,  -- JSON list
    git_commit_hash TEXT
);
```

**Testing:**
- Agent modifies own source files
- Rollback restores previous version
- `/status` command shows full state
- Health checks detect issues (memory leak, stuck tasks)

**Migration:**
- `PROTECTED_FILES` removed (breaking change for safety)
- Users must opt-in to self-modification via config

---

### Phase 7: Error Recovery + Polish

**Goals:**
- Strategy switching on failures
- Thermal management
- Final polish, documentation

**Code Changes:**
- Add: `core/recovery.py`
- Modify: `core/agent_v2.py` (error handling)
- Modify: `utils/config.py` (thermal config)

**Data Model:**
- No changes

**Testing:**
- Agent recovers from write failures via patch
- TDD loop debugs failing tests iteratively
- Thermal throttling reduces threads before shutdown
- Full end-to-end: "build a REST API" completes successfully

**Migration:**
- No breaking changes
- Existing `--fix`, `--tdd` modes enhanced

---

## Detailed Tasks Checklist

### Phase 1 Tasks

- [ ] **Create `core/state.py`**: SQLite wrapper with `get()`, `set()`, `delete()` methods. Schema: `state`, `task_queue`, `episodic_log` tables.
- [ ] **Create `core/daemon.py`**: Main daemon class with Unix socket server, signal handlers (SIGTERM, SIGUSR1), PID file management.
- [ ] **Create `codeyd` bash script**: Daemon launcher with `start|stop|status|reload` commands. PID file check, background fork.
- [ ] **Modify `codey` bash script**: Check if daemon running (PID file exists + socket responds). If yes, connect via socket. If no, spawn direct.
- [ ] **Modify `main.py`**: Add `--daemon` flag detection. If daemon mode, initialize daemon core. Else, run existing REPL/one-shot logic.
- [ ] **Test**: Start daemon, send 10 commands via CLI, verify state persists after `codeyd restart`.

### Phase 2 Tasks

- [ ] **Create `core/filesystem.py`**: `Filesystem` class with `read(path)`, `write(path, content)`, `patch(path, old, new)`, `exists(path)` methods. Path validation, workspace checks.
- [ ] **Modify `tools/file_tools.py`**: Convert functions to class methods on `Filesystem`. Remove confirmation logic (move to agent layer).
- [ ] **Modify `core/agent_v2.py`**: Replace `parse_tool_call()` → `execute_tool()` with direct `self.files.read()` calls. Keep tool tags for logging.
- [ ] **Remove**: `parse_tool_call()`, `extract_json()`, `ROGUE_TAG_MAP` (simplify to basic JSON extraction for backward compat).
- [ ] **Test**: Agent reads 5 files, writes 2 files, patches 1 file. Verify no JSON parsing errors.

### Phase 3 Tasks

- [ ] **Download secondary model**: `wget https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q8_0.gguf -P ~/codey/model/`
- [ ] **Modify `utils/config.py`**: Add `secondary_model`, `secondary_ctx`, routing thresholds to `MODEL_CONFIG`.
- [ ] **Create `core/loader_v2.py`**: `ModelLoader` class with `load_primary()`, `load_secondary()`, `unload()`, `get_active_model()`. Track loaded model state.
- [ ] **Create `core/router.py`**: `route_task(user_input)` heuristic. <50 chars + simple keywords → secondary, else primary. 30-second cooldown.
- [ ] **Modify `core/inference_v2.py`**: Add `model='primary'|'secondary'` parameter. Call `loader.ensure_model(model)` before inference.
- [ ] **Test**: Send 20 mixed queries (simple + complex). Verify router sends to correct model. Measure swap latency (<3 sec).

### Phase 4 Tasks

- [ ] **Install sentence-transformers**: `pip install sentence-transformers` (verify Termux compatibility).
- [ ] **Create `core/embeddings.py`**: `EmbeddingModel` class. Load `all-MiniLM-L6-v2` (small, ~80MB). `embed(text)` → numpy array. `search(query, limit=5)` → file paths.
- [ ] **Create `core/memory_v2.py`**: `Memory` class with `working`, `project`, `longterm`, `episodic` sub-managers. `tick()` method for eviction.
- [ ] **Modify `core/context.py`**: Use `memory_v2` for file loading. `build_file_context_block()` queries working + project memory.
- [ ] **Modify SQLite schema**: Add `project_files`, `longterm_embeddings`, `working_memory` tables.
- [ ] **Test**: Load project, edit 3 files, restart daemon. Verify project files persist, semantic search finds edited files.

### Phase 5 Tasks

- [ ] **Create `core/planner_v2.py`**: `Planner` class. `add_task(desc, dependencies=[])`, `complete_task(id, result)`, `get_next_task()`, `adapt()` (on failure).
- [ ] **Create `core/background.py`**: `BackgroundTask` class. `start()`, `stop()`, `is_running()`. File watch integration with `watchdog`.
- [ ] **Modify `core/daemon.py`**: Add asyncio event loop. `asyncio.create_task()` for background tasks. Socket server runs async.
- [ ] **Remove**: `core/orchestrator.py`, `core/taskqueue.py` (functionality moved to planner).
- [ ] **Modify `main.py`**: Update `--plan` flag to use new planner. Remove orchestrator imports.
- [ ] **Test**: "Build a Flask app with tests" → planner creates 4 tasks, executes in order, adapts on test failure.

### Phase 6 Tasks

- [ ] **Remove `PROTECTED_FILES`**: Delete from `tools/file_tools.py`. All files now writable.
- [ ] **Create `core/checkpoint.py`**: `create_checkpoint(reason)`, `rollback(checkpoint_id)`. Git commit + file backup to `~/.codey/checkpoints/`.
- [ ] **Create `core/observability.py`**: `State` class with properties: `tokens_used`, `memory_loaded`, `tasks_pending`, `model_active`, `temperature`.
- [ ] **Modify all core modules**: Report metrics to `observability.state` (e.g., `state.tokens_used = ctx.tokens`).
- [ ] **Add `/status` command**: Display full state in REPL. `codey status` CLI command for daemon mode.
- [ ] **Test**: Modify `core/agent.py`, create checkpoint, rollback. Verify file restored. Check `/status` shows correct state.

### Phase 7 Tasks

- [ ] **Create `core/recovery.py`**: `StrategySwitcher` class. Fallback trees: `write_file` → `patch_file`, `shell` → `search_files`, test fail → `debug_tests()`.
- [ ] **Modify `core/agent_v2.py`**: On error, call `switcher.get_fallback(error_type)`. Retry with new strategy.
- [ ] **Add thermal config**: `THERMAL_CONFIG` in `utils/config.py`. Track inference duration, warn after 5 min, reduce threads to 2 after 10 min.
- [ ] **Final end-to-end test**: "Create a todo app with user auth, write tests, run them, fix failures" → completes successfully.
- [ ] **Documentation**: Update `README.md` with daemon usage, new commands, migration guide.

---

## Risks and Safeguards

### Self-Modification Risks

**Risk:** Agent breaks itself, becomes unusable.

**Safeguards:**
1. **Checkpoint before every core modification**: Full file backup + git commit
2. **Rollback command**: `codey rollback last` or `codey rollback <checkpoint_id>`
3. **Health check on daemon start**: If core files fail import, auto-rollback to last checkpoint
4. **Opt-in only**: `AGENT_CONFIG["allow_self_modify"] = False` by default. User must enable.

**Implementation:**
```python
# core/checkpoint.py
def create_checkpoint(reason: str) -> str:
    """Backup core files, git commit, return checkpoint ID."""
    checkpoint_id = str(int(time.time()))
    backup_dir = CHECKPOINT_DIR / checkpoint_id
    backup_dir.mkdir(parents=True)

    # Copy all core files
    for src in CORE_FILES:
        dst = backup_dir / src.relative_to(CODEY_DIR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Git commit
    git_commit(f"Codey checkpoint: {reason}")

    # Record in DB
    db.execute(
        "INSERT INTO checkpoints (id, created_at, reason, git_commit_hash) VALUES (?, ?, ?, ?)",
        (checkpoint_id, int(time.time()), reason, git_head())
    )
    return checkpoint_id
```

### Background Task Risks

**Risk:** Rogue background task consumes CPU/battery indefinitely.

**Safeguards:**
1. **Task timeout**: All background tasks have max 30 min runtime (configurable)
2. **Resource limits**: Track CPU time per task, kill if >10 min continuous
3. **User approval**: Background tasks require explicit `codey task --background "..."`
4. **Status command**: `codey tasks` shows running background tasks, `codey task kill <id>` stops

**Implementation:**
```python
# core/background.py
class BackgroundTask:
    def __init__(self, func, timeout=1800):  # 30 min default
        self.func = func
        self.timeout = timeout
        self.started_at = None
        self.cpu_time = 0

    async def run(self):
        self.started_at = time.time()
        try:
            await asyncio.wait_for(self.func(), timeout=self.timeout)
        except asyncio.TimeoutError:
            log.warning(f"Task {self.id} timed out after {self.timeout}s")
            raise
```

### Daemon Risks

**Risk:** Daemon crashes, leaves socket/PID file orphaned.

**Safeguards:**
1. **PID file stale check**: On start, if PID file exists but process dead, remove it
2. **Socket cleanup**: On SIGTERM, unlink socket before exit
3. **Auto-restart option**: `codeyd --auto-restart` respawns on crash (logs crash reason)
4. **Health endpoint**: `codey status` checks if daemon responsive, not just PID running

**Implementation:**
```python
# core/daemon.py
def check_pid_file():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
        except (ProcessLookupError, ValueError):
            PID_FILE.unlink()  # Stale, remove it
        else:
            raise RuntimeError("Daemon already running")
```

### Health Checks

**What to monitor:**
1. **Memory usage**: If daemon RSS > 1GB, log warning. If > 1.5GB, trigger GC + evict working memory.
2. **Task queue stuck**: If task status = "running" for >30 min, mark failed, log error.
3. **Model load failures**: If model fails to load 3x consecutively, disable hot-swap, use primary only.
4. **Disk space**: If `~/.codey/` > 5GB, prune old checkpoints (keep last 5).

**Implementation:**
```python
# core/observability.py
def health_check() -> dict:
    return {
        "memory_mb": get_process_memory(),
        "stuck_tasks": db.count("task_queue WHERE status='running' AND started_at < ?", time.time() - 1800),
        "disk_gb": get_directory_size(CODEY_DIR) / 1e9,
        "model_load_failures": state.get("model_load_failures", 0),
    }
```

---

## Future Extensions (Out of Scope for v2)

These are nice-to-have improvements explicitly **not** in the initial implementation:

1. **NPU Acceleration**: Offload layers to Snapdragon NPU if llama.cpp adds support. (Blocked on upstream llama.cpp development.)

2. **Vector Memory UI**: Interactive search interface for long-term memory ("show me all files related to authentication"). (Nice-to-have, not critical.)

3. **Multi-Device Sync**: Sync state/checkpoints across devices via encrypted cloud storage. (Adds complexity, defeats "local-only" goal.)

4. **Plugin System**: Third-party tools (e.g., Docker integration, API clients). (Security risk, defer until core is stable.)

5. **Voice Interface**: Speech-to-text input, text-to-speech output. (Gimmick, not core functionality.)

6. **Multi-Agent Collaboration**: Spawn specialized sub-agents (tester, documenter). (Overkill for single-device use.)

7. **GUI Dashboard**: Web UI for monitoring daemon, viewing tasks. (CLI-first philosophy; GUI can be added later.)

---

## Summary

Codey v2 is a **persistent, daemon-like AI agent** with:
- **Daemon core** (Unix socket, PID file, signal handlers)
- **Direct filesystem access** (no JSON tool parsing)
- **Internal planning** (native task queue, not model-asked)
- **Hierarchical memory** (working/project/long-term/episodic)
- **Self-modification** (with checkpointing + rollback)
- **Dual-model hot-swap** (7B for code, 1.5B for simple tasks)
- **Background execution** (async tasks, file watches)
- **Observability** (self-state queries, health checks)
- **Error recovery** (strategy switching, not fixed retries)
- **Direct llama.cpp binding** (no HTTP server)

**7 implementation phases**, each with concrete tasks, testing strategies, and migration notes. Risks mitigated via checkpointing, timeouts, health checks, and opt-in safeguards.
