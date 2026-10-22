"""RIA duplicate reminder confirmation — decision only."""

import json
import os


SYSTEM_POLICY = """
You interpret the user's response to RIA asking whether to
create another reminder that duplicates an existing reminder.

Return exactly:
{"decision":"confirm|decline|clarify|unrelated"}

Rules:
- confirm: User explicitly approves creating another reminder.
- decline: User refuses, says no, or wants to keep only the existing one.
- clarify: User's reply is ambiguous about creating another.
- unrelated: User changes the subject, asks an unrelated question,
  or makes a hypothetical statement.


RIA_P110824_HYPOTHETICAL_POLICY:

A hypothetical question about approval is NOT approval.
Classify hypothetical questions as unrelated, even when they
contain the word "yes" or "confirm".

Examples:
"What if I said yes?" -> unrelated
"Suppose I agreed?" -> unrelated
"If I said yes, would you create another?" -> unrelated
"Would you create another one if I agreed?" -> unrelated

Do not treat these as clarify. The user is asking a question,
not expressing uncertainty about whether to approve.

An actual question requesting explanation is unrelated.
An uncertain answer to the confirmation question is clarify.

"Yes, create another one." -> confirm
"No, don't create another." -> decline
"I'm not sure." -> clarify

Never execute a reminder creation from a hypothetical statement.

Never infer approval from silence, numbers, or unrelated speech.
Negated approvals are not approvals.
Understand English, Tamil and Tanglish naturally.
Return JSON only.
"""


def decide_duplicate_confirmation(message):
    from groq import Groq
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Empty confirmation message")

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is missing")

    client = Groq(timeout=15.0, max_retries=1)

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM_POLICY},
            {
                "role": "user",
                "content": (
                    "RIA previously asked: "
                    "'You already have an exercise reminder at 9 PM. "
                    "Do you want to create another one?'\n"
                    f"User replied: {message}"
                ),
            },
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    if (
        not isinstance(result, dict)
        or set(result) != {"decision"}
        or result["decision"]
        not in {"confirm", "decline", "clarify", "unrelated"}
    ):
        raise ValueError("Invalid duplicate confirmation decision")

    return result["decision"]
