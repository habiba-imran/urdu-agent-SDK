import asyncio
import os
from worker.factories import make_tts

async def main():
    os.environ['UPLIFT_MODE'] = 'live'
    tts = make_tts('v_meklc281')
    stream = tts.synthesize('سلام')
    print("✅ ResilientTTS and ResilientChunkedStream initialized successfully!")

if __name__ == "__main__":
    asyncio.run(main())
