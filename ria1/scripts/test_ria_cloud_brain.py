"""Evaluate RIA's cloud conversational intelligence."""

import os
import time
from groq import Groq

client = Groq(timeout=30, max_retries=0)

MODEL = "openai/gpt-oss-120b"

SYSTEM = """
You are Ria, a joyful, witty, emotionally aware AI desk companion.

Speak naturally, warmly and concisely.
Be expressive when appropriate, not exaggerated.
Match the user's emotional tone.
Use one or two short spoken sentences for ordinary replies.

For greetings, be friendly and relaxed.
For exciting news, be genuinely enthusiastic.
For sadness, listen and respond with care.
For factual questions, answer directly and accurately.

Never invent personal experiences, activities, memories or tool actions.
Don't introduce unrelated music, guitar or hobbies.
Avoid repetitive Ahh, Ooooh, emojis and unnecessary questions.

When a request is unclear, ask one short clarification.
When you don't know something, acknowledge uncertainty.
Follow conversational context accurately.
"""

TESTS = [
    ("Greeting", [
        "How are you doing today?",
    ]),
    ("Excitement", [
        "I have some exciting news!",
    ]),
    ("Emotional support", [
        "I'm feeling a little sad today.",
    ]),
    ("Personal honesty", [
        "What did you do today?",
        "Did you listen to music today?",
    ]),
    ("Technical follow-ups", [
        "Explain machine learning with a simple example.",
        "Now explain that in two lines.",
        "Give me another example.",
        "I didn't understand that last example. Explain it more simply.",
    ]),
    ("Ambiguity", [
        "Remind me about that thing later.",
    ]),
]

total_tokens = 0

for name, turns in TESTS:
    print(f"\n{'=' * 55}")
    print("TEST:", name)

    messages = [{"role": "system", "content": SYSTEM}]

    for user_text in turns:
        messages.append({"role": "user", "content": user_text})

        start = time.perf_counter()

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.3,
                max_completion_tokens=250,
            )
        except Exception as exc:
            print("ERROR:", type(exc).__name__, str(exc)[:500])
            break

        elapsed = time.perf_counter() - start

        reply = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        total_tokens += tokens

        print("\nYOU:", user_text)
        print("RIA:", reply.strip() or "[EMPTY RESPONSE]")
        print("TIME:", round(elapsed, 2), "seconds")
        print("TOKENS:", tokens)

        if reply.strip():
            messages.append({
                "role": "assistant",
                "content": reply.strip(),
            })

print("\nTOTAL TOKENS:", total_tokens)
print("Cloud evaluation complete.")
