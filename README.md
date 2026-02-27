# Codey v0.1.0
Local AI coding assistant for Termux using Qwen2.5-Coder-7B.

## Requirements
- llama.cpp built at ~/llama.cpp/build/bin/
- Model at ~/models/qwen2.5-coder-7b/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf
- pip install rich

## Usage
    codey "task"              # one-shot
    codey --yolo "task"       # no confirmations
    codey                     # interactive chat
    codey --chat "task"       # chat with prefilled prompt

## Chat commands
    /exit    quit
    /clear   clear history
    /cwd     show/change directory
    /help    show help

## Environment variables
    CODEY_MODEL    path to GGUF model
    CODEY_THREADS  CPU threads (default 4)
    LLAMA_BIN      path to llama-server binary

## Files created in current working directory
All files Codey creates go in whatever directory you run codey from.
Use /cwd to change it mid-session.
