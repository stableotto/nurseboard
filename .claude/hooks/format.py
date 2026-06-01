#!/usr/bin/env python3
"""PostToolUse hook: auto-format the file Claude just edited.

Boris-style: Claude's output is usually well-formatted; this fixes the last
10% so you don't fail CI on formatting later. It gracefully no-ops if the
relevant formatter isn't installed, so it's safe to copy into any project.

Wired up via .claude/settings.json (PostToolUse, matcher Edit|Write|MultiEdit).
"""
import json
import os
import shutil
import subprocess
import sys


def _run(cmd):
    try:
        subprocess.run(cmd, check=False, capture_output=True)
    except Exception:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    path = (data.get("tool_input") or {}).get("file_path")
    if not path or not os.path.isfile(path):
        return

    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        if shutil.which("ruff"):
            _run(["ruff", "format", path])
        elif shutil.which("black"):
            _run(["black", "-q", path])
    elif ext in (".js", ".mjs", ".cjs", ".ts", ".json", ".css", ".html", ".md"):
        if shutil.which("prettier"):
            _run(["prettier", "--write", path])
        elif shutil.which("npx"):
            _run(["npx", "--no-install", "prettier", "--write", path])


if __name__ == "__main__":
    main()
