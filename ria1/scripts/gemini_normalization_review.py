
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

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL}:generateContent"
)


def save_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def digest(data):
    encoded = json.dumps(
        data, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_state(path, source_hash, section):
    if not path.exists():
        return {"source_hash": source_hash, section: {}}

    state = json.loads(path.read_text(encoding="utf-8"))

    if state.get("source_hash") != source_hash:
        raise ValueError(
            f"Source mismatch in {path.name}. "
            "Refusing to mix different datasets."
        )

    return state


def ask_gemini(pair):
    key = os.environ.get("GEMINI_API_KEY")

    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    instructions = """
You are reviewing a paired Tanglish-to-Tamil dataset.

Your job is to evaluate whether the Tamil sentence
faithfully preserves the meaning of the Romanized Tamil.

Pay attention to:
- Subject, person, gender and pronouns
- Negation and prohibitions
- Past, present and future tense
- Singular/plural and respect forms
- Commands, questions and requests
- Word meaning and English loanwords
- Natural conversational Tamil

Classify each pair:

faithful_script:
The Tamil is a faithful colloquial-script conversion.
Minor spelling or punctuation differences are acceptable.

normalization:
The Tamil preserves the complete intended meaning,
but rewrites some words, grammar or vocabulary.

incorrect:
The Tamil changes a significant part of the meaning,
loses a critical detail, or is incomprehensible.

Be conservative. Do not approve inaccurate conversions.
Do not invent content to make the pair seem correct.

For incorrect cases, suggest a corrected Tamil sentence
that preserves the original Tanglish meaning.

Return ONLY JSON:
{
  "classification": "faithful_script",
  "meaning_preserved": true,
  "critical_error": false,
  "reason": "Short explanation",
  "suggested_tamil": ""
}
"""

    task = {
        "tanglish": pair["tanglish"],
        "tamil": pair["tamil"],
    }

    payload = {
        "system_instruction": {
            "parts": [{"text": instructions}]
        },
        "contents": [{
            "role": "user",
            "parts": [{
                "text": json.dumps(task, ensure_ascii=False)
            }],
        }],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=120
        ) as response:
            result = json.load(response)

    except urllib.error.HTTPError as error:
        details = error.read().decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(
            f"HTTP {error.code}: {details[:600]}"
        ) from error

    parts = result["candidates"][0]["content"]["parts"]
    raw = "".join(
        part.get("text", "") for part in parts
    )
    suggestion = json.loads(raw)

    classification = suggestion.get("classification")

    if classification not in (
        "faithful_script", "normalization", "incorrect"
    ):
        raise ValueError("Invalid Gemini classification")

    for field in ("meaning_preserved", "critical_error"):
        if type(suggestion.get(field)) is not bool:
            raise ValueError(f"Invalid field: {field}")

    for field in ("reason", "suggested_tamil"):
        if not isinstance(suggestion.get(field), str):
            raise ValueError(f"Invalid field: {field}")

    if (
        classification == "incorrect"
        and not suggestion["suggested_tamil"].strip()
    ):
        raise ValueError("Missing correction for incorrect pair")

    return {
        **suggestion,
        "model": MODEL,
        "evaluated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


def evaluate(pairs, source_hash):
    state = load_state(
        SUGGESTIONS, source_hash, "suggestions"
    )
    suggestions = state["suggestions"]

    remaining = [
        pair for pair in pairs
        if str(pair["source_index"]) not in suggestions
    ]

    print("\nRIA-1 GEMINI NORMALIZATION EVALUATION")
    print("=" * 55)
    print("Completed:", len(suggestions), "/124")
    print("Remaining:", len(remaining))
    print("Model:", MODEL)

    for index, pair in enumerate(remaining, 1):
        rid = str(pair["source_index"])

        try:
            result = ask_gemini(pair)

        except Exception as error:
            print(f"\nStopped at pair {rid}: {error}")
            print("Completed suggestions are saved.")
            return

        suggestions[rid] = result
        save_json(SUGGESTIONS, state)

        print(
            f"{index}/{len(remaining)} | "
            f"Pair {rid} | {result['classification']}"
        )

        # Gentle pacing; this does not bypass quotas.
        time.sleep(1)

    print("\nGEMINI EVALUATION COMPLETE")
    print("Suggestions:", len(suggestions), "/124")


def review(pairs, source_hash):
    suggested_state = load_state(
        SUGGESTIONS, source_hash, "suggestions"
    )
    review_state = load_state(
        REVIEWS, source_hash, "reviews"
    )

    suggestions = suggested_state["suggestions"]
    reviews = review_state["reviews"]

    print("\nRIA-1 HUMAN APPROVAL")
    print("=" * 55)

    for index, pair in enumerate(pairs, 1):
        rid = str(pair["source_index"])

        if rid in reviews:
            continue

        suggestion = suggestions.get(rid)

        if not suggestion:
            continue

        print("\n" + "=" * 65)
        print(f"{index}/124")
        print("TANGLISH:", pair["tanglish"])
        print("TAMIL:", pair["tamil"])
        print()
        print("GEMINI:", suggestion["classification"])
        print("REASON:", suggestion["reason"])

        if suggestion["critical_error"]:
            print("CRITICAL ERROR FLAGGED")

        if suggestion["suggested_tamil"]:
            print(
                "SUGGESTED CORRECTION:",
                suggestion["suggested_tamil"]
            )

        print("\na = Accept Gemini decision")
        print("1 = Faithful script")
        print("2 = Normalization")
        print("3 = Enter corrected Tamil")
        print("s = Skip")
        print("q = Quit")

        while True:
            choice = input("Decision: ").strip().lower()

            if choice == "q":
                print("Progress preserved.")
                return

            if choice == "s":
                break

            if choice == "a":
                kind = suggestion["classification"]

                if kind == "incorrect":
                    correction = suggestion[
                        "suggested_tamil"
                    ].strip()

                    if not correction:
                        print("Correction missing.")
                        continue

                    decision = {
                        "status": "approved_corrected",
                        "type": "corrected",
                        "tamil": correction,
                    }
                else:
                    decision = {
                        "status": "approved",
                        "type": kind,
                        "tamil": pair["tamil"],
                    }

            elif choice in ("1", "2"):
                decision = {
                    "status": "approved",
                    "type": (
                        "faithful_script"
                        if choice == "1"
                        else "normalization"
                    ),
                    "tamil": pair["tamil"],
                }

            elif choice == "3":
                correction = input(
                    "Correct Tamil: "
                ).strip()

                if not correction:
                    print("Correction cannot be empty.")
                    continue

                decision = {
                    "status": "approved_corrected",
                    "type": "corrected",
                    "tamil": correction,
                }

            else:
                print("Invalid option.")
                continue

            decision["reviewed_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            reviews[rid] = decision
            save_json(REVIEWS, review_state)

            print("Approved and saved.")
            break

    print("\nHuman-approved:", len(reviews), "/124")

    if len(reviews) != len(pairs):
        print("Remaining approvals can be resumed.")
        return

    if EXPORT.exists():
        print("Export already exists; refusing overwrite.")
        return

    with EXPORT.open("x", encoding="utf-8") as file:
        for pair in pairs:
            rid = str(pair["source_index"])
            decision = reviews[rid]

            row = {
                "id": f"RIA-NORM-{int(rid):03d}",
                "tanglish": pair["tanglish"],
                "tamil": decision["tamil"],
                "pair_type": decision["type"],
                "review_status": "approved",
            }

            file.write(
                json.dumps(row, ensure_ascii=False)
                + "\n"
            )

    print("\nALL 124 PAIRS APPROVED")
    print("Exported:", EXPORT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evaluate", action="store_true"
    )
    parser.add_argument(
        "--review", action="store_true"
    )
    args = parser.parse_args()

    audit = json.loads(
        SOURCE.read_text(encoding="utf-8")
    )
    pairs = audit["pairs"]

    if len(pairs) != 124:
        raise ValueError("Expected 124 candidate pairs")

    source_hash = digest(pairs)

    if args.evaluate:
        evaluate(pairs, source_hash)
    elif args.review:
        review(pairs, source_hash)
    else:
        parser.error("Choose --evaluate or --review")


if __name__ == "__main__":
    main()

