import re
from functools import lru_cache

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Initial experimental threshold, not a calibrated production value.
THRESHOLD = 0.45


@lru_cache(maxsize=1)
def get_encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )


def memory_description(key, value):
    if key == "instrument":
        return (
            f"The user is learning {value}. "
            f"The user's musical instrument is {value}. "
            f"The user's music practice and instrument."
        )

    return f"The user's {key.replace('_', ' ')} is {value}."


def semantic_retrieve(message, memories, threshold=THRESHOLD):
    """
    Return scored candidates.

    A score indicates embedding similarity, not certainty
    that a memory is relevant.
    """
    message = message.strip()

    if not message or not memories:
        return []

    encoder = get_encoder()

    entries = [
        (key, value, memory_description(key, value))
        for key, value in memories.items()
    ]

    texts = [message] + [entry[2] for entry in entries]

    vectors = encoder.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    query = vectors[0]
    candidates = []

    for (key, value, _), vector in zip(entries, vectors[1:]):
        score = float(np.dot(query, vector))

        if score >= threshold:
            candidates.append({
                "key": key,
                "value": value,
                "score": round(score, 4),
            })

    return sorted(
        candidates,
        key=lambda item: item["score"],
        reverse=True,
    )
