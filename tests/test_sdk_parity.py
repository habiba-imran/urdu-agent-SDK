"""Server SDK provider/language field check (ADR-036 Phase 3).

HISTORY: this file used to assert that `sdk-server/src/index.ts` and a hand-duplicated copy
at `client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts` were byte-identical, because
two hand-maintained copies had already drifted once and broken machine-agent HMAC
canonicalization.

That second copy no longer exists — commit 62b2eb3 replaced client-submission_v2 with
`client-deliverables-final/`, which points integrators at the published
`@awaazlabs-uva/agents` package instead of shipping a source copy. There is now exactly one
source of truth, so the duplication this guarded against cannot happen, and the byte-identity
test was failing purely on a missing path (it never ran: F-H1's whitelist hid it).

What is still worth checking — that the provider/language fields ADR-036 added are actually
present in the published SDK's source — is kept below.

Real type-checking is no longer the gap the old docstring described: `npm test` in
sdk-server/ builds with tsc and runs the signing/contract suite (audit §2 item 26).
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SDK_SERVER = _ROOT / "sdk-server" / "src" / "index.ts"

_EXPECTED_NEW_FIELDS = (
    "agentLanguage",
    "sttProvider",
    "sttModel",
    "sttOptions",
    "llmProvider",
    "llmOptions",
    "ttsProvider",
    "ttsVoiceId",
    "ttsOptions",
)


def test_sdk_server_is_the_single_source_of_truth():
    """No second hand-maintained copy of the agents SDK source should reappear."""
    duplicates = [
        p
        for p in _ROOT.rglob("index.ts")
        if "@awaazlabs-uva" in str(p)
        and "agents" in str(p)
        and "node_modules" not in str(p)
    ]
    assert duplicates == [], (
        "a second copy of the agents SDK source has appeared "
        f"({duplicates}) — integrators should consume the published package, and drift "
        "between copies has already broken HMAC canonicalization once"
    )


def test_new_provider_fields_present_in_the_server_sdk():
    text = _SDK_SERVER.read_text(encoding="utf-8")
    missing = [f for f in _EXPECTED_NEW_FIELDS if f not in text]
    assert missing == [], f"{_SDK_SERVER}: missing expected fields {missing}"
