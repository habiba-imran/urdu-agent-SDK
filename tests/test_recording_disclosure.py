"""Unit tests for F-C4 Phase C recording disclosure (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker.recording_disclosure import (
    recording_disclosure_text,
    reset_consent_column_probe,
    speak_recording_disclosure_if_needed,
)
from worker.recording_policy import (
    CONSENT_GRANTED,
    CONSENT_NOT_APPLICABLE,
    CONSENT_PENDING,
)


@pytest.fixture(autouse=True)
def _reset_probe() -> None:
    reset_consent_column_probe()


def test_disclosure_text_english_default() -> None:
    text = recording_disclosure_text("en")
    assert "recorded" in text.lower()
    assert "agree" in text.lower()


def test_disclosure_text_urdu() -> None:
    text = recording_disclosure_text("ur")
    assert "ریکارڈ" in text
    assert text != recording_disclosure_text("en")


@pytest.mark.asyncio
async def test_no_disclosure_when_recording_may_start_false() -> None:
    class Sess:
        def __init__(self) -> None:
            self.said = None
            self.userdata = SimpleNamespace(
                recording_may_start=False,
                recording_consent_status=CONSENT_NOT_APPLICABLE,
            )

        def say(self, text: str, **kwargs: object):
            self.said = text
            raise AssertionError("say must not be called")

    sess = Sess()
    ok = await speak_recording_disclosure_if_needed(
        sess,
        agent_language="en",
        room_name="r1",
        logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
    )
    assert ok is False
    assert sess.userdata.recording_consent_status == CONSENT_NOT_APPLICABLE


@pytest.mark.asyncio
async def test_disclosure_before_grant_on_playout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[tuple[str, str]] = []

    def _fake_persist(*, room_name: str, status: str, consented_at=None) -> bool:
        persisted.append((room_name, status))
        return True

    monkeypatch.setattr(
        "worker.recording_disclosure.persist_recording_consent", _fake_persist
    )

    class Handle:
        interrupted = False

        async def wait_for_playout(self) -> None:
            return None

    class Sess:
        def __init__(self) -> None:
            self.say_calls: list[tuple[str, dict]] = []
            self.userdata = SimpleNamespace(
                recording_may_start=True,
                recording_consent_status=CONSENT_PENDING,
                recording_consent_at=None,
            )

        def say(self, text: str, **kwargs: object):
            self.say_calls.append((text, kwargs))
            return Handle()

    sess = Sess()
    logs: list[str] = []
    ok = await speak_recording_disclosure_if_needed(
        sess,
        agent_language="en",
        room_name="room-x",
        logger=SimpleNamespace(
            info=lambda *a, **k: logs.append(str(a)),
            warning=lambda *a, **k: None,
        ),
    )
    assert ok is True
    assert len(sess.say_calls) == 1
    assert sess.say_calls[0][1].get("allow_interruptions") is False
    assert "recorded" in sess.say_calls[0][0].lower()
    assert sess.userdata.recording_consent_status == CONSENT_GRANTED
    assert sess.userdata.recording_consent_at
    assert persisted == [("room-x", CONSENT_GRANTED)]


@pytest.mark.asyncio
async def test_disclosure_interrupted_keeps_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "worker.recording_disclosure.persist_recording_consent",
        lambda **kwargs: True,
    )

    class Handle:
        interrupted = True

        async def wait_for_playout(self) -> None:
            return None

    class Sess:
        def __init__(self) -> None:
            self.userdata = SimpleNamespace(
                recording_may_start=True,
                recording_consent_status=CONSENT_PENDING,
                recording_consent_at=None,
            )

        def say(self, text: str, **kwargs: object):
            return Handle()

    sess = Sess()
    ok = await speak_recording_disclosure_if_needed(
        sess,
        agent_language="en",
        room_name="r2",
        logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
    )
    assert ok is False
    assert sess.userdata.recording_consent_status == CONSENT_PENDING


@pytest.mark.asyncio
async def test_disclosure_arms_opening_active_during_playout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telephony force barge-in skips when opening_active (same shield as greeting)."""
    monkeypatch.setattr(
        "worker.recording_disclosure.persist_recording_consent",
        lambda **kwargs: True,
    )
    flags: list[bool] = []

    class Handle:
        interrupted = False

        async def wait_for_playout(self) -> None:
            # Observed mid-playout by the fake session userdata.
            return None

    class Sess:
        def __init__(self) -> None:
            self.userdata = SimpleNamespace(
                recording_may_start=True,
                recording_consent_status=CONSENT_PENDING,
                recording_consent_at=None,
                opening_active=False,
            )

        def say(self, text: str, **kwargs: object):
            flags.append(bool(self.userdata.opening_active))
            return Handle()

    sess = Sess()
    ok = await speak_recording_disclosure_if_needed(
        sess,
        agent_language="en",
        room_name="r4",
        logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
    )
    assert ok is True
    assert flags == [True]
    assert sess.userdata.opening_active is False


@pytest.mark.asyncio
async def test_disclosure_runs_for_user_first_speaker_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """first_speaker=user still gets disclosure when recording_may_start (plan C.2)."""
    monkeypatch.setattr(
        "worker.recording_disclosure.persist_recording_consent",
        lambda **kwargs: True,
    )

    class Handle:
        interrupted = False

        async def wait_for_playout(self) -> None:
            return None

    class Sess:
        def __init__(self) -> None:
            self.said = None
            self.userdata = SimpleNamespace(
                recording_may_start=True,
                recording_consent_status=CONSENT_PENDING,
                recording_consent_at=None,
                opening_active=False,
            )

        def say(self, text: str, **kwargs: object):
            self.said = text
            return Handle()

    sess = Sess()
    ok = await speak_recording_disclosure_if_needed(
        sess,
        agent_language="ur",
        room_name="r3",
        logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
    )
    assert ok is True
    assert sess.said is not None
    assert "ریکارڈ" in sess.said
    assert sess.userdata.recording_consent_status == CONSENT_GRANTED
