"""Owned Socket.IO handshake and error-aware request queues for Uplift 1.6.x."""
from __future__ import annotations

import asyncio
import uuid
import socketio
from livekit.agents import APIConnectionError, APIStatusError
from livekit.plugins.upliftai.tts import WebSocketClient, WEBSOCKET_NAMESPACE


class RequestQueue(asyncio.Queue):
    def __init__(self, client, request_id):
        super().__init__()
        self.client, self.request_id = client, request_id

    async def get(self):
        try:
            item = await asyncio.wait_for(super().get(), 6.0)
        except asyncio.CancelledError:
            await self.client.cancel(self.request_id)
            raise
        except TimeoutError as error:
            await self.client.cancel(self.request_id)
            raise APIConnectionError("Uplift audio progress deadline exceeded") from error
        if isinstance(item, Exception):
            raise item
        return item


class ReliableWebSocketClient(WebSocketClient):
    def __init__(self, opts):
        super().__init__(opts)
        self._connect_lock = asyncio.Lock()
        self._ready = asyncio.Event()

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self.connected and self.sio is not None and self.sio.connected:
                return True
            await self.disconnect()
            self._ready.clear()
            self.sio = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)
            self.sio.on("message", self._on_message, namespace=WEBSOCKET_NAMESPACE)
            self.sio.on("connect", self._on_connect, namespace=WEBSOCKET_NAMESPACE)
            self.sio.on("disconnect", self._on_disconnect, namespace=WEBSOCKET_NAMESPACE)
            try:
                async with asyncio.timeout(5.0):
                    await self.sio.connect(self.opts.base_url, auth={"token": self.opts.api_key},
                        namespaces=[WEBSOCKET_NAMESPACE], transports=["websocket"], wait_timeout=5)
                    await self._ready.wait()
                return True
            except BaseException:
                await self.disconnect()
                raise

    async def synthesize(self, text: str, request_id: str | None = None):
        await self.connect()
        request_id = request_id or str(uuid.uuid4())
        queue = RequestQueue(self, request_id)
        self.audio_callbacks[request_id] = queue
        self.active_requests[request_id] = True
        message = {"type": "synthesize", "requestId": request_id, "text": text,
            "voiceId": self.opts.voice_settings.voice_id,
            "outputFormat": self.opts.voice_settings.output_format}
        if self.opts.phrase_replacement_config_id:
            message["phraseReplacementConfigId"] = self.opts.phrase_replacement_config_id
        try:
            await asyncio.wait_for(self.sio.emit("synthesize", message,
                namespace=WEBSOCKET_NAMESPACE), 5.0)
        except BaseException:
            await self.cancel(request_id)
            raise
        return queue

    async def cancel(self, request_id: str) -> None:
        if self.audio_callbacks.pop(request_id, None) is not None:
            self.active_requests.pop(request_id, None)
            # Closing the session socket stops abandoned work without assuming an
            # undocumented server cancellation event. The next request reconnects.
            await self.disconnect()

    async def disconnect(self) -> None:
        socket, self.sio = self.sio, None
        self.connected = False
        self._ready.clear()
        try:
            if socket is not None:
                await asyncio.wait_for(socket.disconnect(), 1.0)
        finally:
            await self._on_disconnect()

    async def _on_disconnect(self, *args) -> None:
        self.connected = False
        self._ready.clear()
        for queue in self.audio_callbacks.values():
            queue.put_nowait(APIConnectionError("Uplift websocket disconnected before audio_end"))
        self.audio_callbacks.clear()
        self.active_requests.clear()

    async def _on_message(self, data) -> None:
        if not isinstance(data, dict):
            return
        if data.get("type") == "ready":
            self.connected = True
            self._ready.set()
            return
        if data.get("type") == "error":
            request_id = data.get("requestId")
            status = data.get("statusCode") or data.get("status")
            try:
                status = int(status)
            except (ValueError, TypeError):
                status = 500
            error = APIStatusError("Uplift synthesis rejected", status_code=status, retryable=False)
            keys = [request_id] if request_id in self.audio_callbacks else list(self.audio_callbacks)
            for key in keys:
                self.audio_callbacks.pop(key).put_nowait(error)
                self.active_requests.pop(key, None)
            return
        await super()._on_message(data)
