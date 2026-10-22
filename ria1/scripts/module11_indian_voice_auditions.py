import asyncio
import json
from pathlib import Path

import edge_tts

OUTPUT = Path("ria1/voice_samples/indian_auditions")

SAMPLES = {
    "natural": (
        "Ah, there you are! How's your day going? "
        "Tell me something interesting."
    ),
    "playful": (
        "Oh my gosh! You're finally here! "
        "Okay, tell me everything. What happened?"
    ),
}

async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    voices = await edge_tts.list_voices()

    female_indian = sorted(
        (
            v for v in voices
            if v.get("Locale") == "en-IN"
            and v.get("Gender", "").lower() == "female"
        ),
        key=lambda v: v["ShortName"]
    )

    if not female_indian:
        print("No Indian-English female voices found.")
        return

    print("Available Indian-English female voices:")

    manifest = []

    for voice in female_indian:
        short_name = voice["ShortName"]
        print(" -", short_name)

        for style, text in SAMPLES.items():
            filename = f"{short_name}_{style}.mp3"
            path = OUTPUT / filename

            try:
                tts = edge_tts.Communicate(
                    text=text,
                    voice=short_name,
                    rate="+0%",
                    pitch="+0Hz",
                )
                await tts.save(str(path))

                manifest.append({
                    "voice": short_name,
                    "style": style,
                    "file": filename,
                })

                print("   Saved:", filename, flush=True)

            except Exception as exc:
                print("   Failed:", style, str(exc))

    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )

    print("\nAuditions complete:", OUTPUT)

asyncio.run(main())
