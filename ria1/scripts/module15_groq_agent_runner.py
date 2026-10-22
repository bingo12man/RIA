"""RIA P1.4: Groq tool selection, without tool execution."""

import json
import os
import sys

from groq import Groq

from ria1.scripts.module15_agent_tools import TOOL_SCHEMAS


def main():
    request = json.load(sys.stdin)
    messages = request["messages"]

    client = Groq(
        api_key=os.environ["GROQ_API_KEY"],
        timeout=6.0,
        max_retries=1,
    )

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=messages,
        tools=TOOL_SCHEMAS,
        tool_choice="auto",
        temperature=0.2,
        max_completion_tokens=500,
    )

    message = response.choices[0].message

    tool_calls = []

    for call in message.tool_calls or []:
        if call.type != "function":
            continue

        tool_calls.append({
            "id": call.id,
            "name": call.function.name,
            "arguments": json.loads(call.function.arguments),
        })

    output = {
        "model": response.model,
        "reply": message.content or "",
        "tool_calls": tool_calls,
    }

    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
