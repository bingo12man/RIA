"""Read-only recovery for previously claimed duplicate creation."""

import json

from ria1.scripts.module15_tool_executor import (
    OWNER,
    _ledger_connect,
    _recover_absolute_reminder,
    _recover_reminder,
)
from ria1.scripts.module32_duplicate_claim import claim_duplicate


def recover_duplicate(session_id, request_id, user_id=OWNER):
    claim = claim_duplicate(session_id, request_id, user_id)

    # Recovery must only inspect an EXISTING claim.
    if claim["new_claim"]:
        raise RuntimeError(
            "No prior execution to recover; "
            "new claim was not executed"
        )

    arguments = json.loads(claim["args_json"])
    execution_id = claim["execution_id"]

    with _ledger_connect() as db:
        record = db.execute(
            """
            SELECT *
            FROM tool_executions
            WHERE execution_id = ?
            """,
            (execution_id,),
        ).fetchone()

    if record is None:
        raise RuntimeError(
            "Execution was claimed but never started; "
            "manual reconciliation required"
        )

    # RIA_P110836_FINGERPRINT
    from ria1.scripts.module15_tool_executor import (
        _request_hash,
        _validate,
    )

    validated_args = _validate(
        claim["tool_name"], arguments
    )

    # RIA_P110860_DURABLE_ORIGINAL_ID
    original_id = claim["original_reminder_id"]
    if type(original_id) is not int or original_id <= 0:
        raise PermissionError("Legacy claim has no durable original ID")

    expected_hash = _request_hash(
        claim["tool_name"],
        {**validated_args, "_duplicate_of_id": original_id},
        user_id,
    )

    if (
        record["user_id"] != user_id
        or record["tool_name"] != claim["tool_name"]
        or record["request_hash"] != expected_hash
    ):
        raise PermissionError("Execution fingerprint mismatch")

    if record["status"] == "completed":
        result = json.loads(record["result_json"])
    else:
        if claim["tool_name"] == "reminder_create_absolute":
            reminder = _recover_absolute_reminder(
                execution_id, arguments
            )
        else:
            reminder = _recover_reminder(
                execution_id, arguments
            )

        if reminder is None:
            raise RuntimeError(
                "Duplicate creation outcome remains uncertain; "
                "no new creation request was sent"
            )

        result = {
            "success": True,
            "action": "reminder_created",
            "reminder": reminder,
        }

    if (
        not isinstance(result, dict)
        or result.get("success") is not True
        or result.get("action") != "reminder_created"
        or not isinstance(result.get("reminder"), dict)
    ):
        raise RuntimeError("Unverified recovery result")

    return {
        "success": True,
        "action": "reminder_created",
        "reminder": result["reminder"],
        "reply": "Done! I've created another reminder.",
    }
