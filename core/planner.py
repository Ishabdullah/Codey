"""
Plan mode — think before acting on complex tasks.
Codey writes a short plan, user approves, then executes.
"""
from utils.logger import console, info, warning, separator

PLAN_SYSTEM_PROMPT = """You are Codey's planning module. When given a task, write a concise action plan.

Format your plan as numbered steps. Each step should be ONE specific action:
- "Create file X with Y"
- "Edit function Z in file A to do B"  
- "Run command C to verify"

Rules:
- Maximum 6 steps
- Be specific about filenames and what changes
- No code, no tool calls — just the plan
- End with: "Ready to execute."

Example:
1. Create calculator.py with add, subtract, multiply, divide functions
2. Add input validation to each function
3. Run python3 calculator.py to verify no syntax errors
Ready to execute.
"""

# Keywords that suggest a complex multi-step task
COMPLEX_TASK_SIGNALS = [
    "create", "build", "implement", "add", "refactor", "rewrite",
    "and then", "then run", "also", "with tests", "multiple",
    "class", "module", "app", "application", "system",
]

def is_complex(user_message: str) -> bool:
    """Heuristic: does this message look like a multi-step task?"""
    msg = user_message.lower()
    # Long messages are usually complex
    if len(user_message) > 120:
        return True
    # Multiple action words
    signals = sum(1 for s in COMPLEX_TASK_SIGNALS if s in msg)
    return signals >= 2

def get_plan(user_message: str, system_context: str = "") -> str:
    """Ask the model to plan before executing."""
    from core.inference import infer
    messages = [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT + (f"\n\nProject context:\n{system_context}" if system_context else "")},
        {"role": "user",   "content": f"Plan this task: {user_message}"}
    ]
    from utils.logger import console, info
    info("Generating plan...")
    result = infer(messages, stream=False)
    return result

def show_and_confirm_plan(plan: str) -> bool:
    """
    Display the plan to the user and ask for approval.
    Returns True if approved, False if rejected.
    """
    separator()
    console.print("[bold cyan]📋 Plan:[/bold cyan]")
    for line in plan.splitlines():
        if line.strip():
            console.print(f"  {line}")
    separator()
    try:
        ans = input("Execute this plan? [Y/n/edit]: ").strip().lower()
        if ans in ("", "y", "yes"):
            return True, plan
        elif ans in ("n", "no"):
            info("Plan rejected. Type a different task or refine your request.")
            return False, plan
        else:
            # User wants to edit — let them type a revised instruction
            revised = input("Revised instruction: ").strip()
            return True, revised
    except (KeyboardInterrupt, EOFError):
        return False, plan
