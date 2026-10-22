"""RIA duplicate creation: single-claim execution.

A repeated claim never initiates another creation attempt.
"""

import json

from ria1.scripts.module15_tool_executor import OWNER, execute_tool
from ria1.scripts.module32_duplicate_claim import claim_duplicate
from ria1.scripts.module33_duplicate_recovery import recover_duplicate


def execute_approved_duplicate(session_id, request_id, user_id=OWNER):
    # RIA_P110844_RECOVER_BEFORE_RECHECK
    from ria1.scripts.module15_tool_executor import _ledger_connect

    with _ledger_connect() as db:
        table = db.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='duplicate_execution_claims'"
        ).fetchone()
        previous = (
            db.execute(
                "SELECT * FROM duplicate_execution_claims "
                "WHERE session_id=? AND request_id=? AND user_id=?",
                (session_id, request_id, user_id),
            ).fetchone()
            if table else None
        )

    if previous is not None:
        return recover_duplicate(session_id, request_id, user_id)

    # RIA_P110843_PRECLAIM_RECHECK
    # Do not consume approval when the reminder recheck fails.
    #
    # Only inspect an existing reservation; this performs no writes.
    from ria1.scripts.module30_duplicate_proposals import (
        get_reserved_duplicate,
    )
    from ria1.scripts.module34_duplicate_recheck import (
        recheck_duplicate,
    )

    reservation = get_reserved_duplicate(
        session_id, request_id, user_id
    )

    if reservation is None:
        raise PermissionError("No matching duplicate approval")

    # This read may occur on a replay. Replays will still be
    # handled by the existing claim/recovery mechanism below.
    # We will refine that distinction during gateway integration.
    import json
    precheck = recheck_duplicate(
        reservation["tool_name"],
        json.loads(reservation["args_json"]),
    )
    if reservation["original_reminder_id"] not in (
        precheck["matching_reminder_ids"]
    ):
        raise PermissionError("Approved original reminder no longer matches")

    claim = claim_duplicate(session_id, request_id, user_id)

    # RIA_P110838_READ_ONLY_REPLAY
    if not claim["new_claim"]:
        return recover_duplicate(
            session_id, request_id, user_id
        )

    arguments = json.loads(claim["args_json"])

    # RIA_P110842_DUPLICATE_RECHECK
    from ria1.scripts.module34_duplicate_recheck import (
        recheck_duplicate,
    )

    # Recheck only for a NEW claim.
    # A repeated claim follows read-only recovery above.
    # RIA_P110857_ATOMIC_DUPLICATE
    checked = recheck_duplicate(claim["tool_name"], arguments)
    original_id = claim["original_reminder_id"]
    if original_id not in checked["matching_reminder_ids"]:
        raise PermissionError("Original reminder no longer matches")

    result = execute_tool(
        claim["tool_name"],
        arguments,
        user_id,
        claim["execution_id"],
        duplicate_of_id=original_id,
    )

    if (
        not isinstance(result, dict)
        or result.get("success") is not True
        or result.get("action") != "reminder_created"
        or not isinstance(result.get("reminder"), dict)
    ):
        raise RuntimeError("Unverified duplicate reminder execution")

    return {
        "success": True,
        "action": "reminder_created",
        "reminder": result["reminder"],
        "reply": "Done! I've created another reminder.",
    }
