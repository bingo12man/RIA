
import hashlib
import json
from pathlib import Path

from mlx_lm import load, generate

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "ria1/data/normalization_training_v2"
ADAPTER = ROOT / "ria1/adapters/normalization_pilot_001"
BASELINE = ROOT / "ria1/data/evaluation/mlx_normalization_baseline_v1.jsonl"

OUTPUT = ROOT / "ria1/data/evaluation/mlx_normalization_adapter_v1.jsonl"
MANIFEST = ROOT / "ria1/data/evaluation/mlx_normalization_adapter_manifest_v1.json"

MODEL = "mlx-community/Qwen3-1.7B-4bit"
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
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    validation_path = DATA / "valid.jsonl"
    adapter_weights = ADAPTER / "adapters.safetensors"
    adapter_config = ADAPTER / "adapter_config.json"

    for path in (
        validation_path,
        adapter_weights,
        adapter_config,
        BASELINE,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    validation = read_jsonl(validation_path)
    baseline = read_jsonl(BASELINE)

    if len(validation) != 25 or len(baseline) != 25:
        raise ValueError("Expected 25 validation and baseline records")

    baseline_by_id = {row["id"]: row for row in baseline}
    validation_ids = [row["id"] for row in validation]

    if (
        len(set(validation_ids)) != 25
        or len(baseline_by_id) != 25
        or set(baseline_by_id) != set(validation_ids)
    ):
        raise ValueError("Baseline and validation IDs differ")

    config = {
        "model": MODEL,
        "adapter": str(ADAPTER.relative_to(ROOT)),
        "adapter_weights_sha256": digest(adapter_weights),
        "adapter_config_sha256": digest(adapter_config),
        "validation_sha256": digest(validation_path),
        "baseline_sha256": digest(BASELINE),
        "max_tokens": MAX_TOKENS,
        "system_prompt": SYSTEM,
        "thinking": False,
    }

    if MANIFEST.exists():
        previous = json.loads(
            MANIFEST.read_text(encoding="utf-8")
        )

        for key, value in config.items():
            if previous.get(key) != value:
                raise ValueError(
                    f"Cannot resume: configuration changed ({key})"
                )

    elif OUTPUT.exists():
        raise ValueError(
            "Prediction output exists without a manifest"
        )

    else:
        MANIFEST.write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )

    saved = read_jsonl(OUTPUT) if OUTPUT.exists() else []
    completed = {row["id"]: row for row in saved}

    if len(completed) != len(saved):
        raise ValueError("Duplicate saved predictions")

    if not set(completed).issubset(set(validation_ids)):
        raise ValueError("Unknown prediction IDs")

    print("\nRIA-1 — MODULE 4.64")
    print("LoRA ADAPTER EVALUATION")
    print("=" * 60)
    print("Model:", MODEL)
    print("Validation examples:", len(validation))
    print("Already completed:", len(completed))

    if len(completed) == 25:
        print("All 25 predictions already saved.")
        return

    model, tokenizer = load(
        MODEL,
        adapter_path=str(ADAPTER),
    )

    for index, row in enumerate(validation, 1):
        rid = row["id"]

        if rid in completed:
            continue

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": row["tanglish"]},
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

        baseline_prediction = baseline_by_id[rid]["predicted_tamil"]

        result = {
            "id": rid,
            "tanglish": row["tanglish"],
            "expected_tamil": row["tamil"],
            "baseline_tamil": baseline_prediction,
            "adapter_tamil": prediction,
        }

        with OUTPUT.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    result, ensure_ascii=False
                ) + "\n"
            )

        print(f"\n{index}/25 — {rid}")
        print("INPUT:", row["tanglish"])
        print("EXPECTED:", row["tamil"])
        print("BASELINE:", baseline_prediction)
        print("ADAPTER:", prediction)

    print("\n" + "=" * 60)
    print("Completed:", len(read_jsonl(OUTPUT)), "/25")
    print("Saved:", OUTPUT)
    print("Status: Human meaning review required")


if __name__ == "__main__":
    main()

