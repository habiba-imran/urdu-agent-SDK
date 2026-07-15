from dataclasses import dataclass, field

from .function_schema import FunctionSchema


@dataclass
class ToolsSchema:
    standard_tools: list[FunctionSchema] = field(default_factory=list)
