# Pytest-compatible test wrappers for the CER harness ported from the old Pipecat repo.
# Each wrapper imports the original test module and calls its async run() function.

import asyncio
import pytest


def _runner(module_name: str):
    """Import a test module and run its async run(), returning the Check object."""
    import importlib

    module = importlib.import_module(module_name)
    check = asyncio.run(module.run())
    return check


class TestCERHarness:
    """CER harness tests ported from the old Pipecat repo.

    P0-T08 acceptance: these tests must be collected by pytest --collect-only
    and exercise the real persona.py, tools.py, db.py logic against live
    external services (or their fixture equivalents).
    """

    def test_schema(self):
        """Schema test: all tables exist with correct seed counts."""
        check = _runner("test_schema")
        assert check.passed, (
            f"Schema check failed: {[(label, d) for label, ok, d in check.results if not ok]}"
        )

    def test_tools(self):
        """Tool unit tests: every tool handler, validation, timeout path."""
        check = _runner("test_tools")
        assert check.passed, (
            f"Tool check failed: {[(label, d) for label, ok, d in check.results if not ok]}"
        )

    def test_e2e(self):
        """E2E loop: 8 Urdu utterances through real LLM + tools + Mahnoor persona."""
        check = _runner("test_e2e")
        assert check.passed, (
            f"E2E check failed: {[(label, d) for label, ok, d in check.results if not ok]}"
        )

    def test_env_smoke(self):
        """Env smoke: one real call to every external dependency."""
        check = _runner("test_env_smoke")
        assert check.passed, (
            f"Env smoke failed: {[(label, d) for label, ok, d in check.results if not ok]}"
        )

    def test_stt_accuracy(self):
        """STT accuracy: Soniox vs Gladia vs Whisper CER measurement."""
        check = _runner("test_stt_accuracy")
        assert check.passed, (
            f"STT accuracy failed: {[(label, d) for label, ok, d in check.results if not ok]}"
        )


@pytest.mark.skip(
    reason="Pipeline harness requires bot.py + Pipecat (not ported per 11-ARCHITECTURE.md)"
)
class TestPipelineHarness:
    """Pipeline-level tests that require the full Pipecat stack. Skipped until Phase 3."""

    def test_interruption(self):
        pass

    def test_latency(self):
        pass
