#!/usr/bin/env python3
"""Local Worker Watchdog Runner with Automatic Crash Recovery.

Runs `python -m worker.main dev` in a continuous auto-restart loop.
If the underlying Windows Rust WebRTC binding panics during room teardown
(`malformed serialized RtcError`), this watchdog instantly revives the worker
within 1 second so you never have to manually restart it in your terminal.

Usage:
    python scripts/dev_worker.py
"""

import subprocess
import sys
import time


def main():
    print("==================================================================")
    print("      LIVEKIT WORKER WATCHDOG — AUTO-RESTART ENABLED              ")
    print("==================================================================")
    print("Press Ctrl+C at any time to stop the worker.\n")

    restart_count = 0

    while True:
        try:
            # Run worker in dev mode
            res = subprocess.run([sys.executable, "-m", "worker.main", "dev"])
            restart_count += 1
            print(f"\n🔄 Worker exited (code {res.returncode}). Auto-restarting watchdog (attempt #{restart_count})...")
            time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n🛑 Worker watchdog stopped by user.")
            break


if __name__ == "__main__":
    main()
