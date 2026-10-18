
import hashlib
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "ria1/data/normalization_training_v2"
VALID = DATA / "valid.jsonl"

OUTPUT = ROOT / "ria1/data/evaluation/normalization_baseline_v1.jsonl"
MANIFEST = ROOT / "ria1/data/evaluation/normalization_baseline_manifest_v1.json"

MODEL = os.getenv("RIA_BASELINE_MODEL", "qwen3:1.7b")
URL = "http://127.0.0.1:11434/api/chat"

SYSTEM = """
You are a Tanglish-to-Tamil script converter.

Convert the user's Romanized Tamil into natural Tamil script.

Rules:
- Preserve the original meaning exactly.
- Preserve subjects, pronouns and gender.
- Preserve tense, negation, questions and commands.
- Preserve all quantities and time references.
- Retain technical product names such as FastAPI and MongoDB.
- Do not translate into English.
- Do not answer the request.
- Do not add explanations.
- Return only the Tamil sentence.
""".strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ask_model(tanglish):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": tanglish},
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_ctx": 2048,
            "num_predict": 180,
        },
        "keep_alive": "5m",
        "think": False,
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=240
    ) as response:
        result = json.load(response)

    return result["message"]["content"].strip()


def main():
    if not VALID.exists():
        raise FileNotFoundError(
            "Validation dataset not found. Complete Module 4.59."
        )

    records = read_jsonl(VALID)

    if len(records) != 25:
        raise ValueError(
            f"Expected 25 validation cases, found {len(records)}"
        )

    ids = [r["id"] for r in records]

    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate validation IDs")

    if MANIFEST.exists():
        old_manifest = json.loads(
            MANIFEST.read_text(encoding="utf-8")
        )

        if (
            old_manifest["validation_sha256"]
            != sha256(VALID)
            or old_manifest["model"] != MODEL
        ):
            raise ValueError(
                "Dataset or model changed after baseline started."
            )
    elif OUTPUT.exists():
        raise ValueError(
            "Existing predictions have no manifest. "
            "Inspect them manually before continuing."
        )
    else:
        manifest = {
            "module": "4.60",
            "model": MODEL,
            "validation_sha256": sha256(VALID),
            "system_prompt": SYSTEM,
            "temperature": 0,
            "status": "in_progress",
        }

        MANIFEST.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )

    completed = {}

    if OUTPUT.exists():
        for row in read_jsonl(OUTPUT):
            rid = row["id"]

            if rid in completed:
                raise ValueError(f"Duplicate prediction: {rid}")

            completed[rid] = row

        if not set(completed).issubset(set(ids)):
            raise ValueError("Unknown IDs in previous predictions")

    print("\nRIA-1 — MODULE 4.60")
    print("NORMALIZATION BASELINE")
    print("=" * 60)
    print("Model:", MODEL)
    print("Validation examples:", len(records))
    print("Already completed:", len(completed))

    for index, record in enumerate(records, 1):
        rid = record["id"]

        if rid in completed:
            continue

        try:
            prediction = ask_model(record["tanglish"])
        except Exception as error:
            print(f"\nStopped at {rid}: {error}")
            print("Previous predictions remain saved.")
            return

        result = {
            "id": rid,
            "tanglish": record["tanglish"],
            "expected_tamil": record["tamil"],
            "predicted_tamil": prediction,
            "pair_type": record["pair_type"],
        }

        with OUTPUT.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    result, ensure_ascii=False
                ) + "\n"
            )

        print(f"\n{index}/25 — {rid}")
        print("Tanglish:", record["tanglish"])
        print("Expected:", record["tamil"])
        print("Predicted:", prediction)

    print("\n" + "=" * 60)
    print("Completed:", len(read_jsonl(OUTPUT)), "/25")
    print("Saved:", OUTPUT)
    print("STATUS: Baseline generated; human scoring required.")


if __name__ == "__main__":
    main()

