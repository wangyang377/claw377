import json
import os
import subprocess

from dotenv import load_dotenv
from litellm import completion
from prompt_toolkit import PromptSession

load_dotenv()


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


TOOL_HANDLERS = {
    "bash": lambda **kwargs: run_bash(kwargs["command"]),
}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run",
                    }
                },
                "required": ["command"],
            },
        },
    }
]


def agent_loop(messages: list[dict]) -> str:
    while True:
        response = completion(
            model=os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL"),
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        messages.append(choice.message.model_dump(exclude_none=True))

        if choice.finish_reason != "tool_calls":
            return choice.message.content

        for tool_call in choice.message.tool_calls:
            tool_name = tool_call.function.name
            handler = TOOL_HANDLERS.get(tool_name)
            args = json.loads(tool_call.function.arguments or "{}")
            output = handler(**args) if handler else f"Unknown tool: {tool_name}"

            print(f"> {tool_name}:")
            print(output[:200])

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "tool_name":tool_call.function.name,
                    "content": output
                }
            )


if __name__ == "__main__":
    history: list[dict] = []
    session = PromptSession()

    while True:
        query = session.prompt("You> ")
        if query in {"q", "quit", "exit"}:
            break

        history.append({"role": "user", "content": query})
        response_content = agent_loop(history)
        print(response_content)
        print()
