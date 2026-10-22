"""RIA P1.2 — Allowed agent tool definitions.

These are declarations only. No tool executes here.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "memory_save",
            "description": (
                "Save an explicitly requested personal fact. "
                "Do not infer permission to save from ordinary chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "The exact fact to remember."
                    }
                },
                "required": ["fact"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list",
            "description": "Recall the user's saved personal memories.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_update",
            "description": (
                "Correct a specific existing personal memory. "
                "The old fact must match exactly one saved memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "old_fact": {"type": "string"},
                    "new_fact": {"type": "string"},
                },
                "required": ["old_fact", "new_fact"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_forget",
            "description": (
                "Forget one explicitly identified saved memory. "
                "Never delete all memories through this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exact_fact": {"type": "string"},
                },
                "required": ["exact_fact"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminder_create",
            "description": (
                "Create a one-time reminder when the user "
                "provides a task and an unambiguous relative time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "minutes_from_now": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 525600,
                    },
                },
                "required": ["title", "minutes_from_now"],
                "additionalProperties": False,
            },
        },
    },
]

# RIA_P11073_ABSOLUTE_TOOL_SCHEMA
TOOL_SCHEMAS.append({
    "type": "function",
    "function": {
        "name": "reminder_create_absolute",
        "description": (
            "Create a reminder at an explicit, unambiguous "
            "calendar datetime with an IANA timezone."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "scheduled_at": {"type": "string"},
                "timezone": {"type": "string"},
            },
            "required": [
                "title", "scheduled_at", "timezone"
            ],
            "additionalProperties": False,
        },
    },
})


TOOL_NAMES = frozenset(
    item["function"]["name"] for item in TOOL_SCHEMAS
)
