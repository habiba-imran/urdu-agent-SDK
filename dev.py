#!/usr/bin/env python3
"""Local Dev Orchestration Script.

Launches both the control plane (FastAPI) and the voice worker (LiveKit Agent)
concurrently in a single terminal, intercepts and prefixes their logs for easy
debugging, and handles graceful shutdown (Ctrl+C / SIGINT) of both processes.
"""

import os
import sys
import signal
import subprocess
import threading
import time
from pathlib import Path

# Define project root and check for .env.local
ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env.local"

# ANSI Terminal Colors
COLOR_RESET = "\033[0m"
COLOR_CP = "\033[36m"      # Cyan for Control Plane
COLOR_WK = "\033[35m"      # Magenta for Voice Worker
COLOR_SYS = "\033[33;1m"   # Bold Yellow for Orchestrator
COLOR_ERR = "\033[31;1m"   # Bold Red for Errors

def log_sys(msg: str):
    print(f"{COLOR_SYS}[Orchestrator] {msg}{COLOR_RESET}")

def log_err(msg: str):
    print(f"{COLOR_ERR}[Orchestrator ERROR] {msg}{COLOR_RESET}", file=sys.stderr)

def check_env():
    if not ENV_FILE.exists():
        log_err(f"File '.env.local' not found at {ENV_FILE}")
        log_sys("Please copy '.env.example' to '.env.local' and configure your LiveKit, Supabase, and AI keys.")
        sys.exit(1)
    
    # Read and parse key env vars for warnings
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    vars_dict = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            vars_dict[k.strip()] = v.strip()
            
    required = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "SUPABASE_DB_URL"]
    missing = [r for r in required if not vars_dict.get(r)]
    if missing:
        log_err(f"Missing required environment variables in .env.local: {', '.join(missing)}")
        sys.exit(1)

def log_pipe(stream, prefix, color):
    """Read a stream line-by-line and print it with a color-coded prefix."""
    try:
        for line in iter(stream.readline, b""):
            decoded = line.decode("utf-8", errors="replace").rstrip()
            print(f"{color}{prefix} | {decoded}{COLOR_RESET}")
    except Exception as e:
         pass

def main():
    check_env()
    log_sys("Environment validation passed. Starting services...")
    log_sys(f"Interactive Sandbox available at: {COLOR_SYS}http://localhost:7860/static/dev_sandbox.html{COLOR_RESET}")

    # Set up environment (ensure ROOT is in PYTHONPATH)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    processes = []
    
    # 1. Start Control Plane (FastAPI / Uvicorn)
    cp_cmd = [sys.executable, "-m", "uvicorn", "control_plane.app:app", "--host", "0.0.0.0", "--port", "7860", "--reload"]
    log_sys(f"Launching Control Plane (Port 7860)...")
    cp_proc = subprocess.Popen(
        cp_cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )
    processes.append((cp_proc, "Control Plane", COLOR_CP))

    # 2. Start Voice Worker (LiveKit runner in dev mode)
    wk_cmd = [sys.executable, "-m", "worker.main", "dev"]
    log_sys(f"Launching Voice Worker (LiveKit dev mode)...")
    wk_proc = subprocess.Popen(
        wk_cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )
    processes.append((wk_proc, "Voice Worker", COLOR_WK))

    # Start thread log relays
    threads = []
    for proc, name, color in processes:
        t_out = threading.Thread(target=log_pipe, args=(proc.stdout, name, color), daemon=True)
        t_err = threading.Thread(target=log_pipe, args=(proc.stderr, name, color), daemon=True)
        t_out.start()
        t_err.start()
        threads.extend([t_out, t_err])

    # Graceful shutdown handler
    shutdown_event = threading.Event()
    
    def handle_sigint(signum, frame):
        log_sys("SIGINT/Ctrl+C received. Terminating processes gracefully...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    # Monitor processes
    try:
        while not shutdown_event.is_set():
            # Check if any process exited prematurely
            for proc, name, _ in processes:
                ret = proc.poll()
                if ret is not None:
                    log_err(f"Process [{name}] exited unexpectedly with code {ret}.")
                    shutdown_event.set()
                    break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        # Terminate processes
        for proc, name, _ in processes:
            if proc.poll() is None:
                log_sys(f"Stopping [{name}]...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    log_sys(f"Force-killing [{name}]...")
                    proc.kill()
                    proc.wait()
        log_sys("All processes terminated. Goodbye!")

if __name__ == "__main__":
    main()
