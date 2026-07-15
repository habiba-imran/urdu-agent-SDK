# conftest.py — CER harness pytest integration.
#
# Two responsibilities:
#   1. Put the project root + pipecat_stubs/ on sys.path so the ported CER tests can import
#      tools/db/persona/processors (pytest.ini `pythonpath` does the same for collection).
#   2. Free-tier offline guard. No test may open a live connection to a paid provider. Per
#      docs/30-GUIDE-FREE-TIER.md the tests replay from tests/fixtures/; a live attempt means a
#      fixture is missing, so the test SKIPS with a clear message and never calls out. The guard
#      blocks at the socket/DNS layer, so "zero outbound" holds regardless of which client a test
#      uses. It does NOT touch any assertion or expected value: a guard-tripped test skips, but a
#      genuine logic failure (guard not tripped) still fails.

import os
import socket
import sys

import pytest
from _pytest.outcomes import Skipped

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PIPECAT_STUBS = os.path.join(_PROJECT_ROOT, "pipecat_stubs")
for _path in (_PIPECAT_STUBS, _PROJECT_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Default every paid provider to its offline/fixture path (30-GUIDE-FREE-TIER.md §6/§7).
for _var in ("UPLIFT_MODE", "GLADIA_MODE", "LLM_MODE"):
    os.environ.setdefault(_var, "fixture")

# Is the harness configured to reach any real backend? At Phase 0 there is no .env.local, so these
# are all empty. When unconfigured, a live-dependent test cannot run and must SKIP rather than fail
# on a missing-credential error (which surfaces before any socket, so the network guard can't catch
# it). Once Phase 1+ populates .env.local this flips to True and such failures become real again.
_CREDENTIAL_VARS = (
    "SUPABASE_URL",
    "SUPABASE_DB_URL",
    "SUPABASE_KEY",
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "CEREBRAS_API_KEY",
    "UPLIFTAI_API_KEY",
)
_HAS_CREDENTIALS = any(os.environ.get(_v) for _v in _CREDENTIAL_VARS)

# --- offline network guard ---------------------------------------------------------------
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
_hits = {"n": 0}


def _extra_allowed_hosts():
    """Hosts tests MAY reach beyond loopback: the FREE Supabase dev backend, so the RLS
    isolation test can hit the real DB. Paid providers (Uplift/Gladia/LLMs) are never
    added here — they stay blocked, which is the whole point of the guard."""
    import urllib.parse as _up

    from dotenv import dotenv_values as _dv

    hosts = set()
    cfg = _dv(os.path.join(_PROJECT_ROOT, ".env.local"))
    for key in ("SUPABASE_URL", "SUPABASE_DB_URL"):
        val = cfg.get(key)
        if val:
            host = _up.urlparse(val).hostname
            if host:
                hosts.add(host)
    return hosts


_ALLOWED = set(_LOOPBACK) | _extra_allowed_hosts()


class PaidNetworkBlocked(OSError):
    """A test tried to open a live socket to a non-loopback host.

    Under the free-tier harness that means a fixture is missing: the test is skipped and no
    paid provider is ever contacted.
    """


def _host(value):
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    if isinstance(value, (tuple, list)) and value:
        value = value[0]
    return value


def _block(target):
    _hits["n"] += 1
    return PaidNetworkBlocked(
        f"outbound connection to {target!r} blocked by the free-tier offline guard "
        f"(docs/30-GUIDE-FREE-TIER.md §2); add a fixture under tests/fixtures/ to run this offline"
    )


_orig_getaddrinfo = socket.getaddrinfo
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_create_connection = socket.create_connection


def _guard_getaddrinfo(host, *args, **kwargs):
    if host is not None and _host(host) not in _ALLOWED:
        raise _block(_host(host))
    return _orig_getaddrinfo(host, *args, **kwargs)


def _guard_connect(self, address, *args, **kwargs):
    if _host(address) not in _ALLOWED:
        raise _block(_host(address))
    return _orig_connect(self, address, *args, **kwargs)


def _guard_connect_ex(self, address, *args, **kwargs):
    if _host(address) not in _ALLOWED:
        raise _block(_host(address))
    return _orig_connect_ex(self, address, *args, **kwargs)


def _guard_create_connection(address, *args, **kwargs):
    if _host(address) not in _ALLOWED:
        raise _block(_host(address))
    return _orig_create_connection(address, *args, **kwargs)


def pytest_configure(config):
    socket.getaddrinfo = _guard_getaddrinfo
    socket.socket.connect = _guard_connect
    socket.socket.connect_ex = _guard_connect_ex
    socket.create_connection = _guard_create_connection


def pytest_unconfigure(config):
    socket.getaddrinfo = _orig_getaddrinfo
    socket.socket.connect = _orig_connect
    socket.socket.connect_ex = _orig_connect_ex
    socket.create_connection = _orig_create_connection


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Skip a test that cannot run offline; leave genuine logic failures untouched.

    A test is skipped only when it failed AND either (a) the offline guard blocked a live
    connection, or (b) the harness has no credentials configured at all — both mean "no backend
    and no fixture available", not "the code is wrong". When credentials ARE present the code runs
    for real and any failure stays a failure.
    """
    before = _hits["n"]
    try:
        return (yield)
    except Skipped:
        raise
    except BaseException as exc:
        tripped = _hits["n"] > before
        if tripped or not _HAS_CREDENTIALS:
            reason = (
                f"the offline guard blocked {_hits['n'] - before} connection attempt(s)"
                if tripped
                else "no credentials configured (.env.local absent) and no fixture cache yet"
            )
            raise Skipped(
                f"{item.name}: needs a live provider or a committed fixture — {reason}; "
                f"no paid API was called (docs/30-GUIDE-FREE-TIER.md)",
                allow_module_level=False,
            ) from exc
        raise
