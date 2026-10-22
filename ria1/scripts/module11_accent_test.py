import asyncio
from pathlib import Path
import edge_tts

TEXT = (
    "Ah, there you are! "
    "Oh my gosh, I was just about to say hello! "
    "Wait, wait! Tell me what happened. "
    "This sounds exciting!"
)

VOICES = {
    "american_jenny": "en-US-JennyNeural",
    "indian_neerja": "en-IN-NeerjaNeural",
    "indian_aarti": "en-IN-AartiNeural",
}

async def main():
    output = Path("ria1/voice_samples/accents")
    output.mkdir(parents=True, exist_ok=True)

    available = {
        voice["ShortName"]
        for voice in await edge_tts.list_voices()
    }

    for name, voice in VOICES.items():
        if voice not in available:
            print(f"SKIPPED: {voice} is unavailable")
            continue

        print(f"Generating {name}...", flush=True)

        tts = edge_tts.Communicate(
            text=TEXT,
            voice=voice,
            rate="+0%",
            pitch="+0Hz",
        )

        await tts.save(str(output / f"{name}.mp3"))
        print(f"Saved: {name}")

    print("Accent comparison complete!")

asyncio.run(main())
