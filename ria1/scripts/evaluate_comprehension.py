
import argparse
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "ria1/data/evaluation/tanglish_comprehension_v1.jsonl"
OUT = ROOT / "ria1/data/evaluation"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemma3:4b")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    records = [
        json.loads(line)
        for line in DATA.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    if not 1 <= args.limit <= len(records):
        parser.error("Invalid --limit value")

    results = []

    with httpx.Client(
        timeout=180, trust_env=False
    ) as client:
        for record in records[:args.limit]:
            print("\n" + "=" * 55)
            print("ID:", record["id"])
            print("USER:", record["user_message"])

            try:
                response = client.post(
                    "http://127.0.0.1:11434/api/chat",
                    json={
                        "model": args.model,
                        "stream": False,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are evaluating Tanglish "
                                    "language comprehension. "
                                    "Explain in one short English "
                                    "sentence what the user means. "
                                    "Do not answer the user's request."
                                ),
                            },
                            {
                                "role": "user",
                                "content": record["user_message"],
                            },
                        ],
                        "options": {
                            "temperature": 0,
                            "num_predict": 100,
                        },
                    },
                )
                response.raise_for_status()
                prediction = response.json()["message"]["content"]
                error = None
            except Exception as exc:
                prediction = ""
                error = str(exc)

            print("PREDICTED:", prediction)
            print("EXPECTED:", record["expected_meaning"])

            results.append({
                **record,
                "model": args.model,
                "prediction": prediction,
                "error": error,
                "human_score": None,
            })

    OUT.mkdir(parents=True, exist_ok=True)

    safe_model = args.model.replace("/", "_").replace(":", "_")
    path = OUT / f"{safe_model}_comprehension_{args.limit}.json"

    path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 55)
    print("Evaluation responses:", len(results))
    print("Saved:", path)
    print("Human scoring: pending")


if __name__ == "__main__":
    main()

