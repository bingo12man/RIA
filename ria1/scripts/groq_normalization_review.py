from groq import Groq
import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "ria1/data/evaluation"

SOURCE = BASE / "normalization_pair_audit_v1.json"
SUGGESTIONS = BASE / "normalization_gemini_suggestions_v1.json"
REVIEWS = BASE / "normalization_pair_reviews_v1.json"
EXPORT = BASE / "approved_normalization_pairs_v1.jsonl"

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
URL = "https://api.groq.com/openai/v1/chat/completions"


def save_json(path, obj):
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def source_hash(pairs):
    content = json.dumps(
        pairs, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def load_state(path, expected_hash, section):
    if not path.exists():
        return {
            "source_hash": expected_hash,
            section: {},
        }

    state = json.loads(path.read_text(encoding="utf-8"))

    if state.get("source_hash") != expected_hash:
        raise ValueError(
            f"Dataset mismatch in {path.name}"
        )

    return state


INSTRUCTIONS = """
You are a careful Tamil and Tanglish dataset reviewer.

Compare the Romanized Tamil sentence with its Tamil-script
equivalent. Do not translate freely or invent missing meaning.

Assess:
- Who is speaking and who acts
- Pronouns, plurality and honorifics
- Past/present/future tense
- Negation and prohibitions
- Commands, requests and questions
- Code-switched English vocabulary
- The actual meaning of Tamil words

Choose one classification:
faithful_script = faithful script conversion, including
natural colloquial spelling and punctuation differences.
normalization = same complete meaning but substantial
vocabulary or grammatical normalization.
incorrect = material change in meaning, actor, tense,
negation, request or intent.

For incorrect pairs, give a suggested corrected Tamil
sentence with the original meaning.

You MUST return a valid JSON object with these fields:
{
  "classification": "faithful_script",
  "meaning_preserved": true,
  "critical_error": false,
  "reason": "Short English explanation",
  "suggested_tamil": ""
}

Be conservative. Do not automatically approve ambiguous
or incomprehensible Tamil.
"""


def evaluate_pair(pair):
    key = os.getenv("GROQ_API_KEY")

    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    client = Groq(api_key=key, max_retries=0)

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_completion_tokens=1200,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": INSTRUCTIONS,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "tanglish": pair["tanglish"],
                        "tamil": pair["tamil"],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)

    allowed = {
        "faithful_script",
        "normalization",
        "incorrect",
    }

    if result.get("classification") not in allowed:
        raise ValueError("Invalid classification")

    for field in ("meaning_preserved", "critical_error"):
        if type(result.get(field)) is not bool:
            raise ValueError(f"Invalid {field}")

    for field in ("reason", "suggested_tamil"):
        if not isinstance(result.get(field), str):
            raise ValueError(f"Invalid {field}")

    if (
        result["classification"] == "incorrect"
        and not result["suggested_tamil"].strip()
    ):
        raise ValueError(
            "Incorrect classification without correction"
        )

    result["model"] = MODEL
    result["provider"] = "groq"
    result["evaluated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    audit = json.loads(
        SOURCE.read_text(encoding="utf-8")
    )
    pairs = audit["pairs"]

    if len(pairs) != 124:
        raise ValueError("Expected 124 pairs")

    fingerprint = source_hash(pairs)
    state = load_state(
        SUGGESTIONS, fingerprint, "suggestions"
    )
    suggestions = state["suggestions"]

    review_state = load_state(
        REVIEWS, fingerprint, "reviews"
    )
    approved = review_state["reviews"]

    pending = [
        pair for pair in pairs
        if str(pair["source_index"]) not in suggestions
        and str(pair["source_index"]) not in approved
    ]

    if args.limit > 0:
        pending = pending[:args.limit]

    print("\nRIA-1 — GROQ NORMALIZATION EVALUATION")
    print("=" * 55)
    print("Model:", MODEL)
    print("Existing suggestions:", len(suggestions))
    print("Already approved:", len(approved))
    print("Cases in this run:", len(pending))

    for index, pair in enumerate(pending, 1):
        rid = str(pair["source_index"])

        try:
            result = evaluate_pair(pair)
        except Exception as error:
            print(f"\nSTOPPED at pair {rid}")
            print(error)
            print("Previous results remain saved.")
            return

        suggestions[rid] = result

        # Keep all old Gemini suggestions unchanged.
        state["suggestions"] = suggestions
        save_json(SUGGESTIONS, state)

        print(
            f"{index}/{len(pending)} "
            f"Pair {rid}: {result['classification']}"
        )
        print("Reason:", result["reason"])

        # Conservative spacing to reduce token/minute issues.
        if index < len(pending):
            time.sleep(6)

    print("\nEvaluation completed for this run.")
    print("Total saved suggestions:", len(suggestions))
    print("Already human-approved:", len(approved))
    print("No human approvals were changed.")


if __name__ == "__main__":
    main()

