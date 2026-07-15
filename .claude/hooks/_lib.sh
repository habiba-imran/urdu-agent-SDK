#!/usr/bin/env bash
# Shared JSON field extraction. FAILS CLOSED.
# A guard hook that fails open when a dependency is missing is worse than no guard.
json_field() { # $1=json  $2=field
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$1" | jq -r ".tool_input.$2 // \"\"" 2>/dev/null && return 0
  fi
  # jq-free fallback: extract "field":"value"
  printf '%s' "$1" | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p"
}
