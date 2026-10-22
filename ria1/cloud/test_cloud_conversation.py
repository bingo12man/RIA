import io
import time
import numpy as np
import modal

from voice.recording import record_until_silence
from voice.tts import synthesize_to_pcm
from voice.audio_player import ContinuousAudioPlayer


def main():
    print("=" * 45)
    print("RIA — CLOUD CONVERSATION TEST")
    print("=" * 45)

    print("\n1. Recording your voice...")
    audio = record_until_silence()

    if audio is None:
        print("No speech detected. Test cancelled.")
        return

    buffer = io.BytesIO()
    np.save(buffer, audio, allow_pickle=False)

    print("\n2. Sending audio to cloud Whisper...")
    started = time.perf_counter()

    whisper = modal.Cls.from_name(
        "ria-whisper",
        "WhisperService",
    )

    transcription = whisper().transcribe.remote(
        buffer.getvalue()
    )

    stt_time = time.perf_counter() - started

    text = transcription["text"].strip()

    print("YOU:", text)
    print("Language:", transcription["language"])
    print(f"[Cloud STT] {stt_time:.2f}s")

    if not text:
        print("Empty transcription. Test cancelled.")
        return

    print("\n3. Sending transcription to cloud Qwen...")
    started = time.perf_counter()

    qwen = modal.Cls.from_name(
        "ria-qwen-cached-test",
        "RiaModel",
    )

    result = qwen().chat.remote(text)

    llm_time = time.perf_counter() - started

    reply = result["reply"]

    print("RIA:", reply)
    print(f"[Cloud LLM] {llm_time:.2f}s")
    print(
        "[Generation]",
        result["generation_seconds"],
        "seconds",
    )

    print("\n4. Generating speech...")
    started = time.perf_counter()

    speech = synthesize_to_pcm(
        reply,
        language="english",
    )

    print(
        f"[TTS] {time.perf_counter() - started:.2f}s"
    )

    if len(speech):
        with ContinuousAudioPlayer() as player:
            player.play(speech)

    print("\nCloud conversation test completed.")


if __name__ == "__main__":
    main()
