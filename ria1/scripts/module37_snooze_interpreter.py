"""RIA: GPT-OSS interpretation of natural snooze follow-ups.

This module never modifies reminders.
It returns validated, structured decisions for the trusted coordinator.
"""

import json
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

from ria1.scripts.module15_agent_bridge import ROOT, PYTHON
from ria1.scripts.module21_absolute_time import validate_scheduled_time

TIMEZONE = "Asia/Kolkata"
MAX_MINUTES = 365 * 24 * 60

POLICY = """
You are RIA's snooze conversation interpreter.

A reminder has already been selected by the trusted backend.
Interpret what the user wants to do with that reminder.

Return exactly one JSON object:
{
  "decision": "snooze|clarify|cancel_snooze|cancel_reminder|unrelated",
  "minutes": null,
  "scheduled_at": null,
  "reply": ""
}

Rules:

1. For a duration such as "15 minutes", "two hours" or
   "three days", use decision=snooze and convert to integer minutes.

2. For an exact date/time such as "tomorrow at eight in the
   morning", use decision=snooze and return scheduled_at as
   ISO-8601 including its UTC offset. Use the supplied current
   datetime and timezone. Do not invent an hour or AM/PM.

3. A snooze decision must contain exactly ONE of minutes
   or scheduled_at.

4. If a snooze duration/time is missing or ambiguous, use
   decision=clarify and ask a concise natural question.

5. "Never mind", "don't snooze" or "cancel the snooze"
   means cancel_snooze. The reminder must remain unchanged.

6. "Cancel the reminder itself" means cancel_reminder.
   This does NOT authorize cancellation. A separate trusted
   cancellation confirmation is required.

7. An unrelated request means unrelated. Do not inherit
   the previous snooze operation.

8. Corrections override earlier answers.
   Understand conversational English naturally.
   Do not use fixed phrase matching to interpret meaning.

9. If the user mentions a hypothetical action, quoted command
   or example, do not execute it.

10. Never claim a reminder has already been changed.

For snooze, reply must be empty.
For clarify, reply must be a nonempty question.
For every other decision, reply must be empty.

For non-snooze decisions, both minutes and scheduled_at
must be null.

Return JSON only.
"""


def _validate_output(result):
    if not isinstance(result, dict) or set(result) != {
        "decision", "minutes", "scheduled_at", "reply"
    }:
        raise ValueError("Invalid snooze decision structure")

    decision = result["decision"]
    minutes = result["minutes"]
    scheduled_at = result["scheduled_at"]
    reply = result["reply"]

    if decision not in {
        "snooze", "clarify", "cancel_snooze",
        "cancel_reminder", "unrelated",
    }:
        raise ValueError("Unsupported snooze decision")

    if not isinstance(reply, str):
        raise ValueError("Invalid snooze reply")

    if decision == "snooze":
        if reply:
            raise ValueError("Snooze cannot claim completion")

        if (minutes is None) == (scheduled_at is None):
            raise ValueError("Exactly one snooze time is required")

        if minutes is not None:
            if type(minutes) is not int or not (
                1 <= minutes <= MAX_MINUTES
            ):
                raise ValueError("Invalid snooze duration")

            return {
                "decision": "snooze",
                "minutes": minutes,
                "due_at": None,
                "reply": "",
            }

        if not isinstance(scheduled_at, str):
            raise ValueError("Invalid scheduled datetime")

        due_at = validate_scheduled_time(
            scheduled_at, TIMEZONE
        )

        return {
            "decision": "snooze",
            "minutes": None,
            "due_at": due_at,
            "reply": "",
        }

    if minutes is not None or scheduled_at is not None:
        raise ValueError("Unexpected snooze time")

    if decision == "clarify":
        if not reply.strip():
            raise ValueError("Clarification question required")
    elif reply:
        raise ValueError("Unexpected reply")

    return {
        "decision": decision,
        "minutes": None,
        "due_at": None,
        "reply": reply.strip(),
    }


def interpret_snooze(message, reminder, history=None):
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Empty user message")

    if not isinstance(reminder, dict):
        raise ValueError("Missing selected reminder")

    if (
        type(reminder.get("id")) is not int
        or reminder["id"] < 1
        or not isinstance(reminder.get("title"), str)
        or not reminder["title"].strip()
        or type(reminder.get("due_at")) is not int
        or reminder.get("status") != "pending"
    ):
        raise ValueError("Invalid selected reminder")

    if history is None:
        history = []

    if not isinstance(history, list) or len(history) > 24:
        raise ValueError("Invalid conversation history")

    payload = {
        "message": message,
        "reminder": {
            "id": reminder["id"],
            "title": reminder["title"],
            "due_at": reminder["due_at"],
        },
        "history": history,
        "calendar_context": {
            "current_local_datetime": datetime.now(
                ZoneInfo(TIMEZONE)
            ).isoformat(timespec="seconds"),
            "timezone": TIMEZONE,
        },
    }

    # GPT-OSS runs in RIA's existing Groq-enabled interpreter.
    code = """
import json, os, sys
from groq import Groq

payload = json.load(sys.stdin)
policy = sys.argv[1]

response = Groq(
    api_key=os.environ["GROQ_API_KEY"],
    timeout=15.0,
    max_retries=1,
).chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {"role": "system", "content": policy},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ],
    response_format={"type": "json_object"},
    temperature=0,
    max_completion_tokens=350,
)

result = json.loads(response.choices[0].message.content)
print(json.dumps(result, ensure_ascii=False))
"""

    process = subprocess.run(
        [str(PYTHON), "-c", code, POLICY],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        timeout=35,
        check=False,
    )

    if process.returncode != 0:
        raise RuntimeError(
            "Snooze interpretation failed: "
            + process.stderr[-300:]
        )

    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid GPT-OSS response") from exc

    return _validate_output(result)
