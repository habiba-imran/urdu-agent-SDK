# Minimal stub — the old repo used Pipecat's FunctionSchema for tool definitions.
# In this repo, tools.py only needs the schema shape for the CER harness tests
# (build_tools_schema) and register_tools. LiveKit Agents has its own equivalent.

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FunctionSchema:
    name: str
    description: str
    properties: dict[str, Any]
    required: list[str]
