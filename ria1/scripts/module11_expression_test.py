import asyncio
from pathlib import Path

import edge_tts

VOICE = "en-US-JennyNeural"

SAMPLES = {
    "01_normal": "Ah, there you are! Okay, okay, tell me everything!",
    "02_stretched": "Aaaah, there you are! Okaaay, okay, tell me everything!",
    "03_pauses": "Ahhh... there you are! Okay... okay! Tell me everything!",
    "04_conversational": "Awww, there you are! Wait, wait! Tell me everything!",
}

async def main():
    output = Path("ria1/voice_samples/expression")
    output.mkdir(parents=True, exist_ok=True)

    for name, text in SAMPLES.items():
        print(f"Generating {name}: {text}", flush=True)

        tts = edge_tts.Communicate(
            text=text,
            voice=VOICE,
            rate="+0%",
            pitch="+0Hz",
        )

        await tts.save(str(output / f"{name}.mp3"))

    print("\nAll expression samples generated.")

if __name__ == "__main__":
    asyncio.run(main())
