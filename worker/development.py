"""Explicit isolated development launcher. Does not change shared/production defaults."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import runpy
import sys

PROVIDERS = ("cartesia", "rime", "elevenlabs", "uplift")


def configure(agent_name: str, *, environ=None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    if not re.fullmatch(r"uva-humanization-dev-[a-z0-9][a-z0-9-]{2,48}", agent_name):
        raise ValueError("Use a unique uva-humanization-dev-<name> dispatch; shared names are rejected")
    values = {
        "LIVEKIT_AGENT_NAME": agent_name,
        "UVA_HUMANIZATION_POLICY_VERSION": "conversational_v1",
        "UVA_OVERLAP_POLICY": "overlap_v1",
        "UVA_OPENING_POLICY": "opening_v1",
        "UVA_PUBLISH_TURN_LATENCY": "1",
    }
    for provider in PROVIDERS:
        values["UVA_TTS_RENDERER_" + provider.upper()] = "delivery_v1"
        values["UVA_TTS_STREAMING_" + provider.upper()] = "streaming_v1"
    env.update(values)
    return values


def validate_installed() -> None:
    for package in ("livekit-agents", "livekit-plugins-cartesia", "livekit-plugins-rime",
                    "livekit-plugins-elevenlabs", "livekit-plugins-upliftai"):
        if importlib.metadata.version(package) != "1.6.5":
            raise RuntimeError(f"{package} must remain at the audited 1.6.5; no dependency upgrade")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("worker", "control-plane"))
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--check", action="store_true", help="resolve flags only; no worker, network or synthesis")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(".env.local", override=False)
    values = configure(args.agent_name)
    validate_installed()
    from .humanization.policy import resolve_humanization_policy
    assert resolve_humanization_policy().behavior_enabled
    print(json.dumps({"development_profile": values, "target": args.target}, sort_keys=True))
    if args.check:
        return
    if args.target == "worker":
        # Fresh process imports all updated code after profile application.
        sys.argv = ["worker.main", "dev"]
        runpy.run_module("worker.main", run_name="__main__")
    else:
        import uvicorn
        uvicorn.run("control_plane.app:app", host="127.0.0.1", port=8100)


if __name__ == "__main__":
    main()
