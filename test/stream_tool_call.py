tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current temperature for a given location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City and country e.g. Bogota, Colombia"
                }
            },
            "required": [
                "location"
            ],
            "additionalProperties": False
        }
    }
}]

import json
import os

from litellm import completion
from dotenv import load_dotenv

load_dotenv()


stream = completion(
    model=os.getenv("MODEL_NAME"),
    messages=[{"role": "user", "content": "你好，介绍一下你是谁"}],
    tools=tools,
    stream=True
)

for event in stream:
    print(json.dumps(event.model_dump(), indent=2, ensure_ascii=False))
