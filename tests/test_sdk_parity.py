"""SDK parity check — Phase 3 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

sdk-server/src/index.ts and client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts are hand
-duplicated files with nothing enforcing they stay in sync (Phase 0 audit finding #5) — the exact
class of bug that already hit the machine-agent HMAC canonicalization once (Session 13). This
guards against that regression happening again for the provider/language fields.

NOTE ON SCOPE: `tsc` is not installed in this environment (confirmed repeatedly across every
`make gate` run — "'tsc' is not recognized as an internal or external command"), a pre-existing gap
(state/PROGRESS.md Session 14d already flagged the TS SDK isn't type-checked by the gate at all).
This test cannot substitute for real type-checking; it only proves the two files stay byte-
identical and that the fields this phase added are actually present in both. Real `tsc --noEmit`
verification is still an open gap, not fixed here — flagged, not silently worked around.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SDK_SERVER = _ROOT / "sdk-server" / "src" / "index.ts"
_CLIENT_SUBMISSION = (
    _ROOT
    / "client-submission_v2"
    / "sdk"
    / "@awaazlabs-uva"
    / "agents"
    / "src"
    / "index.ts"
)

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


def test_sdk_server_and_client_submission_are_byte_identical():
    server_text = _SDK_SERVER.read_text(encoding="utf-8")
    client_text = _CLIENT_SUBMISSION.read_text(encoding="utf-8")
    assert server_text == client_text, (
        "sdk-server/src/index.ts and the client-submission_v2 copy have drifted apart — "
        "these are meant to be identical (copy one over the other, don't hand-edit both)"
    )


def test_new_provider_fields_present_in_both_sdk_files():
    for path in (_SDK_SERVER, _CLIENT_SUBMISSION):
        text = path.read_text(encoding="utf-8")
        missing = [f for f in _EXPECTED_NEW_FIELDS if f not in text]
        assert missing == [], f"{path}: missing expected fields {missing}"
