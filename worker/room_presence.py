"""Read-only room evidence for orphan cleanup; unknown never means disconnected."""
from __future__ import annotations
import asyncio
import os
import logging

log = logging.getLogger("worker.room_presence")


def room_is_active(room_name: str) -> bool | None:
    from livekit import api
    async def check():
        client = api.LiveKitAPI(url=os.getenv("LIVEKIT_URL"), api_key=os.getenv("LIVEKIT_API_KEY"),
                                api_secret=os.getenv("LIVEKIT_API_SECRET"))
        try:
            response = await asyncio.wait_for(client.room.list_participants(
                api.ListParticipantsRequest(room=room_name)), 5.0)
            # A caller without a functioning worker is an orphan too. Requiring a
            # worker avoids treating an abandoned phone leg as a healthy voice call.
            return any(p.kind == 4 for p in response.participants)
        except api.TwirpError as error:
            if error.code == "not_found":
                return False
            raise
        finally:
            await client.aclose()
    try:
        return asyncio.run(check())
    except Exception:
        log.warning("orphan_presence_unknown room=%s", room_name, exc_info=True)
        return None
