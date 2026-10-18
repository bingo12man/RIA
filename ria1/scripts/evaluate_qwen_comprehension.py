
import argparse
import json
import re
from pathlib import Path

import mlx.core as mx
from mlx_lm import load, generate


ROOT = Path(__file__).resolve().parents[2]

BENCHMARK = (
    ROOT / "ria1/data/evaluation/"
    "tanglish_comprehension_v1.jsonl"
)

OUTPUT_DIR = ROOT / "ria1/data/evaluation"

MODEL = "mlx-community/Qwen3-1.7B-4bit"

ADAPTER = ROOT / "ria1/adapters/pilot_001"

SYSTEM = (
    "You are evaluating spoken Tamil written in English "
    "letters, also called Tanglish. Understand Tamil "
    "grammar and colloquial expressions. "
    "Explain in one short English sentence exactly what "
    "the user means. Do not answer the user's request. "
    "Preserve negation, pronouns, emotional meaning, "
    "and who is speaking."
)


def load_benchmark():
    with BENCHMARK.open("r", encoding="utf-8") as f:
        rows = [
            json.loads(line)
            for line in f
            if line.strip()
        ]

    ids = [r["id"] for r in rows]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate benchmark IDs.")

    return rows


def build_prompt(tokenizer, message):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": message},
    ]

    formatted = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    return tokenizer.encode(
        formatted,
        add_special_tokens=False,
    )


def clean_response(text):
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL,
    )

    return text.strip()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=["base", "adapter"],
        required=True,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=30,
    )

    args = parser.parse_args()
    rows = load_benchmark()

    if not 1 <= args.limit <= len(rows):
        parser.error("Invalid limit.")

    if args.mode == "adapter":
        if not ADAPTER.exists():
            raise FileNotFoundError(ADAPTER)

        print("Loading RIA-1 LoRA adapter...")

        model, tokenizer = load(
            MODEL,
            adapter_path=str(ADAPTER),
        )
    else:
        print("Loading original Qwen3 model...")

        model, tokenizer = load(MODEL)

    results = []

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        OUTPUT_DIR /
        f"qwen3_{args.mode}_comprehension_"
        f"{args.limit}.json"
    )

    for index, record in enumerate(
        rows[:args.limit], 1
    ):
        print("\n" + "=" * 60)
        print(f"CASE {index}/{args.limit}")
        print("ID:", record["id"])
        print("USER:", record["user_message"])

        try:
            mx.random.seed(42)

            prompt = build_prompt(
                tokenizer,
                record["user_message"],
            )

            raw = generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=120,
            )

            prediction = clean_response(raw)
            error = None

        except Exception as exc:
            prediction = ""
            error = str(exc)

        print("\nPREDICTED:", prediction)
        print("EXPECTED:", record["expected_meaning"])

        if error:
            print("ERROR:", error)

        results.append({
            **record,
            "model": MODEL,
            "mode": args.mode,
            "prediction": prediction,
            "error": error,
            "human_score": None,
        })

        # Save progress after every case.
        output_path.write_text(
            json.dumps(
                results,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print("\n" + "=" * 60)
    print("RIA-1 COMPREHENSION EVALUATION")
    print("=" * 60)
    print("Mode:", args.mode)
    print("Evaluated:", len(results))
    print(
        "Errors:",
        sum(r["error"] is not None for r in results)
    )
    print("Human scoring: pending")
    print("Saved:", output_path)


if __name__ == "__main__":
    main()

