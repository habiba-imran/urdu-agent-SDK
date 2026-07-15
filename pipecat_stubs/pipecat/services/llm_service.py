# Minimal stub — tools.py imports FunctionCallParams from this module.
# In production (Phase 3), this will be replaced with the LiveKit Agents equivalent.


class FunctionCallParams:
    def __init__(self):
        self.arguments: dict = {}
        self.function_name: str = ""

    async def result_callback(self, result):
        pass
