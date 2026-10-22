"""Read-only evaluation of RIA's compact decision policy."""

import json
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

CASES = {
    "negated_memory": {
        "message": (
            "Don't remember this. I'm just giving an example: "
            "I prefer fictional orange notebooks."
        ),
        "expected": "respond",
        "history": [],
    },
    "memory_recall": {
        "message": "What personal information have you saved about me?",
        "expected": "execute",
        "expected_tool": "memory_list",
        "history": [],
    },
    "existing_reminder": {
        "message": (
            "I meant the 9 PM reminder, not the 7 PM one."
        ),
        "expected": "clarify",
        "history": [],
    },
    "memory_ambiguity": {
        "message": "What do you remove about me?",
        "expected": "clarify",
        "history": [],
    },
    "reminder_reschedule": {
        "message": "Move my exercise reminder to Friday at 7 AM.",
        "expected": "execute",
        "expected_tool": "reminder_manage_lookup",
        "history": [],
    },
    "conversation": {
        "message": "Hey RIA! I've been coding all day. How's it going?",
        "expected": "respond",
        "history": [],
    },
}

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in CASES:
        print("Available cases:", ", ".join(CASES))
        raise SystemExit(2)

    name = sys.argv[1]
    case = CASES[name]

    payload = {
        "message": case["message"],
        "memories": {},
        "history": case["history"],
        "calendar_context": {
            "current_local_datetime": datetime.now(
                ZoneInfo("Asia/Kolkata")
            ).isoformat(timespec="seconds"),
            "timezone": "Asia/Kolkata",
        },
    }

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ria1.scripts.module19_decision_runner",
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=60,
    )

    if result.returncode:
        print("INCONCLUSIVE — Runner/API error")
        print(result.stderr[-700:])
        raise SystemExit(2)

    decision = json.loads(result.stdout)

    assert set(decision) == {
        "decision", "tool", "arguments", "reply"
    }

    print("Case:", name)
    print("Decision:", decision["decision"])
    print("Tool:", decision["tool"])
    print("Reply:", decision["reply"])

    assert decision["decision"] == case["expected"]

    if "expected_tool" in case:
        assert decision["tool"] == case["expected_tool"]
    else:
        assert decision["tool"] is None
        assert decision["arguments"] == {}

    print("PASS — Decision matched expected behavior")

if __name__ == "__main__":
    main()
