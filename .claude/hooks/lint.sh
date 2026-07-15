#!/usr/bin/env bash
IN=$(cat); FILE=$(printf '%s' "$IN" | jq -r '.tool_input.file_path // ""')
case "$FILE" in *.py) ruff check --fix "$FILE" 2>&1 | head -20 ;; *.ts|*.tsx) npx --no-install prettier -w "$FILE" 2>/dev/null ;; esac
exit 0
