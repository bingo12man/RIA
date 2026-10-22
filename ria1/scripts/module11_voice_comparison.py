import asyncio
import tempfile
from pathlib import Path

import edge_tts

TEXT = (
    "Ahhh, there you are! "
    "Okay, okay, tell me everything. "
    "What's the exciting news today?"
)

VOICE = "en-US-JennyNeural"

STYLES = {
    "current": {"rate": "-10%", "pitch": "+0Hz"},
    "cheerful": {"rate": "+5%", "pitch": "+3Hz"},
    "bubbly": {"rate": "+10%", "pitch": "+6Hz"},
}


async def main():
    output = Path("ria1/voice_samples")
    output.mkdir(parents=True, exist_ok=True)

    for name, settings in STYLES.items():
        path = output / f"ria_{name}.mp3"

        print(f"Generating {name}...", flush=True)

        communicator = edge_tts.Communicate(
            text=TEXT,
            voice=VOICE,
            rate=settings["rate"],
            pitch=settings["pitch"],
        )

        await communicator.save(str(path))
        print(f"Saved: {path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
