import os
import json
from groq import Groq

# Load the env file manually if needed
try:
    with open("../../.env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val
except Exception:
    pass

api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_incident",
            "description": "Get incident info",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string"}
                },
                "required": ["incident_id"]
            }
        }
    }
]

models_to_test = ["groq/compound-mini", "qwen/qwen3.8-27b"]

for model in models_to_test:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "What is the status of incident INC-123?"}],
            tools=tools,
            tool_choice="auto"
        )
        message = response.choices[0].message
        if message.tool_calls:
            print(f"SUCCESS {model} tool call:", message.tool_calls[0].function.name)
        else:
            print(f"SUCCESS {model} but no tool call:", message.content)
    except Exception as e:
        print(f"FAILED {model}: {e}")

