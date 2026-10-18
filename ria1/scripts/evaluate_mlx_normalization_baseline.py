
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mlx_lm import load, generate

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ria1/data/normalization_training_v2"
SFT = ROOT / "ria1/data/mlx_normalization_v1"
OUTPUT = ROOT / "ria1/data/evaluation/mlx_normalization_baseline_v1.jsonl"
MANIFEST = ROOT / "ria1/data/evaluation/mlx_normalization_baseline_manifest_v1.json"

MODEL_NAME = "mlx-community/Qwen3-1.7B-4bit"
MAX_TOKENS = 180

SYSTEM = (
    "Convert conversational Tanglish into natural Tamil script. "
    "Preserve the exact meaning, pronouns, negation, tense, "
    "requests, questions, quantities and English technical names. "
    "Do not answer, explain, or translate into English. "
    "Return only the Tamil-script sentence."
)


def read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_manifest(data):
    temporary = MANIFEST.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(MANIFEST)


def main():
    valid_path = SOURCE / "valid.jsonl"
    sft_manifest_path = SFT / "manifest.json"

    if not valid_path.exists():
        raise FileNotFoundError(
            "normalization_training_v2/valid.jsonl missing. "
            "Complete Module 4.59 first."
        )

    if not sft_manifest_path.exists():
        raise FileNotFoundError(
            "mlx_normalization_v1/manifest.json missing. "
            "Complete Module 4.61 first."
        )

    sft_manifest = json.loads(
        sft_manifest_path.read_text(encoding="utf-8")
    )

    if sft_manifest["source_valid_sha256"] != digest(valid_path):
        raise ValueError("Validation data changed since SFT preparation")

    if sft_manifest["system_prompt"] != SYSTEM:
        raise ValueError("Baseline prompt and SFT prompt differ")

    records = read_jsonl(valid_path)

    if len(records) != 25:
        raise ValueError(f"Expected 25 cases, got {len(records)}")

    ids = [record["id"] for record in records]
    if len(set(ids)) != 25:
        raise ValueError("Duplicate validation IDs")

    config = {
        "module": "4.62",
        "model": MODEL_NAME,
        "adapter": None,
        "max_tokens": MAX_TOKENS,
        "system_prompt": SYSTEM,
        "validation_sha256": digest(valid_path),
        "sft_manifest_sha256": digest(sft_manifest_path),
        "template_enable_thinking": False,
        "status": "in_progress",
    }

    if MANIFEST.exists():
        previous = json.loads(MANIFEST.read_text(encoding="utf-8"))

        for field in (
            "model", "adapter", "max_tokens",
            "system_prompt", "validation_sha256",
            "sft_manifest_sha256", "template_enable_thinking",
        ):
            if previous.get(field) != config[field]:
                raise ValueError(
                    f"Resume settings mismatch: {field}"
                )
    elif OUTPUT.exists():
        raise ValueError(
            "Existing predictions have no manifest; refusing to append"
        )
    else:
        save_manifest(config)

    previous_rows = read_jsonl(OUTPUT) if OUTPUT.exists() else []
    completed = {}

    for row in previous_rows:
        if row["id"] in completed:
            raise ValueError(f"Duplicate saved prediction: {row['id']}")
        completed[row["id"]] = row

    if not set(completed).issubset(set(ids)):
        raise ValueError("Saved prediction IDs do not match validation")

    print("\nRIA-1 — MODULE 4.62")
    print("MATCHED MLX BASELINE")
    print("=" * 58)
    print("Model:", MODEL_NAME)
    print("Validation examples:", len(records))
    print("Previously completed:", len(completed))

    if len(completed) == len(records):
        print("All 25 predictions already saved.")
        return

    model, tokenizer = load(MODEL_NAME)

    if not getattr(tokenizer, "chat_template", None):
        raise RuntimeError("Model tokenizer has no chat template")

    for index, record in enumerate(records, 1):
        rid = record["id"]

        if rid in completed:
            continue

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": record["tanglish"]},
        ]

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

        prediction = generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=MAX_TOKENS,
            verbose=False,
        ).strip()

        result = {
            "id": rid,
            "tanglish": record["tanglish"],
            "reference_tamil": record["tamil"],
            "predicted_tamil": prediction,
            "model": MODEL_NAME,
            "adapter": None,
        }

        with OUTPUT.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(result, ensure_ascii=False) + "\n"
            )

        print(f"\n{index}/25 — {rid}")
        print("INPUT:", record["tanglish"])
        print("EXPECTED:", record["tamil"])
        print("PREDICTED:", prediction)

    config["status"] = "completed"
    config["completed_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    config["output_sha256"] = digest(OUTPUT)
    save_manifest(config)

    print("\n" + "=" * 58)
    print("Completed:", len(read_jsonl(OUTPUT)), "/25")
    print("Saved:", OUTPUT)
    print("Status: Ready for controlled LoRA comparison")


if __name__ == "__main__":
    main()

