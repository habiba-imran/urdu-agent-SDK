#!/usr/bin/env python3
"""Local Worker Watchdog Runner with Automatic Crash Recovery.

Runs ``python -m worker.main dev`` in a continuous auto-restart loop.
If the underlying Windows Rust WebRTC binding panics during room teardown
(``malformed serialized RtcError``), this watchdog instantly revives the worker
so you never have to manually restart it.

Usage:
    python scripts/dev_worker.py

Stop: press Ctrl+C twice within 2 seconds (a single Ctrl+C only restarts —
Windows console signals often hit the parent while a call is active).
"""

from __future__ import annotations

import subprocess
import sys
import time


def main() -> None:
    print("==================================================================")
    print("      LIVEKIT WORKER WATCHDOG — AUTO-RESTART ENABLED              ")
    print("==================================================================")
    print("Press Ctrl+C twice within 2s to stop. Single Ctrl+C restarts.\n")

    restart_count = 0
    last_interrupt_at = 0.0
    creationflags = 0
    if sys.platform == "win32":
        # Isolate the child so a console Ctrl+C is handled by the watchdog first
        # instead of racing LiveKit's shutdown while a PSTN call is mid-TTS.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    while True:
        proc: subprocess.Popen[bytes] | None = None
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "worker.main", "dev"],
                creationflags=creationflags,
            )
            returncode = proc.wait()
            restart_count += 1
            print(
                f"\n🔄 Worker exited (code {returncode}). "
                f"Auto-restarting watchdog (attempt #{restart_count})..."
            )
            time.sleep(0.5)
        except KeyboardInterrupt:
            now = time.monotonic()
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=8)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            if now - last_interrupt_at <= 2.0:
                print("\n🛑 Worker watchdog stopped by user.")
                break

            last_interrupt_at = now
            restart_count += 1
            print(
                "\n⚠️  Ctrl+C received — worker stopped. "
                "Press Ctrl+C again within 2s to quit the watchdog, "
                f"or wait for auto-restart (attempt #{restart_count})..."
            )
            time.sleep(0.5)


if __name__ == "__main__":
    main()
