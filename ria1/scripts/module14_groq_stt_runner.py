"""Isolated Groq speech transcription process."""

import json
import sys

from ria1.scripts.module14_groq_stt import transcribe_wav

def main():
    wav_bytes = sys.stdin.buffer.read()
    result = transcribe_wav(wav_bytes)
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
