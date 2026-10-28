"""Bounded Gladia 1.6.x handshake and explicit unexpected-close propagation."""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlencode

import aiohttp
from livekit.agents import APIConnectionError, APIStatusError, APITimeoutError
from livekit.plugins.gladia.stt import SpeechStream, _build_streaming_config


class ReliableSpeechStream(SpeechStream):
    async def _init_live_session(self) -> dict:
        config = _build_streaming_config(self._opts)
        url = f"{self._base_url}?{urlencode({'region': config.pop('region')})}"
        async with self._session.post(url=url, json=config,
                headers={"X-Gladia-Key": self._api_key},
                timeout=aiohttp.ClientTimeout(total=self._conn_options.timeout)) as response:
            if response.status not in (200, 201):
                raise APIStatusError("Gladia session initialization rejected", status_code=response.status,
                                     retryable=response.status >= 500)
            return await response.json()

    async def _run(self) -> None:
        while True:
            try:
                # REST allocation plus WS handshake share one attempt budget.
                async with asyncio.timeout(self._conn_options.timeout):
                    started = time.perf_counter()
                    info = await self._init_live_session()
                    self._request_id = info["id"]
                    self._ws = await self._session.ws_connect(info["url"])
                self._report_connection_acquired(time.perf_counter() - started, False)
            except TimeoutError as error:
                raise APITimeoutError("Gladia connection deadline exceeded") from error
            tasks = [asyncio.create_task(self._send_audio_task()),
                     asyncio.create_task(self._recv_messages_task()),
                     asyncio.create_task(self._reconnect_event.wait())]
            send, receive, reconnect = tasks
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                if reconnect in done:
                    self._reconnect_event.clear()
                    continue
                if receive in done and not send.done():
                    raise APIConnectionError("Gladia websocket closed while audio input was still open")
                # A normal end_input still needs the final provider messages.
                if send in done and receive not in done:
                    await asyncio.wait_for(receive, self._conn_options.timeout)
                return
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self._audio_duration_collector.flush()
                if self._ws is not None:
                    await self._ws.close()
                    self._ws = None

    def _process_gladia_message(self, data: dict) -> None:
        if data.get("type") == "error":
            raise APIConnectionError("Gladia reported a streaming error")
        super()._process_gladia_message(data)

    async def _recv_messages_task(self) -> None:
        # The upstream receiver catches parser exceptions, including provider errors.
        async for message in self._ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                import json
                self._process_gladia_message(json.loads(message.data))
            elif message.type == aiohttp.WSMsgType.ERROR:
                raise APIConnectionError("Gladia websocket receive failed")
            elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                return
