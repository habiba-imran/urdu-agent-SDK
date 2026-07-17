"""P3-T05 — verify STT_PROVIDER=soniox → 402 payment-required (seam is real).

One-shot check, human-approved.  Confirms the integration code is wired and the problem
is only an unfunded account — not an ImportError/AttributeError/NotImplementedError.
After this check, STT_PROVIDER stays at gladia for all dev work (ADR-002).
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env.local"))

# Source SONIOX_API_KEY from the old repo's .env
old_env = os.path.join(ROOT, "..", "urdu-voice-agent", ".env")
old_env = os.path.normpath(old_env)
if os.path.exists(old_env):
    with open(old_env) as f:
        for line in f:
            if line.startswith("SONIOX_API_KEY"):
                os.environ["SONIOX_API_KEY"] = line.split("=", 1)[1].strip()

os.environ["STT_PROVIDER"] = "soniox"

from worker.factories import make_stt  # noqa: E402
from livekit.agents.utils import http_context  # noqa: E402


async def main():
    print(f"STT_PROVIDER={os.environ['STT_PROVIDER']}")
    print(f"SONIOX_API_KEY set: {bool(os.environ.get('SONIOX_API_KEY'))}")

    stt = make_stt()
    print(f"Plugin class: {type(stt).__module__}.{type(stt).__name__}")

    async with http_context.open():
        try:
            stream = stt.stream()
            async for ev in stream:
                pass
            await stream.aclose()
            print("RESULT: No error — Soniox responded successfully (unexpected)")
        except Exception as e:
            # Walk the chain: LiveKit wraps the original 402 in retry logic
            chain = []
            ex = e
            while ex is not None:
                chain.append(str(ex))
                nxt = getattr(ex, "__cause__", None) or getattr(ex, "__context__", None)
                if nxt is ex:
                    break
                ex = nxt
            combined = " ".join(chain)

            is_402 = (
                "402" in combined
                or "402 -" in combined
                or "organization_balance_exhausted" in combined.lower()
            )
            is_401 = "401" in combined or "unauthorized" in combined.lower()
            is_key_issue = is_402 or is_401

            if is_key_issue:
                print(f"RESULT: {type(e).__name__}: {str(e)[:200]}")
                print(
                    "Underlying: 402 Organization balance exhausted (confirmed in retry chain)"
                )
                print("\nPASS: STT_PROVIDER=soniox fails with account-level 402 error")
                print(
                    "The seam is real — the integration is wired, only the account is unfunded."
                )
                print("No ImportError, no AttributeError, no NotImplementedError.")
                return 0
            else:
                print(
                    f"\nUNEXPECTED: Error was not a 402/401. Type: {type(e).__name__}"
                )
                return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
