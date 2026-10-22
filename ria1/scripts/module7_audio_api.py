import asyncio

from fastapi import FastAPI, File, HTTPException, UploadFile

from ria1.scripts.module7_audio_conversion import webm_to_whisper_bytes

app = FastAPI(title="RIA Audio API")

MAX_AUDIO_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {"audio/webm", "audio/mp4", "audio/ogg"}


async def read_audio(file: UploadFile):
    content_type = (file.content_type or "").split(";")[0].lower()

    if content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported audio format")

    audio = await file.read(MAX_AUDIO_BYTES + 1)

    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio too large")

    if not audio:
        raise HTTPException(422, "Audio is empty")

    return content_type, audio


@app.get("/health")
def health():
    return {"status": "ok", "service": "ria-audio"}


@app.post("/audio")
async def receive_audio(file: UploadFile = File(...)):
    content_type, audio = await read_audio(file)

    return {
        "status": "received",
        "filename": file.filename,
        "content_type": content_type,
        "size_bytes": len(audio),
    }


@app.post("/audio/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    _, audio = await read_audio(file)

    import time
    conversion_start = time.perf_counter()

    try:
        whisper_bytes = await asyncio.to_thread(
            webm_to_whisper_bytes, audio
        )
        conversion_seconds = time.perf_counter() - conversion_start
        print(f"RIA TIMING conversion: {conversion_seconds:.2f}s", flush=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    import os

    stt_backend = os.getenv("RIA_STT_BACKEND", "local").lower()

    if stt_backend == "groq":
        import io
        import wave

        import numpy as np

        from ria1.scripts.module14_groq_stt_bridge import (
            transcribe_via_bridge,
        )

        audio = np.load(
            io.BytesIO(whisper_bytes),
            allow_pickle=False,
        )

        if audio.ndim != 1:
            raise HTTPException(422, "Invalid audio shape")

        audio = np.asarray(audio, dtype=np.float32)

        pcm = (
            np.clip(audio, -1.0, 1.0) * 32767
        ).astype("<i2")

        output = io.BytesIO()

        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm.tobytes())

        try:
            result = await asyncio.to_thread(
                transcribe_via_bridge,
                output.getvalue(),
            )
        except Exception as exc:
            print(
                f"RIA Groq STT unavailable: {type(exc).__name__}: {exc}",
                flush=True,
            )
            raise HTTPException(
                status_code=503,
                detail="Speech recognition is temporarily unavailable",
            ) from exc

        return {
            "text": result.get("text", ""),
            "language": "en",
            "inference_seconds": result.get("inference_seconds"),
            "conversion_seconds": round(conversion_seconds, 2),
            "modal_roundtrip_seconds": None,
            "backend": "groq",
            "rejected": result.get("rejected", False),
            "rejection_reason": result.get("rejection_reason"),
            "silence_detected": (
                result.get("rejection_reason") == "silence"
            ),
            "speech_detected": (
                not result.get("rejected", False)
            ),
        }

    if stt_backend == "persistent":
        from ria1.scripts.module13_persistent_whisper_supervisor import (
            transcribe_with_recovery,
        )

        try:
            result = await asyncio.to_thread(
                transcribe_with_recovery, whisper_bytes
            )
        except (RuntimeError, TimeoutError) as exc:
            print(f"RIA persistent Whisper unavailable: {exc}", flush=True)
            raise HTTPException(
                status_code=503,
                detail="Speech recognition is temporarily unavailable",
            ) from exc

        return {
            "status": "transcribed",
            "text": result.get("text", ""),
            "language": result.get("language", ""),
            "inference_seconds": result.get("inference_seconds"),
            "conversion_seconds": round(conversion_seconds, 2),
            "modal_roundtrip_seconds": None,
            "backend": "persistent",
            "rejected": result.get("rejected", False),
            "rejection_reason": result.get("rejection_reason"),
            "silence_detected": result.get("silence_detected", False),
            "speech_detected": result.get("speech_detected"),
            "no_speech_prob": result.get("no_speech_prob"),
            "avg_logprob": result.get("avg_logprob"),
        }

    if stt_backend == "local":
        from ria1.scripts.module11_whisper_supervisor import (
            transcribe_supervised,
        )

        try:
            result = await asyncio.to_thread(
                transcribe_supervised, whisper_bytes
            )
        except Exception as exc:
            print(f"RIA local Whisper error: {exc}", flush=True)
            raise HTTPException(
                503, "Local speech recognition unavailable"
            ) from exc

        return {
            "status": "transcribed",
            "text": result.get("text", ""),
            "language": result.get("language", ""),
            "inference_seconds": result.get("inference_seconds"),
            "conversion_seconds": round(conversion_seconds, 2),
            "modal_roundtrip_seconds": None,
            "backend": "local",
            "rejected": result.get("rejected", False),
            "rejection_reason": result.get("rejection_reason"),
            "silence_detected": result.get("silence_detected", False),
            "speech_detected": result.get("speech_detected"),
            "no_speech_prob": result.get("no_speech_prob"),
            "avg_logprob": result.get("avg_logprob"),
        }

    if stt_backend != "modal":
        raise HTTPException(500, "Invalid RIA_STT_BACKEND setting")

    try:
        import modal

        cloud_start = time.perf_counter()

        Whisper = modal.Cls.from_name(
            "ria-cloud-voice",
            "RiaWhisper"
        )

        result = await asyncio.to_thread(
            lambda: Whisper().transcribe.remote(whisper_bytes)
        )

        cloud_seconds = time.perf_counter() - cloud_start
        print(f"RIA TIMING Modal roundtrip: {cloud_seconds:.2f}s", flush=True)

    except Exception as exc:
        print(f"RIA transcription error: {exc}")
        raise HTTPException(
            503,
            "Whisper service unavailable. Check Modal deployment."
        )

    inference_seconds = result.get("inference_seconds")

    if inference_seconds is not None:
        overhead = cloud_seconds - float(inference_seconds)
        print(
            f"RIA WHISPER SUMMARY | "
            f"conversion={conversion_seconds:.2f}s | "
            f"cloud={cloud_seconds:.2f}s | "
            f"inference={float(inference_seconds):.2f}s | "
            f"other_cloud_time={overhead:.2f}s",
            flush=True,
        )
    else:
        print("RIA WHISPER SUMMARY | inference timing unavailable", flush=True)

    return {
        "status": "transcribed",
        "text": result.get("text", ""),
        "language": result.get("language", ""),
        "inference_seconds": result.get("inference_seconds"),
        "conversion_seconds": round(conversion_seconds, 2),
        "modal_roundtrip_seconds": round(cloud_seconds, 2),
    }




# RIA_P181_BACKEND_SESSION_CLEANUP
MEMORY_CHANGE_ACTIONS = frozenset({
    "memory_saved",
    "memory_updated",
    "memory_deleted",
})


def _delete_old_conversation_session(session_id):
    """Best-effort removal of obsolete server-side chat history."""
    if not session_id:
        return True

    import urllib.request
    from urllib.parse import quote

    if not isinstance(session_id, str) or len(session_id) > 128:
        return False

    url = (
        "http://127.0.0.1:8003/session/"
        + quote(session_id, safe="")
    )

    try:
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=3) as response:
            return 200 <= response.status < 300
    except Exception as exc:
        print(
            "RIA session cleanup warning:",
            type(exc).__name__,
            flush=True,
        )
        return False


async def _finalize_memory_session(result, old_session_id):
    """Reset conversation continuity after a confirmed memory change."""
    if (
        result.get("success") is True
        and result.get("action") in MEMORY_CHANGE_ACTIONS
    ):
        import asyncio

        deleted = await asyncio.to_thread(
            _delete_old_conversation_session,
            old_session_id,
        )

        if not deleted:
            print(
                "RIA warning: old conversation session cleanup "
                "was not confirmed.",
                flush=True,
            )

        # The frontend must drop the old ID even if DELETE fails.
        result["reset_session"] = True
        result["session_id"] = None

    return result


# Module 8: Execute recognized reminder commands locally.
from pydantic import BaseModel
from ria1.scripts.module8_command_executor import execute_voice_command


class VoiceCommandRequest(BaseModel):
    text: str
    session_id: str | None = None
    request_id: str | None = None  # RIA_P16_INTERACTION_ID
    native_session_id: str | None = None



@app.post("/command")
async def command_from_text(request: VoiceCommandRequest):
    if not request.text.strip():
        raise HTTPException(422, "Command text is empty")

    normalized = request.text.lower().strip(" .!?")

    if normalized in {
        "stop",
        "ria stop",
        "hey ria stop",
        "stop talking",
        "ria stop talking",
        "hey ria stop talking",
    }:
        return {
            "action": "stop",
            "success": True,
            "reply": "",
        }

    # P0.2: Never forward unclear speech fragments to Qwen
    # or allow them to trigger memory/reminder actions.
    from ria1.scripts.module11_clarification import (
        speech_needs_clarification,
        UNCLEAR_SPEECH_REPLY,
    )

    if speech_needs_clarification(request.text):
        return {
            "action": "clarification",
            "success": True,
            "reply": UNCLEAR_SPEECH_REPLY,
            "session_id": request.session_id,
        }

    import os

    # RIA_HYBRID_V1
    # Keep chat and native-action sessions independent.
    if os.getenv("RIA_HYBRID_AGENT_ENABLED", "0") == "1":
        import json
        import urllib.request

        from ria1.scripts.module19_native_gateway import (
            run_native_request,
        )

        if not request.request_id:
            raise HTTPException(
                status_code=422,
                detail="Hybrid agent requires request_id",
            )

        try:
            native = await asyncio.to_thread(
                run_native_request,
                request.text,
                request.request_id,
                session_id=request.native_session_id,
            )

            native = dict(native)
            native_sid = native.pop("session_id", None)
            native_reset = native.pop("reset_session", False)

            if native.get("action") == "respond":
                def ask_chat():
                    payload = json.dumps({
                        "message": request.text,
                        "session_id": request.session_id,
                    }).encode("utf-8")

                    req = urllib.request.Request(
                        "http://127.0.0.1:8003/chat",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )

                    with urllib.request.urlopen(
                        req, timeout=240
                    ) as response:
                        return json.load(response)

                chat = await asyncio.to_thread(ask_chat)

                return {
                    "action": "conversation",
                    "success": True,
                    "reply": chat["reply"],
                    "model": chat["model"],
                    "session_id": chat["session_id"],
                    "native_session_id": (
                        None if native_reset else native_sid
                    ),
                }

            native["native_session_id"] = (
                None if native_reset else native_sid
            )
            native["native_reset_session"] = bool(native_reset)
            native["session_id"] = request.session_id

            memory_changed = (
                native.get("success") is True
                and native.get("action") in MEMORY_CHANGE_ACTIONS
            )

            if memory_changed:
                deleted = await asyncio.to_thread(
                    _delete_old_conversation_session,
                    request.session_id,
                )
                if not deleted:
                    print(
                        "RIA hybrid: conversation cleanup unconfirmed",
                        flush=True,
                    )

                native["session_id"] = None
                native["native_session_id"] = None
                native["reset_session"] = True
            else:
                # Native cancellation/confirmation resets must
                # not accidentally delete chat history.
                native["reset_session"] = False

            return native

        except (ValueError, PermissionError):
            return {
                "action": "authorization_rejected",
                "success": False,
                "reply": "I couldn't safely process that request.",
                "session_id": request.session_id,
                "native_session_id": request.native_session_id,
            }
        except Exception as exc:
            print(
                "RIA HYBRID ERROR:",
                type(exc).__name__,
                str(exc)[:300],
                flush=True,
            )
            raise HTTPException(
                status_code=503,
                detail="Hybrid agent unavailable or uncertain",
            )

    # RIA_P193_NATIVE_AGENT_ROUTE
    # Native mode has priority and never falls through to legacy parsers.
    import os

    if os.getenv("RIA_NATIVE_AGENT_ENABLED", "0") == "1":
        from ria1.scripts.module19_native_gateway import run_native_request

        if not request.request_id:
            raise HTTPException(
                status_code=422,
                detail="Native agent requires a stable request_id",
            )

        try:
            native_result = await asyncio.to_thread(
                run_native_request,
                request.text,
                request.request_id,
                session_id=request.session_id,
            )
        except (ValueError, PermissionError):
            return {
                "action": "authorization_rejected",
                "success": False,
                "reply": "I couldn't safely process that request.",
                "session_id": request.session_id,
            }
        except Exception as exc:
            print(
                "RIA NATIVE AGENT ERROR:",
                type(exc).__name__,
                str(exc)[:300],
                flush=True,
            )
            raise HTTPException(
                status_code=503,
                detail="RIA native agent unavailable or uncertain",
            )

        # P1104: Preserve the native gateway's session ID.
        # New sessions and resets are owned by the native gateway.
        native_result.setdefault("session_id", request.session_id)
        return await _finalize_memory_session(
            native_result, request.session_id
        )

    # RIA_P164_FEATURE_FLAGGED_AGENT
    # Disabled by default. Existing routes remain available.
    import os

    if os.getenv("RIA_AGENT_ENABLED", "0") == "1":
        from ria1.scripts.module15_agent_gateway import run_agent_request

        if not request.request_id:
            raise HTTPException(
                status_code=422,
                detail="Agent mode requires a stable request_id",
            )

        try:
            agent_result = await asyncio.to_thread(
                run_agent_request,
                request.text,
                request.request_id,
            )
        except (PermissionError, ValueError) as exc:
            return {
                "action": "authorization_rejected",
                "success": False,
                "reply": "I couldn't safely process that request.",
                "session_id": request.session_id,
            }
        except Exception as exc:
            print(
                "RIA AGENT ERROR:",
                type(exc).__name__,
                str(exc)[:300],
                flush=True,
            )
            raise HTTPException(
                status_code=503,
                detail="RIA agent action unavailable or uncertain",
            )

        if agent_result.get("action") != "conversation":
            agent_result["session_id"] = request.session_id
            return await _finalize_memory_session(
                agent_result, request.session_id
            )

        # Ordinary conversation continues through the existing
        # session-aware conversation service below.
        # This initial beta may make an additional LLM selection call.

    try:
        # Module 11: Handle explicit memory requests first.
        from ria1.scripts.module11_memory_commands import (
            handle_memory_command,
        )

        memory_result = await asyncio.to_thread(
            handle_memory_command,
            request.text,
            "ria_local_owner",
        )

        if memory_result["handled"]:
            memory_response = {
                "action": memory_result["action"],
                "success": memory_result["action"] not in (
                    "memory_invalid",
                    "memory_error",
                ),
                "reply": memory_result["reply"],
                "session_id": request.session_id,
            }
            return await _finalize_memory_session(
                memory_response, request.session_id
            )

        # Existing reminder routing remains unchanged.
        result = await asyncio.to_thread(
            execute_voice_command, request.text
        )

        if result["action"] != "conversation":
            return result

        # Ordinary conversation goes to local Ollama.
        import json
        import urllib.request

        def ask_conversation():
            payload = {
                "message": request.text,
                "session_id": request.session_id,
            }

            req = urllib.request.Request(
                "http://127.0.0.1:8003/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=240) as response:
                return json.load(response)

        chat = await asyncio.to_thread(ask_conversation)

        return {
            "action": "conversation",
            "success": True,
            "reply": chat["reply"],
            "session_id": chat["session_id"],
            "model": chat["model"],
        }

    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        print(f"RIA conversation error: {exc}")
        raise HTTPException(503, "Conversation service unavailable")



# Module 9: Generate spoken responses using existing RIA TTS.
import io
import wave

from fastapi.responses import Response
from pydantic import BaseModel as SpeechBaseModel
from voice.tts import synthesize_to_pcm, OUTPUT_SAMPLE_RATE


class SpeakRequest(SpeechBaseModel):
    text: str
    language: str = "english"


def synthesize_wav(text, language):
    import numpy as np

    pcm = synthesize_to_pcm(text, language=language)

    if len(pcm) == 0:
        raise ValueError("No speech generated")

    samples = (
        np.clip(pcm, -1.0, 1.0) * 32767
    ).astype("<i2")

    output = io.BytesIO()

    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(OUTPUT_SAMPLE_RATE)
        wav.writeframes(samples.tobytes())

    return output.getvalue()


@app.post("/speak")
async def speak(request: SpeakRequest):
    text = request.text.strip()

    if not text:
        raise HTTPException(422, "Speech text is empty")

    if len(text) > 500:
        raise HTTPException(422, "Speech text is too long")

    if request.language not in {"english", "tamil", "tanglish"}:
        raise HTTPException(422, "Unsupported language")

    try:
        wav_bytes = await asyncio.to_thread(
            synthesize_wav,
            text,
            request.language,
        )
    except Exception as exc:
        print(f"RIA TTS error: {exc}")
        raise HTTPException(503, "Speech synthesis unavailable")

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


# P0.3.5: Start persistent Whisper in the background.
@app.on_event("startup")
def initialize_persistent_whisper():
    import os

    if os.getenv("RIA_STT_BACKEND", "local").lower() == "persistent":
        from ria1.scripts.module13_persistent_whisper_supervisor import (
            start_background,
        )
        start_background()


@app.on_event("shutdown")
def stop_persistent_whisper():
    from ria1.scripts.module13_persistent_whisper_supervisor import shutdown
    shutdown()


@app.get("/audio/worker-status")
def persistent_whisper_status():
    import os

    backend = os.getenv("RIA_STT_BACKEND", "local").lower()

    if backend != "persistent":
        return {
            "backend": backend,
            "status": "not_enabled",
        }

    from ria1.scripts.module13_persistent_whisper_supervisor import status

    return {
        "backend": "persistent",
        "status": status(),
    }
