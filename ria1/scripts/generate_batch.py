
import argparse
import json
import os
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "ria1/data/expansion/batch_001.jsonl"
OUTPUT = ROOT / "ria1/data/expansion/batch_001_candidates.jsonl"

MODEL = os.getenv("RIA_MODEL", "gemma3:4b")
OLLAMA_URL = os.getenv(
    "RIA_OLLAMA_URL", "http://127.0.0.1:11434"
).rstrip("/")


LANGUAGE_RULES = {
    "english": (
        "Respond in natural, friendly English. "
        "Avoid overly formal or robotic language."
    ),
    "tamil": (
        "Respond using natural, everyday spoken Tamil "
        "in Tamil script. Avoid literary Tamil."
    ),
    "tanglish": (
        "Respond in conversational Tamil written using "
        "English letters. Mix English words naturally. "
        "Use correct Tamil grammar. Do not invent words "
        "or use Tamil script. Do not use English-only replies."
    ),
}

TONE_RULES = {
    "sad_stressed": (
        "Be empathetic and gentle. Acknowledge the difficulty."
    ),
    "happy_excited": (
        "Be energetic, cheerful and playful."
    ),
    "romantic_flirty": (
        "Offer a cute, cheeky compliment when invited. "
        "Do not claim real human feelings."
    ),
    "casual_friendly": (
        "Be relaxed, friendly and conversational."
    ),
    "confused_learning": (
        "Explain clearly with accurate, simple examples."
    ),
    "frustrated_angry": (
        "Acknowledge mistakes and respond calmly. "
        "Do not blame the user."
    ),
    "lonely_vulnerable": (
        "Be supportive and attentive without "
        "encouraging emotional dependency."
    ),
}


def read_jsonl(path):
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))

    return records


def write_jsonl_atomic(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    temporary.replace(path)


def generate(client, record):
    language = record["language"]
    tone = record["tone"]

    system = (
        "You are Ria, a helpful, warm AI companion.\n"
        "Respond to the user's actual message.\n"
        "Keep the answer concise, usually 1-3 sentences.\n"
        "Preserve who is speaking and who is being addressed.\n"
        "Do not invent personal experiences or memories.\n"
        + LANGUAGE_RULES[language]
        + "\n"
        + TONE_RULES[tone]
    )

    started = time.perf_counter()

    response = client.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": record["user_message"]
                },
            ],
            "options": {
                "temperature": 0.4,
                "num_predict": 250,
            },
        },
    )

    response.raise_for_status()
    data = response.json()

    text = data["message"]["content"].strip()

    if not text:
        raise ValueError("Model returned an empty response")

    return {
        "candidate_response": text,
        "candidate_status": "pending_review",
        "model": MODEL,
        "latency_seconds": round(
            time.perf_counter() - started, 3
        ),
        "done_reason": data.get("done_reason"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=21)
    args = parser.parse_args()

    if not 1 <= args.limit <= 21:
        parser.error("--limit must be between 1 and 21")

    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Create Batch 001 first: {SOURCE}"
        )

    source_records = read_jsonl(SOURCE)

    existing = (
        read_jsonl(OUTPUT) if OUTPUT.exists() else []
    )

    by_id = {str(r["id"]): r for r in existing}

    if len(by_id) != len(existing):
        raise ValueError("Duplicate candidate IDs")

    source_ids = {str(r["id"]) for r in source_records}

    if not set(by_id).issubset(source_ids):
        raise ValueError(
            "Candidate file contains unknown record IDs"
        )

    with httpx.Client(
        timeout=180,
        trust_env=False
    ) as client:

        for record in source_records[:args.limit]:
            record_id = str(record["id"])

            if record_id in by_id:
                print("Already generated:", record_id)
                continue

            print("\n" + "=" * 55)
            print(record_id)
            print("Language:", record["language"])
            print("Tone:", record["tone"])
            print("USER:", record["user_message"])

            try:
                candidate = generate(client, record)

                result = {
                    **record,
                    **candidate,
                }

                print("\nGEMMA CANDIDATE:")
                print(result["candidate_response"])

            except Exception as exc:
                result = {
                    **record,
                    "candidate_response": "",
                    "candidate_status": "generation_failed",
                    "model": MODEL,
                    "error": str(exc),
                }

                print("Generation failed:", exc)

            by_id[record_id] = result

            ordered = [
                by_id[str(item["id"])]
                for item in source_records
                if str(item["id"]) in by_id
            ]

            write_jsonl_atomic(OUTPUT, ordered)

    successful = sum(
        item.get("candidate_status") == "pending_review"
        for item in by_id.values()
    )

    print("\n" + "=" * 55)
    print("RIA-1 BATCH 001 GENERATION")
    print("Generated candidates:", successful)
    print("Total saved records:", len(by_id))
    print("Human approvals: 0 (not yet reviewed)")
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()

