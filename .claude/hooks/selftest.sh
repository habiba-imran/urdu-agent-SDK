#!/usr/bin/env bash
# P0-T05 gate: every BLOCK case must exit 2.
pass=0; fail=0
t(){ out=$(printf '%s' "$2" | .claude/hooks/$1 >/dev/null 2>&1; echo $?)
     if [ "$out" = "$3" ]; then pass=$((pass+1)); else echo "FAIL: $1 <- $2 (got $out want $3)"; fail=$((fail+1)); fi; }
t guard-bash.sh '{"tool_input":{"command":"rm -rf /tmp/x"}}' 2
t guard-bash.sh '{"tool_input":{"command":"git push origin main"}}' 2
t guard-bash.sh '{"tool_input":{"command":"git push origin HEAD:main"}}' 2
t guard-bash.sh '{"tool_input":{"command":"git push -f origin master"}}' 2
t guard-bash.sh '{"tool_input":{"command":"git push origin phase/3-worker"}}' 0
t guard-bash.sh '{"tool_input":{"command":"echo $SERVICE_ROLE_KEY"}}' 2
t guard-bash.sh '{"tool_input":{"command":"UPLIFT_MODE=live python x.py"}}' 2
t guard-bash.sh '{"tool_input":{"command":"pip install twilio"}}' 2
t guard-bash.sh '{"tool_input":{"command":"git reset --hard HEAD~1"}}' 2
t guard-bash.sh '{"tool_input":{"command":"pytest -q"}}' 0
t test-guard.sh  '{"tool_input":{"file_path":"tests/test_tts.py"}}' 2
t test-guard.sh  '{"tool_input":{"file_path":"worker/main.py"}}' 0
echo "selftest: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
