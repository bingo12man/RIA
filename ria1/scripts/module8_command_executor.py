import json
import urllib.error
import urllib.request

from ria1.scripts.module8_voice_commands import parse_voice_command

REMINDER_API = "http://127.0.0.1:8001"


def request_reminders(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()

    request = urllib.request.Request(
        REMINDER_API + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Reminder API returned HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Reminder API unavailable. Is port 8001 running?"
        ) from exc


def execute_voice_command(text):
    command = parse_voice_command(text)
    action = command["action"]

    if action == "create":
        title = command["title"]
        minutes = command["minutes"]

        reminder = request_reminders(
            "POST",
            "/reminders",
            {"title": title, "minutes_from_now": minutes},
        )

        return {
            "action": "create",
            "success": True,
            "reply": f"Got it! I'll remind you to {title} in {minutes} {'minute' if minutes == 1 else 'minutes'}.",
            "reminder": reminder,
        }

    if action in {"snooze", "done", "skip"}:
        due = request_reminders("GET", "/reminders/due")

        # Accept either a list or a wrapped response.
        if isinstance(due, dict):
            due = due.get("reminders", due.get("items", []))

        if not isinstance(due, list):
            raise RuntimeError("Unexpected due reminders response")

        if len(due) == 0:
            return {
                "action": action,
                "success": False,
                "reply": "There isn't a due reminder to update right now.",
            }

        if len(due) > 1:
            return {
                "action": action,
                "success": False,
                "reply": "You have several due reminders. Please choose one on the screen.",
            }

        reminder = due[0]
        reminder_id = reminder["id"]

        if action == "snooze":
            minutes = command["minutes"]
            result = request_reminders(
                "POST",
                f"/reminders/{reminder_id}/snooze",
                {"minutes": minutes},
            )
            reply = f"Okay! Snoozed for {minutes} minutes."

        else:
            result = request_reminders(
                "POST",
                f"/reminders/{reminder_id}/{action}",
            )
            reply = (
                "Nice work! I've marked that reminder done."
                if action == "done"
                else "Okay, I've skipped that reminder."
            )

        return {
            "action": action,
            "success": True,
            "reply": reply,
            "reminder": result,
        }

    if action == "clarify":
        return {
            "action": "clarify",
            "success": False,
            "reply": command["reply"],
        }

    return {
        "action": "conversation",
        "success": False,
        "reply": "That isn't a supported reminder command yet.",
    }


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:])
    if not text:
        text = "Ria, remind me to practice guitar in 2 minutes."

    print(json.dumps(execute_voice_command(text), indent=2))
