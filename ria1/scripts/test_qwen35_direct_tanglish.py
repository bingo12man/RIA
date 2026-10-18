
import json
import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "ria1/data/evaluation/qwen35_direct_v1"

MODEL = "qwen3.5:4b"
URL = "http://127.0.0.1:11434/api/chat"

# New development examples, not training material.
# Do not revise them after observing predictions.
CASES = [
    ("001", "Naan innume ready aagala, konjam time kudu.",
     "I'm still not ready; give me some time."),
    ("002", "Avan varuvaannu sonnaan, aana varave illa.",
     "He said he would come, but he never came."),
    ("003", "Enakku tea venum, coffee vendaam.",
     "I want tea, not coffee."),
    ("004", "Naalaikku vara mudiyadhu, Monday varren.",
     "I can't come tomorrow; I'll come on Monday."),
    ("005", "Nee anuppuna document innum open pannala.",
     "I haven't opened the document you sent yet."),
    ("006", "Ava enna koopta, naan kekkala.",
     "She called out to me, but I didn't hear."),
    ("007", "Indha message-a delete pannaadha, save pannu.",
     "Don't delete this message; save it."),
    ("008", "Avanga mudichittaangala illa innum panraangala?",
     "Have they finished, or are they still working on it?"),
    ("009", "Idhu ennoda laptop illa, en friend-odadhu.",
     "This isn't my laptop; it belongs to my friend."),
    ("010", "Enakku konjam nervous-ah irukku, aana try panren.",
     "I'm a little nervous, but I'll try."),
    ("011", "Five minutes-la call panren nu sonnen.",
     "I said I'd call in five minutes."),
    ("012", "Indha code work aagudhu, aana result thappu.",
     "This code runs, but its result is wrong."),
    ("013", "En permission illaama file share panna koodaadhu.",
     "You must not share the file without my permission."),
    ("014", "Nethu sonna plan-a innaikku change pannitaanga.",
     "They changed today the plan discussed yesterday."),
    ("015", "Yaarume reply pannala, adhaan wait panren.",
     "Nobody replied, so I'm waiting."),
    ("016", "Rendu tasks irukku, urgent aanadha first pannu.",
     "There are two tasks; do the urgent one first."),
    ("017", "Unkitta kovam illa, situation mela dhaan kovam.",
     "I'm not angry with you; I'm angry about the situation."),
    ("018", "Enakku indha explanation podhala, example kudu.",
     "This explanation isn't enough for me; give an example."),
    ("019", "Ava vara sollala, vara vendaamnu sonna.",
     "She didn't ask me to come; she told me not to come."),
    ("020", "Meeting start aaguradhukku munnaadi remind pannu.",
     "Remind me before the meeting starts."),
]

SYSTEM = (
    "You understand conversational Tanglish: Tamil written "
    "using English letters, often mixed with English words. "
    "Explain the exact meaning of the user's sentence in "
    "natural English. Preserve subjects, actions, pronouns, "
    "negation, tense, time, quantities, requests and questions. "
    "Do not answer the request or execute it. "
    "Do not invent information. "
    "Return only the English meaning."
)


def call_model(text):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text},
        ],
        "think": False,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 160,
            "num_ctx": 2048,
        },
        "keep_alive": "2m",
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


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(
            data, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    predictions = OUTPUT_DIR / "predictions.jsonl"
    manifest_path = OUTPUT_DIR / "manifest.json"

    configuration = {
        "model": MODEL,
        "system": SYSTEM,
        "cases_sha256": fingerprint(CASES),
        "thinking": False,
        "temperature": 0,
        "num_predict": 160,
    }

    if manifest_path.exists():
        previous = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        if previous != configuration:
            raise ValueError(
                "Evaluation configuration changed; "
                "cannot mix predictions."
            )
    elif predictions.exists():
        raise ValueError(
            "Predictions exist without a manifest."
        )
    else:
        manifest_path.write_text(
            json.dumps(configuration, indent=2) + "\n",
            encoding="utf-8",
        )

    completed = {}

    if predictions.exists():
        for line in predictions.read_text(
            encoding="utf-8"
        ).splitlines():
            if not line.strip():
                continue

            row = json.loads(line)

            if row["id"] in completed:
                raise ValueError("Duplicate saved prediction")

            completed[row["id"]] = row

    if not set(completed).issubset(
        {case[0] for case in CASES}
    ):
        raise ValueError("Unknown saved case IDs")

    print("\nRIA-1 — MODULE 4.65")
    print("QWEN3.5 DIRECT TANGLISH TEST")
    print("=" * 60)
    print("Model:", MODEL)
    print("Cases:", len(CASES))
    print("Already completed:", len(completed))

    for index, (rid, original, expected) in enumerate(
        CASES, 1
    ):
        if rid in completed:
            continue

        try:
            prediction = call_model(original)
        except Exception as error:
            print(f"\nStopped at case {rid}: {error}")
            print("Completed predictions are saved.")
            return

        row = {
            "id": rid,
            "tanglish": original,
            "expected": expected,
            "predicted": prediction,
        }

        with predictions.open(
            "a", encoding="utf-8"
        ) as file:
            file.write(
                json.dumps(row, ensure_ascii=False)
                + "\n"
            )

        print(f"\n{index}/20 — RIA-NEW-{rid}")
        print("INPUT:", original)
        print("EXPECTED:", expected)
        print("QWEN3.5:", prediction)

    print("\n" + "=" * 60)
    print("Completed: 20/20")
    print("Saved:", predictions)
    print("Status: Human scoring required")


if __name__ == "__main__":
    main()

