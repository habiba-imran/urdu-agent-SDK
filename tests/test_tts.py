"""P3-T02 — TTS fixture cache. A cache miss is a hard LookupError with ZERO network.

Runs under the conftest offline guard, so if `require()` ever tried to reach Uplift the guard would
trip. It must not: the cache read is pure stdlib.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.tts_cache import get, key, require  # noqa: E402


def test_cache_miss_raises_lookuperror_no_network():
    miss_text = "utterance-with-no-committed-fixture-xyz"
    with pytest.raises(LookupError) as e:
        require("v_meklc281", miss_text)
    assert "FIXTURE MISS" in str(e.value)
    assert get("v_meklc281", miss_text) is None


def test_key_is_deterministic_and_distinct():
    assert key("v_meklc281", "hello") == key("v_meklc281", "hello")
    assert key("v_meklc281", "a") != key("v_meklc281", "b")
    assert key("v_other", "a") != key("v_meklc281", "a")
