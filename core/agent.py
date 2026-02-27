import json
import re
from core.inference import infer
from core.context import build_file_context_block, auto_load_from_prompt, list_loaded
from core.project import get_project_summary
from prompts.system_prompt import SYSTEM_PROMPT
from tools.file_tools import tool_read_file, tool_write_file, tool_append_file, tool_list_dir
from tools.shell_tools import shell, search_files
from utils.logger import tool_call, tool_result, warning, separator
from utils.config import AGENT_CONFIG

TOOLS = {
    "read_file":    lambda args: tool_read_file(args["path"]),
    "write_file":   lambda args: tool_write_file(args["path"], args["content"]),
    "append_file":  lambda args: tool_append_file(args["path"], args["content"]),
    "list_dir":     lambda args: tool_list_dir(args.get("path", ".")),
    "shell":        lambda args: shell(args["command"]),
    "search_files": lambda args: search_files(args["pattern"], args.get("path", ".")),
}

ROGUE_TAG_MAP = {
    "write_file": "write_file", "read_file": "read_file",
    "shell": "shell", "append_file": "append_file",
    "list_dir": "list_dir", "search_files": "search_files",
}

HALLUCINATION_MARKERS = [
    "\nuser\n", "\nUser\n", "\nUSER\n",
    "\nassistant\n", "\nAssistant\n",
    "Tool result:", "Next action or final answer:",
    "<|im_start|>", "<|im_end|>",
]

def clean_response(text: str) -> str:
    for marker in HALLUCINATION_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip()

def extract_json(raw: str) -> dict | None:
    raw = raw.strip()
    depth, end = 0, 0
    for i, ch in enumerate(raw):
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == 0:
        return None
    candidate = raw[:end]

    try:
        return json.loads(candidate)
    except Exception:
        pass

    fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        return json.loads(fixed)
    except Exception:
        pass

    def replace_single_quoted_values(s):
        return re.sub(
            r'("(?:content|command|path|pattern)"\s*:\s*)\'((?:[^\'\\]|\\.)*)\'',
            lambda m: m.group(1) + json.dumps(m.group(2)),
            s
        )

    fixed2 = replace_single_quoted_values(fixed)
    try:
        return json.loads(fixed2)
    except Exception:
        pass

    # Manual extraction fallback
    result = {}
    for key in ["name", "path", "content", "command", "pattern"]:
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', candidate)
        if m:
            try:
                result[key] = bytes(m.group(1), "utf-8").decode("unicode_escape")
            except Exception:
                result[key] = m.group(1)
            continue
        m = re.search(rf'"{key}"\s*:\s*\'((?:[^\'\\]|\\.*)*)\'', candidate)
        if m:
            result[key] = m.group(1)

    if result:
        if "name" in result:
            name = result.pop("name")
            return {"name": name, "args": result}
        return result
    return None

def parse_tool_call(text: str) -> dict | None:
    match = re.search(r"<tool>\s*(\{.*)", text, re.DOTALL)
    if match:
        result = extract_json(match.group(1))
        if result and "name" in result:
            return result
    for tag, canonical in ROGUE_TAG_MAP.items():
        match = re.search(rf"<{tag}>\s*(\{{.*)", text, re.DOTALL)
        if match:
            inner = extract_json(match.group(1))
            if inner:
                if "name" in inner:
                    return inner
                return {"name": canonical, "args": inner}
    return None

def execute_tool(tool_dict: dict) -> str:
    name = tool_dict.get("name", "")
    args = tool_dict.get("args", {})
    tool_call(name, args)
    if name not in TOOLS:
        return f"[ERROR] Unknown tool: {name}"
    try:
        result = TOOLS[name](args)
        tool_result(result)
        return result
    except Exception as e:
        return f"[ERROR] {e}"

def is_error(result: str, tool_name: str) -> bool:
    if tool_name != "shell":
        return False
    if "[cancelled]" in result.lower():
        return False
    error_signals = [
        "traceback", "syntaxerror", "nameerror", "typeerror",
        "importerror", "modulenotfounderror", "indentationerror",
        "attributeerror", "valueerror", "filenotfounderror",
        "permissionerror", "error:", "exception:", "failed",
        "command not found", "no such file",
    ]
    return any(s in result.lower() for s in error_signals)

def build_system_prompt() -> str:
    parts = [SYSTEM_PROMPT]

    proj = get_project_summary()
    if proj:
        parts.append(f"\nProject context:\n{proj}")

    file_ctx = build_file_context_block()
    if file_ctx:
        parts.append(f"\nLoaded files:\n{file_ctx}")

    return "\n".join(parts)

def enrich_message(user_message: str) -> str:
    loaded = list_loaded()
    if not loaded:
        return user_message
    fix_keywords = ["fix", "correct", "bug", "wrong", "error", "broken",
                    "update", "change", "edit", "modify"]
    if any(kw in user_message.lower() for kw in fix_keywords):
        return (
            f"{user_message}\n\n"
            f"Files loaded: {', '.join(loaded)}. "
            f"Read them above. Write the COMPLETE corrected file."
        )
    return user_message

def run_agent(user_message: str, history: list, yolo: bool = False):
    auto_load_from_prompt(user_message)
    enriched = enrich_message(user_message)

    messages = [{"role": "system", "content": build_system_prompt()}]
    keep = AGENT_CONFIG["history_turns"] * 2
    messages.extend(history[-keep:] if len(history) > keep else history)
    messages.append({"role": "user", "content": enriched})

    step = 0
    max_steps = AGENT_CONFIG["max_steps"]
    tools_used = []
    last_tool_result = ""
    duplicate_count = 0
    auto_retries = 0
    max_retries = 2

    while step < max_steps:
        step += 1

        response = infer(messages, stream=True, extra_stop=["</tool>"])
        response = clean_response(response)
        tool_dict = parse_tool_call(response)

        if tool_dict:
            name = tool_dict.get("name", "")
            args = tool_dict.get("args", {})
            sig = f"{name}:{json.dumps(args, sort_keys=True)}"

            if sig in tools_used:
                duplicate_count += 1
                if duplicate_count >= 2:
                    separator()
                    summary = f"Done. {last_tool_result[:300]}"
                    print(f"\033[1;32mCodey:\033[0m {summary}")
                    separator()
                    history.append({"role": "user",     "content": user_message})
                    history.append({"role": "assistant", "content": summary})
                    return summary, history
                messages.append({"role": "assistant", "content": f'<tool>\n{json.dumps(tool_dict)}\n</tool>'})
                messages.append({
                    "role": "user",
                    "content": f"Already ran that. Result: {last_tool_result[:200]}\nTask complete. Reply with 1 sentence only."
                })
                continue

            tools_used.append(sig)
            last_tool_result = execute_tool(tool_dict)

            if name == "write_file":
                from core.context import load_file
                load_file(args.get("path", ""))

            if is_error(last_tool_result, name) and auto_retries < max_retries:
                auto_retries += 1
                warning(f"Error detected — auto-retry {auto_retries}/{max_retries}")
                messages.append({"role": "assistant", "content": f'<tool>\n{json.dumps(tool_dict)}\n</tool>'})
                messages.append({
                    "role": "user",
                    "content": f"Error:\n{last_tool_result}\n\nFix it. Read the file above and write a corrected version."
                })
                continue

            messages.append({"role": "assistant", "content": f'<tool>\n{json.dumps(tool_dict)}\n</tool>'})
            messages.append({
                "role": "user",
                "content": f"Tool result: {last_tool_result[:500]}\nNext action or final answer:"
            })
            continue

        separator()
        history.append({"role": "user",     "content": user_message})
        history.append({"role": "assistant", "content": response})
        return response, history

    warning(f"Reached max steps ({max_steps}).")
    return "[Max steps reached]", history
