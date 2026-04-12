import json
import os

from litellm import completion
from dotenv import load_dotenv

load_dotenv()

# Without reasoning
response = completion(
    model=os.getenv("MODEL_NAME"),
    messages=[{"role": "user", "content": "What's 2+2?"}]
)
print(json.dumps(response.model_dump(),indent=2,ensure_ascii=False))

print(response.choices[0].message.content)
