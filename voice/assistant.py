
import json
import os
import queue
import re
import sys
import threading
import time

import httpx
import numpy as np
from faster_whisper import WhisperModel

from voice.recording import record_until_silence
from voice.tts import synthesize_to_pcm
from voice.audio_player import ContinuousAudioPlayer


RIA_API = os.getenv(
    "RIA_API", "http://127.0.0.1:8000"
).rstrip("/")

MODEL_SIZE = os.getenv(
    "RIA_WHISPER_MODEL", "small"
)

DEFAULT_LANGUAGE = os.getenv(
    "RIA_DEFAULT_LANGUAGE", "tanglish"
).lower()

if DEFAULT_LANGUAGE not in (
    "english", "tamil", "tanglish", "auto"
):
    DEFAULT_LANGUAGE = "tanglish"


def transcribe_audio(model, audio):
    start = time.perf_counter()

    segments, info = model.transcribe(
        np.asarray(audio, dtype=np.float32),
        beam_size=2,
        vad_filter=True
    )

    text = " ".join(
        segment.text.strip()
        for segment in segments
    ).strip()

    print(
        f"[Latency] STT: "
        f"{time.perf_counter() - start:.2f}s"
    )

    return text, info.language


def requested_language(text, previous):
    message = text.lower().strip()

    if re.search(
        r"\b(tanglish|tamil[- ]english mix|"
        r"tamil in english letters)\b",
        message
    ):
        return "tanglish"

    if re.search(
        r"\b(pure tamil|tamil script|tamil letters)\b",
        message
    ):
        return "tamil"

    if re.search(
        r"\b(?:in|speak|reply in|explain in|"
        r"answer in|use)\s+"
        r"(?:(?:simple|plain|easy|conversational)\s+)?"
        r"english\b|\benglish\s+please\b",
        message
    ):
        return "english"

    if re.search(
        r"\b(?:in|speak|reply in|explain in|"
        r"answer in|use)\s+"
        r"(?:(?:simple|spoken|conversational)\s+)?"
        r"tamil\b|\btamil\s+please\b",
        message
    ):
        return "tanglish"

    return previous


def receive_stream(
    text,
    session_id,
    language,
    sentence_queue,
    metadata,
    stop_event
):
    payload = {
        "message": text,
        "language": language
    }

    if session_id:
        payload["session_id"] = session_id

    try:
        with httpx.Client(
            timeout=180.0,
            trust_env=False
        ) as client:

            with client.stream(
                "POST",
                f"{RIA_API}/chat/stream",
                json=payload
            ) as response:

                response.raise_for_status()

                for line in response.iter_lines():
                    if stop_event.is_set():
                        break

                    if not line:
                        continue

                    event = json.loads(line)
                    kind = event.get("type")

                    if kind == "meta":
                        metadata["session_id"] = event.get(
                            "session_id"
                        )
                        metadata["language"] = event.get(
                            "language", language
                        )

                    elif kind == "sentence":
                        sentence = event.get(
                            "text", ""
                        ).strip()

                        if sentence:
                            sentence_queue.put(sentence)

                    elif kind == "done":
                        metadata["completed"] = True
                        metadata["session_id"] = event.get(
                            "session_id",
                            metadata.get("session_id")
                        )
                        metadata["language_valid"] = (
                            event.get("language_valid", True)
                        )

                    elif kind == "error":
                        metadata["error"] = event.get(
                            "message", "Unknown error"
                        )
                        break

    except Exception as exc:
        if not stop_event.is_set():
            metadata["error"] = str(exc)

    finally:
        sentence_queue.put(None)


def prepare_audio(
    sentence_queue,
    audio_queue,
    metadata,
    stop_event
):
    """
    Generate PCM audio while playback
    of earlier sentences continues.
    """

    try:
        while not stop_event.is_set():
            sentence = sentence_queue.get()

            if sentence is None:
                break

            if stop_event.is_set():
                break

            started = time.perf_counter()

            audio = synthesize_to_pcm(
                sentence,
                metadata["language"]
            )

            if stop_event.is_set():
                break

            audio_queue.put({
                "text": sentence,
                "audio": audio,
                "tts_seconds": (
                    time.perf_counter() - started
                )
            })

    except Exception as exc:
        metadata["error"] = f"TTS error: {exc}"

    finally:
        audio_queue.put(None)


def stream_conversation(text, session_id, language):
    sentences = queue.Queue(maxsize=8)
    audio_queue = queue.Queue(maxsize=8)
    stop_event = threading.Event()

    metadata = {
        "session_id": session_id,
        "language": language,
        "completed": False,
        "language_valid": True,
        "error": None
    }

    receiver = threading.Thread(
        target=receive_stream,
        args=(
            text,
            session_id,
            language,
            sentences,
            metadata,
            stop_event
        ),
        daemon=True
    )

    synthesizer = threading.Thread(
        target=prepare_audio,
        args=(
            sentences,
            audio_queue,
            metadata,
            stop_event
        ),
        daemon=True
    )

    started = time.perf_counter()
    interrupted = False
    first_audio = True
    audio_underruns = 0

    # Discard an Enter left over from starting recording,
    # but do this once, not between sentences.
    if sys.stdin.isatty():
        try:
            import termios
            termios.tcflush(
                sys.stdin.fileno(),
                termios.TCIFLUSH
            )
        except (OSError, ValueError, ImportError):
            pass

    receiver.start()
    synthesizer.start()

    try:
        # One output stream for the entire reply.
        with ContinuousAudioPlayer() as player:
            while True:
                try:
                    item = audio_queue.get(timeout=0.05)

                except queue.Empty:
                    if not first_audio:
                        audio_underruns += 1

                    # Detect a new Enter even while
                    # waiting for the next audio.
                    from voice.audio_player import (
                        keyboard_interrupted
                    )

                    if keyboard_interrupted():
                        player.interrupted = True
                        interrupted = True
                        stop_event.set()
                        break

                    continue

                if item is None:
                    break

                if first_audio:
                    print(
                        "[Latency] First audio ready: "
                        f"{time.perf_counter() - started:.2f}s"
                    )
                    first_audio = False

                print(f"\nRia: {item['text']}")

                interrupted = player.play(
                    item["audio"]
                )

                if interrupted:
                    stop_event.set()
                    break

    finally:
        stop_event.set()

        # Threads are expected to complete promptly,
        # though active network requests may take longer.
        receiver.join(timeout=2)
        synthesizer.join(timeout=2)

    if metadata["error"] and not interrupted:
        print(f"Pipeline error: {metadata['error']}")

    if not metadata["language_valid"]:
        print("Warning: language validation failed.")

    print(
        f"[Latency] Total: "
        f"{time.perf_counter() - started:.2f}s"
    )

    print(
        f"[Audio] Buffer wait intervals: "
        f"{audio_underruns}"
    )

    # Do not reuse an incomplete new session.
    next_session = (
        metadata["session_id"]
        if metadata["completed"]
        else session_id
    )

    return next_session, interrupted, metadata["completed"]


def main():
    print("Loading Whisper...")

    model = WhisperModel(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8"
    )

    print("=" * 45)
    print("Ria — Continuous Voice Companion")
    print("=" * 45)
    print("Press ENTER to start recording.")
    print("Press ENTER during speech to interrupt.")
    print("Microphone interruption is disabled.")
    print("Type q to exit.")

    session_id = None
    language = DEFAULT_LANGUAGE
    listen_immediately = False

    while True:
        try:
            if not listen_immediately:
                action = input(
                    "\nPress ENTER to speak: "
                )

                if action.strip().lower() == "q":
                    break

            listen_immediately = False

            audio = record_until_silence()

            if audio is None or audio.size == 0:
                continue

            text, detected_language = transcribe_audio(
                model,
                audio
            )

            if not text:
                print("Speech not recognized.")
                continue

            print(f"\nYou: {text}")
            print(
                f"Speech language: {detected_language}"
            )

            language = requested_language(
                text,
                language
            )

            print(f"Response language: {language}")

            session_id, interrupted, completed = (
                stream_conversation(
                    text,
                    session_id,
                    language
                )
            )

            if interrupted:
                listen_immediately = True

        except KeyboardInterrupt:
            print("\nRia stopped.")
            break

        except (
            OSError,
            ValueError,
            httpx.HTTPError
        ) as exc:
            print(f"Voice error: {exc}")


if __name__ == "__main__":
    main()
