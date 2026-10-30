"""Keep trusted static system text cacheable without changing prompt authority.

The pinned plugin flattens the first system message into one block. Per-turn
guidance appended to that block invalidates its cache. The owned client boundary
restores a breakpoint BEFORE that changing suffix, with identical text/order.
"""
from __future__ import annotations

from contextvars import ContextVar
import os
from typing import Any

PREFIX_KEY = 'awaaz_stable_system_prefix'
system_prefix: ContextVar[str | None] = ContextVar('claude_system_cache_prefix', default=None)


def claude_latency_enabled():
    return os.getenv('UVA_CLAUDE_LOW_LATENCY', '1').strip().lower() not in {'0', 'false', 'off', 'no'}


def context_prefix(context: Any) -> str | None:
    for item in getattr(context, 'items', ()):
        if getattr(item, 'role', None) == 'system':
            prefix = (getattr(item, 'extra', None) or {}).get(PREFIX_KEY)
            text = getattr(item, 'raw_text_content', '') or ''
            if isinstance(prefix, str) and prefix and text.startswith(prefix + '\n\n'):
                return prefix
            return None
    return None


def cache_stable_prefix(request: dict, prefix: str | None) -> dict:
    if not prefix or 'cache_control' in request:  # explicit caller policy wins
        return request
    blocks = request.get('system')
    if not isinstance(blocks, list) or not blocks:
        return request
    first = blocks[0]
    text = first.get('text', '')
    if first.get('type') != 'text' or not text.startswith(prefix + '\n\n'):
        return request
    stable = {**first, 'text': prefix, 'cache_control': {'type': 'ephemeral'}}
    suffix = {key: value for key, value in first.items() if key != 'cache_control'}
    suffix['text'] = text[len(prefix):]  # retain every byte of the guidance
    system = [stable, suffix, *[{key: value for key, value in block.items() if key != 'cache_control'}
                               for block in blocks[1:]]]
    # Changing system guidance precedes history, so those history breakpoints
    # cannot hit on the next turn. Don't write unusable entries or exceed the
    # provider's four-breakpoint limit after splitting the system block.
    messages = []
    for message in request.get('messages', []):
        content = message.get('content')
        messages.append({**message, 'content': [
            {key: value for key, value in block.items() if key != 'cache_control'}
            for block in content] if isinstance(content, list) else content})
    return {**request, 'system': system, 'messages': messages}


def install_cache_boundary(client: Any) -> None:
    """Wrap only this adapter's owned SDK resources; no global/plugin patches."""
    resources = [getattr(client, 'messages', None)]
    beta = getattr(client, 'beta', None)
    if beta is not None:
        resources.append(getattr(beta, 'messages', None))
    for resource in resources:
        if resource is None:
            continue
        original = resource.create
        async def create(*args, _original=original, **kwargs):
            return await _original(*args, **cache_stable_prefix(kwargs, system_prefix.get()))
        resource.create = create
