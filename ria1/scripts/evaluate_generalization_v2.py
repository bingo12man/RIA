
import hashlib
import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "ria1/data/evaluation/generalization_v2_frozen"

PROMPTS = FOLDER / "prompts.jsonl"
CONVERSIONS = FOLDER / "conversions_v1.jsonl"
MANIFEST = FOLDER / "manifest.json"
OUTPUT = FOLDER / "model_predictions_v1.jsonl"

MODEL = "gemma3:4b"
URL = "http://127.0.0.1:11434/api/chat"

SYSTEM = (
    "Understand conversational Tamil and Tanglish. "
    "Explain only what the CURRENT USER means in one "
    "concise, natural English sentence. "
    "Use previous conversation when provided. "
    "Preserve speaker, tense, negation, questions, "
    "quantities, directions and emotion. "
    "Do not answer or execute the user's request. "
    "Do not add information."
)


def load_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ask_gemma(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 140,
        },
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.load(response)

    return data["message"]["content"].strip()


def conversation(prompt, current):
    messages = [{"role": "system", "content": SYSTEM}]

    if prompt.get("previous_user") and prompt.get("previous_ria"):
        messages.append({
            "role": "user",
            "content": prompt["previous_user"],
        })
        messages.append({
            "role": "assistant",
            "content": prompt["previous_ria"],
        })

    messages.append({
        "role": "user",
        "content": "CURRENT USER: " + current,
    })

    return messages


def main():
    if OUTPUT.exists():
        raise FileExistsError(
            "Predictions already exist. "
            "First-run results must not be overwritten."
        )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    if sha256(PROMPTS) != manifest["prompts_sha256"]:
        raise ValueError("Frozen prompt hash mismatch")

    answer_key = FOLDER / "answer_key.jsonl"
    if sha256(answer_key) != manifest["answer_key_sha256"]:
        raise ValueError("Frozen answer-key hash mismatch")

    prompts = load_jsonl(PROMPTS)
    conversions = load_jsonl(CONVERSIONS)

    conversion_by_id = {r["id"]: r for r in conversions}

    if (
        len(prompts) != 40
        or len(conversion_by_id) != 40
        or set(conversion_by_id) != {r["id"] for r in prompts}
    ):
        raise ValueError("Evaluation/conversion IDs mismatch")

    results = []

    print("\nRIA-1 GENERALIZATION V2 — MODEL COMPARISON")
    print("=" * 60)

    for index, prompt in enumerate(prompts, 1):
        conversion = conversion_by_id[prompt["id"]]

        methods = {
            "direct": prompt["user_message"],
            "indicxlit_top1": conversion["top1_tamil"],
            "verified_converter": conversion["verified_tamil"],
        }

        predictions = {}

        for method, input_text in methods.items():
            predictions[method] = ask_gemma(
                conversation(prompt, input_text)
            )

        result = {
            "id": prompt["id"],
            "category": prompt["category"],
            "predictions": predictions,
        }

        results.append(result)

        print(f"\n{index}/40 — {prompt['id']}")
        print("ORIGINAL:", prompt["user_message"])

        for name, prediction in predictions.items():
            print(name.upper() + ":", prediction)

    OUTPUT.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in results
        ),
        encoding="utf-8",
    )

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "prompt_count": len(results),
        "category_counts": dict(
            Counter(row["category"] for row in results)
        ),
        "methods": [
            "direct",
            "indicxlit_top1",
            "verified_converter",
        ],
        "prompt_sha256": sha256(PROMPTS),
        "conversion_sha256": sha256(CONVERSIONS),
        "predictions_sha256": sha256(OUTPUT),
        "status": "awaiting_blind_human_scoring",
        "limitations": [
            "Frozen development evaluation, not a production benchmark.",
            "Earlier assistant turns are left unchanged for all methods.",
            "The three methods use the same prompt and decoding settings.",
            "No target answers are supplied to the models.",
            "Model output may vary between runs.",
        ],
    }

    (FOLDER / "prediction_manifest.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("Completed:", len(results), "prompts")
    print("Model responses:", len(results) * 3)
    print("Saved:", OUTPUT)
    print("Human scoring still required.")


if __name__ == "__main__":
    main()

