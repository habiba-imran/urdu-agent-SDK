"""Bounded, explicit live Claude probe. Prints metrics, never keys or responses.

No sessions, phone calls, tools, tenant records or database writes are performed.
Run with --live to spend a small number of model requests (maximum five).
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env.local')
    from livekit.agents import llm
    from livekit.agents.types import APIConnectOptions
    from worker.providers.llm.anthropic import build
    from worker.providers.llm.claude_cache import PREFIX_KEY
    from worker.cartesia_spoken_output import SYSTEM_INSTRUCTIONS_BASE
    model = build(args.model)
    results = []
    try:
        await model.prewarm()
        for index in range(args.runs):
            ctx = llm.ChatContext.empty()
            prefix = SYSTEM_INSTRUCTIONS_BASE + '\nThis is a synthetic test. Answer arithmetic directly in one short sentence. No tools are available.'
            message = ctx.add_message(role='system', content=prefix + (
                '\n\nSynthetic turn guidance: '+('Answer directly.' if index % 2 == 0 else 'Answer concisely.')
                if args.vary_guidance else ''))
            if args.vary_guidance:
                message.extra[PREFIX_KEY] = prefix
            ctx.add_message(role='user', content='What is two plus two?')
            start = time.perf_counter()
            first = None
            usage = None
            async with model.chat(chat_ctx=ctx, tools=[], conn_options=APIConnectOptions(max_retry=0, timeout=10)) as stream:
                async for chunk in stream:
                    if getattr(getattr(chunk, 'delta', None), 'content', None) and first is None:
                        first = (time.perf_counter()-start)*1000
                    if chunk.usage:
                        usage = chunk.usage
            results.append({'run': index+1, 'first_useful_text_ms': round(first, 1) if first is not None else None,
                            'total_ms': round((time.perf_counter()-start)*1000, 1),
                            'input_tokens': getattr(usage, 'prompt_tokens', None),
                            'cache_read_tokens': getattr(usage, 'cache_read_tokens', None),
                            'cache_creation_tokens': getattr(usage, 'cache_creation_tokens', None),
                            'output_tokens': getattr(usage, 'completion_tokens', None)})
        print(json.dumps({'model': model.model, 'settings': model.voice_options, 'measurement': 'live_provider_not_caller_audio',
                          'changing_system_guidance': args.vary_guidance,
                          'results': results}, indent=2))
    except Exception as error:
        # Provider errors can contain request headers/body. Return class/status only.
        print(json.dumps({'error_type': type(error).__name__, 'status': getattr(error, 'status_code', None)}))
        raise SystemExit(1) from None
    finally:
        await model.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--model', default='claude-haiku-5-5')
    parser.add_argument('--runs', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--vary-guidance', action='store_true', help='Verify stable-prefix cache reads while trusted turn guidance changes.')
    args = parser.parse_args()
    if not args.live:
        parser.error('No API calls made. Pass --live to run the bounded paid-provider probe.')
    asyncio.run(run(args))
