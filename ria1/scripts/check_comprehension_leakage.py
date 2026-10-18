
import difflib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ria1/data/mlx_comprehension_v1"
BENCHMARK = (
    ROOT / "ria1/data/evaluation/"
    "tanglish_comprehension_v1.jsonl"
)

OUT = DATA / "leakage_report.json"


def load_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def normalize(text):
    return " ".join(
        re.sub(r"[^\w\s]", " ", text.casefold()).split()
    )


def current_user(text):
    return text.rsplit(
        "Current user:", 1
    )[-1].strip()


def score(a, b):
    a = normalize(a)
    b = normalize(b)

    sequence = difflib.SequenceMatcher(
        None, a, b
    ).ratio()

    left = set(a.split())
    right = set(b.split())

    jaccard = (
        len(left & right) / len(left | right)
        if left | right else 0
    )

    return max(sequence, jaccard)


def main():
    train = load_jsonl(DATA / "train.jsonl")
    valid = load_jsonl(DATA / "valid.jsonl")
    benchmark = load_jsonl(BENCHMARK)

    train_texts = [
        current_user(row["messages"][1]["content"])
        for row in train
    ]

    valid_texts = [
        current_user(row["messages"][1]["content"])
        for row in valid
    ]

    warnings = []

    def compare(left, right, pair_type):
        for i, a in enumerate(left):
            for j, b in enumerate(right):
                value = score(a, b)

                if value >= 0.75:
                    warnings.append({
                        "comparison": pair_type,
                        "left_index": i,
                        "right_index": j,
                        "similarity": round(value, 3),
                        "left": a,
                        "right": b,
                    })

    compare(
        train_texts,
        valid_texts,
        "train_vs_validation",
    )

    benchmark_texts = [
        row["user_message"]
        for row in benchmark
    ]

    compare(
        train_texts,
        benchmark_texts,
        "train_vs_benchmark",
    )

    compare(
        valid_texts,
        benchmark_texts,
        "validation_vs_benchmark",
    )

    OUT.write_text(
        json.dumps(
            {
                "train": len(train),
                "validation": len(valid),
                "benchmark": len(benchmark),
                "warnings": warnings,
                "note": (
                    "Lexical similarity screen only. "
                    "Semantic leakage is not fully excluded."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nRIA-1 COMPREHENSION LEAKAGE CHECK")
    print("=" * 50)
    print("Train:", len(train))
    print("Validation:", len(valid))
    print("Benchmark:", len(benchmark))
    print("Warnings:", len(warnings))

    for warning in warnings[:15]:
        print("\n", warning["comparison"])
        print("Similarity:", warning["similarity"])
        print("A:", warning["left"])
        print("B:", warning["right"])

    print("\nReport:", OUT)


if __name__ == "__main__":
    main()

